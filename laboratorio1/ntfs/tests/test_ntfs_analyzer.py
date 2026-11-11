import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import ntfs_analyzer as na  # noqa: E402

IMAGE = os.path.join(ROOT, "lab_ntfs.img")
HAVE_TSK = shutil.which("fls") and shutil.which("icat")


class TestDataRuns(unittest.TestCase):
    def test_negative_offset(self):
        runs = na.decode_runs(bytes.fromhex("31 10 00 20 00 21 08 00 F8 00".replace(" ", "")))
        self.assertEqual(runs, [(8192, 16), (6144, 8)])

    def test_sparse_run(self):
        # 8 clusters at LCN 100, 4 sparse clusters, 2 clusters at +20 -> LCN 120
        data = bytes([0x11, 0x08, 0x64, 0x01, 0x04, 0x11, 0x02, 0x14, 0x00])
        self.assertEqual(na.decode_runs(data), [(100, 8), (None, 4), (120, 2)])

    def test_empty(self):
        self.assertEqual(na.decode_runs(b"\x00"), [])


class TestFixups(unittest.TestCase):
    def make_record(self, tamper=False):
        buf = bytearray(1024)
        buf[0:4] = b"FILE"
        struct.pack_into("<HH", buf, 4, 0x30, 3)
        buf[0x30:0x32] = b"\x66\x04"      # USN
        buf[0x32:0x34] = b"\xAA\xBB"      # original bytes of sector 0 tail
        buf[0x34:0x36] = b"\xCC\xDD"      # original bytes of sector 1 tail
        buf[510:512] = b"\x66\x04"
        buf[1022:1024] = b"\x66\x04" if not tamper else b"\x00\x00"
        return bytes(buf)

    def test_apply(self):
        out, ok, usn, saved = na.apply_fixups(self.make_record())
        self.assertTrue(ok)
        self.assertEqual(out[510:512], b"\xAA\xBB")
        self.assertEqual(out[1022:1024], b"\xCC\xDD")
        self.assertEqual(usn, b"\x66\x04")

    def test_torn_write_detected(self):
        self.assertFalse(na.apply_fixups(self.make_record(tamper=True))[1])


class TestHelpers(unittest.TestCase):
    def test_le_hex(self):
        self.assertEqual(na.le_hex(bytes([0x88, 0x04])), "88 04 -> 0488h = 1160d")

    def test_filetime(self):
        self.assertEqual(na.filetime(116444736000000000), "1970-01-01 00:00:00 UTC")


@unittest.skipUnless(os.path.exists(IMAGE), "lab_ntfs.img missing: run build_ntfs_image.sh")
class TestImage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vol = na.Volume(IMAGE)

    @classmethod
    def tearDownClass(cls):
        cls.vol.close()

    def test_boot_sector(self):
        v = self.vol
        self.assertEqual(v.part_start, 2048)
        self.assertEqual(v.bytes_per_sector, 512)
        self.assertEqual(v.sectors_per_cluster, 8)
        self.assertEqual(v.cluster_size, 4096)
        self.assertEqual(v.record_size, 1024)
        self.assertEqual(v.index_block_size, 4096)
        self.assertEqual(v.boot_signature, b"\x55\xaa")
        self.assertEqual(v.mft_sector, 2048 + v.mft_lcn * 8)
        self.assertEqual(v.total_sectors + 1, 409600)

    def test_mft_record_zero_and_root(self):
        r0 = self.vol.record(0)
        self.assertEqual(r0.name, "$MFT")
        self.assertTrue(r0.fixup_ok)
        root = self.vol.record(na.ROOT_RECORD)
        self.assertTrue(root.is_dir)
        self.assertEqual(root.name, ".")

    def test_large_directory_uses_index_allocation(self):
        rec, _ = self.vol.resolve("/Muchos")
        self.assertIsNotNone(rec.attr(na.ATTR_INDEX_ALLOC, "$I30"))
        entries = [e for e in self.vol.list_dir(rec) if e["namespace"] != 2]
        self.assertEqual(len(entries), 60)
        self.assertTrue(all(isinstance(e["where"], dict) for e in entries))

    def test_small_directory_is_resident(self):
        rec, _ = self.vol.resolve("/Codigo/asm")
        self.assertIsNone(rec.attr(na.ATTR_INDEX_ALLOC, "$I30"))

    def test_resident_vs_nonresident(self):
        small, _ = self.vol.resolve("/Documentos/pequeno.txt")
        big, _ = self.vol.resolve("/Imagenes/tierra.jpg")
        self.assertFalse(small.attr(na.ATTR_DATA).non_resident)
        self.assertTrue(big.attr(na.ATTR_DATA).non_resident)
        self.assertEqual(na.signature_of(self.vol.read_file("/Imagenes/tierra.jpg")), "JPEG")
        self.assertEqual(na.signature_of(self.vol.read_file("/Aplicaciones/putty.exe")),
                         "Ejecutable Windows (PE/MZ)")

    def test_ads_detected(self):
        rec, _ = self.vol.resolve("/Documentos/nota.txt")
        self.assertEqual([a.name for a in rec.streams], ["", "secreto"])
        self.assertIn(b"Alternate Data Stream", self.vol.read_file("/Documentos/nota.txt:secreto", "secreto"))

    def test_deleted_detected(self):
        items = {d["record"]: d for d in self.vol.deleted()}
        self.assertTrue(items, "no deleted records found")
        previews = [d["preview"] for d in items.values()]
        self.assertTrue(any(p.startswith(b"Este archivo sera borrado") for p in previews))
        big = [d for d in items.values() if d["preview"].startswith(b"BORRADO 00000")]
        self.assertEqual(len(big), 1)
        self.assertFalse(big[0]["resident"])
        # data of the deleted non-resident file is still on disk and recoverable
        rec = self.vol.record(big[0]["record"])
        self.assertEqual(len(self.vol.read_attr(rec.attr(na.ATTR_DATA))), big[0]["size"])

    def test_nested_path_walk(self):
        rec, steps = self.vol.resolve("/Proyectos/2025/Lab2/informe/datos_largo.bin")
        self.assertEqual([s["name"] for s in steps][1:],
                         ["Proyectos", "2025", "Lab2", "informe", "datos_largo.bin"])
        self.assertEqual(rec.number, steps[-1]["record"])

    def test_json_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.json")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = na.main([IMAGE, "--tree", "--json", out])
            self.assertEqual(rc, 0)
            with open(out) as fh:
                data = json.load(fh)
            self.assertEqual(data["partition_start"], 2048)
            self.assertEqual(data["tree"]["record"], 5)


@unittest.skipUnless(os.path.exists(IMAGE) and HAVE_TSK, "needs lab_ntfs.img and sleuthkit")
class TestSleuthKitCrossCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vol = na.Volume(IMAGE)
        out = subprocess.run(["fls", "-o", "2048", "-r", "-p", IMAGE], capture_output=True,
                             text=True, check=True).stdout
        cls.files = []
        for line in out.splitlines():
            m = re.match(r"^r/r (\d+)-(\d+)-(\d+):\s+(.*)$", line)
            if m and not m.group(4).startswith("$") and "$OrphanFiles" not in m.group(4):
                cls.files.append((int(m.group(1)), int(m.group(3)), "/" + m.group(4)))

    @classmethod
    def tearDownClass(cls):
        cls.vol.close()

    def test_every_allocated_file(self):
        self.assertGreaterEqual(len(self.files), 80)
        checked = 0
        for inode, attr_id, path in self.files:
            stream = path.split("/")[-1].split(":", 1)[1] if ":" in path.split("/")[-1] else ""
            with self.subTest(path=path):
                rec, _ = self.vol.resolve(path)
                self.assertEqual(rec.number, inode)
                mine = self.vol.read_file(path, stream)
                tsk = subprocess.run(["icat", "-o", "2048", IMAGE, f"{inode}-128-{attr_id}"],
                                     capture_output=True, check=True).stdout
                self.assertEqual(hashlib.sha256(mine).hexdigest(), hashlib.sha256(tsk).hexdigest())
                checked += 1
        self.assertEqual(checked, len(self.files))

    def test_deleted_matches_tsk(self):
        out = subprocess.run(["fls", "-o", "2048", "-r", "-d", IMAGE], capture_output=True,
                             text=True, check=True).stdout
        tsk = {int(m.group(1)) for m in re.finditer(r"OrphanFile-(\d+)", out)}
        mine = {d["record"] for d in self.vol.deleted()}
        self.assertTrue(mine <= tsk, (mine, tsk))


if __name__ == "__main__":
    unittest.main()

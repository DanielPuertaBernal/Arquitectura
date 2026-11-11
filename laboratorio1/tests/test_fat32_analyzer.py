"""Unit tests for fat32_analyzer (stdlib unittest only).

Run from the project directory:
    python3 -I -m unittest discover -s tests -v
"""

import os
import struct
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import fat32_analyzer as fa  # noqa: E402

REAL_IMG = os.path.join(PROJECT_DIR, "Arqui22025.img")
FAT16_ISO = os.path.join(PROJECT_DIR, "arqui.iso")
have_real = unittest.skipUnless(os.path.exists(REAL_IMG), "Arqui22025.img not present")
have_iso = unittest.skipUnless(os.path.exists(FAT16_ISO), "arqui.iso not present")


# --------------------------------------------------------------------------
# Synthetic FAT32 builder
# --------------------------------------------------------------------------

BPS, SPC, RESERVED, NFATS = 512, 1, 32, 2
CLUSTERS = 65600  # >= 65525 so the volume is really FAT32
SPF = (CLUSTERS + 2) * 4 // BPS + 1
DATA_START = RESERVED + NFATS * SPF
TOTAL = DATA_START + CLUSTERS


def ref_checksum(name11: bytes) -> int:
    """Independent (rotate-right) implementation of the LFN checksum."""
    s = 0
    for c in name11:
        s = (((s >> 1) | ((s & 1) << 7)) + c) & 0xFF
    return s


def short_entry(name11: bytes, attr: int, cluster: int, size: int, deleted=False) -> bytes:
    e = bytearray(32)
    e[0:11] = name11
    e[11] = attr
    struct.pack_into("<H", e, 20, cluster >> 16)
    struct.pack_into("<H", e, 26, cluster & 0xFFFF)
    struct.pack_into("<I", e, 28, size)
    struct.pack_into("<H", e, 24, (2025 - 1980) << 9 | 3 << 5 | 14)  # 2025-03-14
    if deleted:
        e[0] = 0xE5
    return bytes(e)


def lfn_slots(long_name: str, name11: bytes, deleted=False):
    """LFN slots in on-disk order (last part first)."""
    chk = ref_checksum(name11)
    units = list(long_name.encode("utf-16-le"))
    chars = [units[i] | units[i + 1] << 8 for i in range(0, len(units), 2)]
    chars.append(0x0000)
    while len(chars) % 13:
        chars.append(0xFFFF)
    parts = [chars[i : i + 13] for i in range(0, len(chars), 13)]
    out = []
    for idx in range(len(parts), 0, -1):
        p = parts[idx - 1]
        s = bytearray(32)
        s[0] = idx | (0x40 if idx == len(parts) else 0)
        if deleted:
            s[0] = 0xE5
        s[11], s[13] = 0x0F, chk
        for i, c in enumerate(p[0:5]):
            struct.pack_into("<H", s, 1 + 2 * i, c)
        for i, c in enumerate(p[5:11]):
            struct.pack_into("<H", s, 14 + 2 * i, c)
        for i, c in enumerate(p[11:13]):
            struct.pack_into("<H", s, 28 + 2 * i, c)
        out.append(bytes(s))
    return out


class SyntheticImage:
    """Builds a sparse FAT32 image on disk and returns its path."""

    def __init__(self, path: str):
        self.path = path
        self.fh = open(path, "wb+")
        self.fh.truncate(TOTAL * BPS)
        self._boot()
        self.set_fat(0, 0x0FFFFFF8)
        self.set_fat(1, 0x0FFFFFFF)

    def _boot(self):
        b = bytearray(512)
        b[0:3] = b"\xeb\x58\x90"
        b[3:11] = b"MSDOS5.0"
        struct.pack_into("<HBHB", b, 11, BPS, SPC, RESERVED, NFATS)
        b[21] = 0xF8
        struct.pack_into("<I", b, 32, TOTAL)
        struct.pack_into("<I", b, 36, SPF)
        struct.pack_into("<I", b, 44, 2)
        struct.pack_into("<HH", b, 48, 1, 6)
        b[66] = 0x29
        b[71:82] = b"TESTVOL    "
        b[82:90] = b"FAT32   "
        b[510:512] = b"\x55\xaa"
        self.fh.seek(0)
        self.fh.write(b)

    def set_fat(self, cluster: int, value: int):
        for n in range(NFATS):
            self.fh.seek((RESERVED + n * SPF) * BPS + cluster * 4)
            self.fh.write(struct.pack("<I", value))

    def chain(self, clusters, end=0x0FFFFFFF):
        for a, b in zip(clusters, clusters[1:]):
            self.set_fat(a, b)
        self.set_fat(clusters[-1], end)

    def write_cluster(self, cluster: int, data: bytes, offset: int = 0):
        self.fh.seek((DATA_START + (cluster - 2) * SPC) * BPS + offset)
        self.fh.write(data)

    def write_dir(self, cluster: int, slots):
        self.write_cluster(cluster, b"".join(slots))

    def close(self):
        self.fh.close()


def build_scenario(path: str) -> None:
    img = SyntheticImage(path)
    # Root: cluster 2 -> 9 (overflows 16 slots). Sub dir "Documentos largos": cluster 3.
    img.chain([2, 9])
    img.chain([3])
    img.chain([4, 6])  # fragmented 2-cluster file
    img.chain([5])
    img.chain([7])  # deleted file keeps no FAT chain in real life; we leave it free below
    img.set_fat(7, 0)
    img.chain([8])  # pdf
    img.chain([10])  # jpg with wrong bytes
    n_docs = b"DOCUME~1   "
    n_leame = b"LEAME~1 TXT"
    n_del = b"DELETED TXT"
    n_pdf = b"INFORM~1PDF"
    n_jpg = b"FOTO    JPG"
    n_asm = b"OTROAR~1ASM"
    root = [short_entry(b"MYDISK     ", 0x08, 0, 0)]
    root += lfn_slots("Documentos largos", n_docs) + [short_entry(n_docs, 0x10, 3, 0)]
    root += lfn_slots("Léame largo nombre.txt", n_leame) + [short_entry(n_leame, 0x20, 4, 600)]
    root += lfn_slots("borrado.txt", n_del, deleted=True) + [short_entry(n_del, 0x20, 7, 5, deleted=True)]
    root += lfn_slots("informe de prueba.pdf", n_pdf) + [short_entry(n_pdf, 0x20, 8, 40)]
    root += [short_entry(n_jpg, 0x20, 10, 40)]
    root += lfn_slots("otro archivo con nombre largo.asm", n_asm) + [short_entry(n_asm, 0x20, 11, 10)]
    img.chain([11])
    # Split over the two root clusters: 16 slots in cluster 2, the rest in cluster 9.
    img.write_dir(2, root[:16])
    img.write_dir(9, root[16:])
    sub = [
        short_entry(b".          ", 0x10, 3, 0),
        short_entry(b"..         ", 0x10, 0, 0),
        short_entry(b"NOTES   TXT", 0x20, 5, 18),
    ]
    img.write_dir(3, sub)
    img.write_cluster(4, b"A" * 512)
    img.write_cluster(6, b"B" * 88)
    img.write_cluster(5, b"hello fat32 notes\n")
    img.write_cluster(8, b"%PDF-1.4\n%fake")
    img.write_cluster(10, b"NOT A JPEG HEADER....")
    img.write_cluster(11, b"mov ax, 1\n")
    img.close()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


@have_real
class RealImageBootSector(unittest.TestCase):
    def test_known_values(self):
        with fa.Fat32(REAL_IMG) as fs:
            b = fs.boot
            self.assertEqual(b.bytes_per_sector, 512)
            self.assertEqual(b.sectors_per_cluster, 1)
            self.assertEqual(b.reserved_sectors, 1160)
            self.assertEqual(b.num_fats, 2)
            self.assertEqual(b.sectors_per_fat, 7612)
            self.assertEqual(b.root_cluster, 2)
            self.assertEqual(b.fs_type.strip(), "FAT32")
            self.assertEqual(fs.root_sector, 16384)
            self.assertEqual(b.data_start_sector, 16384)

    def test_raw_hex_representation(self):
        with fa.Fat32(REAL_IMG) as fs:
            reserved = next(f for f in fs.boot.fields if f.name == "Reserved sectors")
            self.assertEqual(reserved.offset, 14)
            self.assertEqual(reserved.text, "88 04 -> 0488h = 1160d")

    def test_fat_copies_identical(self):
        with fa.Fat32(REAL_IMG) as fs:
            self.assertTrue(fs.fat_copies_identical)

    def test_known_file_sector(self):
        # Worked example in the lab guide: cluster 58 -> sector 16440.
        with fa.Fat32(REAL_IMG) as fs:
            self.assertEqual(fs.cluster_to_sector(58), 1160 + 2 * 7612 + (58 - 2) * 1)
            self.assertEqual(fs.cluster_to_sector(58), 16440)
            self.assertIn(b"Esto es un documento", fs.read_sector(16440))

    def test_root_chain_is_fragmented_and_all_lfn_valid(self):
        with fa.Fat32(REAL_IMG) as fs:
            walk = fs.walk()
            self.assertEqual(walk.root_chain.clusters, [2, 4190, 6, 490095])
            self.assertEqual(walk.root_chain.end, "EOC")
            self.assertFalse(walk.root_chain.contiguous)
            for e in walk.iter_live():
                if e.lfn:
                    self.assertTrue(e.lfn_checksum_ok, e.path)

    def test_signatures_on_real_files(self):
        with fa.Fat32(REAL_IMG) as fs:
            walk = fs.walk()
            for e in walk.iter_live():
                if e.extension in ("pdf", "jpg", "jpeg", "docx", "apk", "asm") and not e.is_dir:
                    sig = fs.check_signature(e)
                    self.assertEqual(sig["status"], "OK", e.path)


class LfnChecksum(unittest.TestCase):
    def test_known_vector_from_real_image(self):
        # LFN slot of "System Volume Information" stores 0x72 for 'SYSTEM~1   '.
        self.assertEqual(fa.lfn_checksum(b"SYSTEM~1   "), 0x72)

    def test_matches_reference_implementation(self):
        for name in (b"FOO     BAR", b"QUICKS~1APK", b"           ", b"\xe5ABC    TXT"):
            self.assertEqual(fa.lfn_checksum(name), ref_checksum(name))

    def test_requires_11_bytes(self):
        with self.assertRaises(ValueError):
            fa.lfn_checksum(b"SHORT")

    def test_short_name_decoding(self):
        self.assertEqual(fa.decode_short_name(b"QUICKS~1APK"), "QUICKS~1.APK")
        self.assertEqual(fa.decode_short_name(b"OTROS      "), "OTROS")
        self.assertEqual(fa.decode_short_name(b"README  TXT", 0x18), "readme.txt")
        self.assertEqual(fa.decode_short_name(b".          "), ".")


class ClusterMath(unittest.TestCase):
    def setUp(self):
        self.boot = fa.BootSector(512, 1, 1160, 2, 7612, 2, 990627, "FAT32", "X")

    def test_formula(self):
        self.assertEqual(fa.cluster_to_sector(self.boot, 2), 16384)
        self.assertEqual(fa.cluster_to_sector(self.boot, 58), 16440)
        self.assertEqual(fa.cluster_to_sector(self.boot, 4190), 20572)

    def test_spc_greater_than_one(self):
        self.boot.sectors_per_cluster = 8
        self.assertEqual(fa.cluster_to_sector(self.boot, 3), 16384 + 8)

    def test_invalid_cluster(self):
        with self.assertRaises(ValueError):
            fa.cluster_to_sector(self.boot, 1)

    def test_compute_runs(self):
        self.assertEqual(fa.compute_runs([5, 6, 7, 20, 21, 40]), [(5, 7), (20, 21), (40, 40)])
        self.assertEqual(fa.compute_runs([]), [])

    def test_cluster_high_low(self):
        slot = short_entry(b"CARPET~1   ", 0x10, 341518, 0)  # 0x0005360E
        self.assertEqual(struct.unpack_from("<HH", slot, 20)[0], 5)
        self.assertEqual(struct.unpack_from("<H", slot, 26)[0], 0x360E)


class NonFat32(unittest.TestCase):
    @have_iso
    def test_arqui_iso_rejected(self):
        with self.assertRaises(fa.NotFat32Error) as ctx:
            fa.Fat32(FAT16_ISO)
        self.assertIn("NO es FAT32", str(ctx.exception))

    @have_iso
    def test_cli_exit_code_on_iso(self):
        import contextlib
        import io

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = fa.main([FAT16_ISO])
        self.assertEqual(code, 2)
        self.assertIn("NO es FAT32", err.getvalue())

    def test_zero_image_rejected(self):
        with self.assertRaises(fa.NotFat32Error):
            fa.parse_boot_sector(bytes(512))

    def test_fat16_bpb_rejected(self):
        b = bytearray(512)
        struct.pack_into("<HBHB", b, 11, 512, 4, 1, 2)
        struct.pack_into("<H", b, 17, 512)  # root entries != 0 -> FAT12/16
        struct.pack_into("<H", b, 22, 200)
        b[510:512] = b"\x55\xaa"
        with self.assertRaises(fa.NotFat32Error):
            fa.parse_boot_sector(bytes(b))

    def test_missing_file_exit_code(self):
        self.assertEqual(fa.main(["/nonexistent/file.img"]), 1)


class SyntheticImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "synthetic.img")
        build_scenario(cls.path)
        cls.fs = fa.Fat32(cls.path)
        cls.walk = cls.fs.walk()

    @classmethod
    def tearDownClass(cls):
        cls.fs.close()
        cls.tmp.cleanup()

    def by_path(self, path):
        for e in self.walk.iter_live():
            if e.path == path:
                return e
        self.fail(f"{path} not found")

    def test_boot_geometry(self):
        b = self.fs.boot
        self.assertEqual((b.bytes_per_sector, b.sectors_per_cluster, b.reserved_sectors), (512, 1, 32))
        self.assertEqual(self.fs.root_sector, DATA_START)
        self.assertEqual(self.fs.cluster_to_sector(5), DATA_START + 3)

    def test_volume_label_and_root_chain(self):
        self.assertEqual(self.walk.volume_label.strip(), "MYDISK")
        self.assertEqual(self.walk.root_chain.clusters, [2, 9])
        self.assertEqual([s.slots for s in self.walk.root_stats], [16, 16])
        self.assertEqual(self.walk.root_stats[0].live + self.walk.root_stats[0].lfn
                         + self.walk.root_stats[0].deleted, 16)
        self.assertEqual(self.walk.root_stats[1].free, 15)  # only the last 8.3 slot spilled over

    def test_lfn_reconstruction(self):
        e = self.by_path("/Léame largo nombre.txt")
        self.assertEqual(e.short_name, "LEAME~1.TXT")
        self.assertEqual(e.lfn_slots, 2)
        self.assertTrue(e.lfn_checksum_ok)
        self.assertEqual(e.lfn_checksum_stored, ref_checksum(b"LEAME~1 TXT"))
        self.assertEqual(e.size, 600)

    def test_lfn_spanning_three_slots_across_clusters(self):
        e = self.by_path("/otro archivo con nombre largo.asm")
        self.assertEqual(e.lfn_slots, 3)
        self.assertTrue(e.lfn_checksum_ok)

    def test_subdirectory_and_dots(self):
        d = self.by_path("/Documentos largos")
        self.assertTrue(d.is_dir)
        names = [c.short_name for c in d.children]
        self.assertEqual(names, [".", "..", "NOTES.TXT"])
        dotdot = d.children[1]
        self.assertEqual(dotdot.first_cluster, 0)  # '..' to root is cluster 0
        self.assertEqual(self.by_path("/Documentos largos/NOTES.TXT").size, 18)
        # '.' and '..' are never yielded as files
        self.assertFalse(any(e.is_dot for e in self.walk.iter_live()))

    def test_deleted_entry_listed_separately(self):
        self.assertEqual(len(self.walk.deleted), 1)
        d = self.walk.deleted[0]
        self.assertTrue(d.deleted)
        self.assertEqual(d.lfn, "borrado.txt")
        self.assertTrue(d.lfn_checksum_ok)
        self.assertNotIn(d.path, [e.path for e in self.walk.iter_live()])
        self.assertEqual(self.walk.root_stats[0].deleted, 2)  # 1 LFN + 1 short

    def test_chain_fragmented(self):
        e = self.by_path("/Léame largo nombre.txt")
        info = self.fs.describe(e)
        self.assertEqual(info["chain_first"], [4, 6])
        self.assertFalse(info["contiguous"])
        self.assertEqual(info["chain_end"], "EOC")
        self.assertEqual(info["clusters_expected"], 2)
        self.assertTrue(info["chain_matches_size"])

    def test_signatures(self):
        pdf = self.fs.describe(self.by_path("/informe de prueba.pdf"))
        self.assertEqual(pdf["signature"]["status"], "OK")
        jpg = self.fs.describe(self.by_path("/FOTO.JPG"))
        self.assertEqual(jpg["signature"]["status"], "NO_COINCIDE")
        txt = self.fs.describe(self.by_path("/Documentos largos/NOTES.TXT"))
        self.assertEqual(txt["signature"]["status"], "OK")
        asm = self.fs.describe(self.by_path("/otro archivo con nombre largo.asm"))
        self.assertEqual(asm["signature"]["status"], "OK")

    def test_json_output(self):
        import json

        data = fa.build_json(self.fs, self.walk)
        json.dumps(data)  # must be serializable
        self.assertEqual(data["geometry"]["root_sector"], DATA_START)
        self.assertEqual(len(data["deleted"]), 1)

    def test_cli_runs(self):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fa.main([self.path, "--tree", "--find", "pdf", ".asm"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("Documentos largos", text)
        self.assertIn("ENTRADAS BORRADAS", text)
        self.assertIn("informe de prueba.pdf", text)


class ChainEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "edge.img")
        img = SyntheticImage(self.path)
        img.set_fat(20, 21)
        img.set_fat(21, 22)
        img.set_fat(22, 20)  # loop
        img.set_fat(30, 31)
        img.set_fat(31, 0x0FFFFFF7)  # bad cluster
        img.set_fat(40, 0x0FFFFFF8)  # EOC variants
        img.set_fat(41, 0x0FFFFFFF)
        img.set_fat(50, 51)  # 51 is free -> broken chain
        img.close()
        self.fs = fa.Fat32(self.path)

    def tearDown(self):
        self.fs.close()
        self.tmp.cleanup()

    def test_loop_protection(self):
        ch = self.fs.follow_chain(20)
        self.assertEqual(ch.clusters, [20, 21, 22])
        self.assertEqual(ch.end, "LOOP")

    def test_bad_cluster(self):
        ch = self.fs.follow_chain(30)
        self.assertEqual((ch.clusters, ch.end), ([30, 31], "BAD"))

    def test_end_of_chain_markers(self):
        self.assertEqual(self.fs.follow_chain(40).end, "EOC")
        self.assertEqual(self.fs.follow_chain(41).end, "EOC")

    def test_free_link(self):
        self.assertEqual(self.fs.follow_chain(50).end, "FREE")

    def test_out_of_range(self):
        self.assertEqual(self.fs.follow_chain(10**8).end, "OUT_OF_RANGE")


if __name__ == "__main__":
    unittest.main()

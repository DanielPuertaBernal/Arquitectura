#!/usr/bin/env python3
"""NTFS analyzer (stdlib only): locate files, folders and structures in an NTFS disk image.

Usage:
    python3 ntfs_analyzer.py IMAGE [--tree] [--record N] [--path /a/b.txt] [--deleted] [--json out.json]

The tool never mounts anything: it reads raw sectors, so every number it prints can be
verified with a hex editor. User-facing output is in Spanish; code is in English.
"""
import argparse
import datetime
import json
import struct
import sys

SECTOR = 512
ATTR_STD_INFO = 0x10
ATTR_ATTR_LIST = 0x20
ATTR_FILE_NAME = 0x30
ATTR_DATA = 0x80
ATTR_INDEX_ROOT = 0x90
ATTR_INDEX_ALLOC = 0xA0
ATTR_BITMAP = 0xB0
ATTR_NAMES = {
    0x10: "$STANDARD_INFORMATION", 0x20: "$ATTRIBUTE_LIST", 0x30: "$FILE_NAME",
    0x40: "$OBJECT_ID", 0x50: "$SECURITY_DESCRIPTOR", 0x60: "$VOLUME_NAME",
    0x70: "$VOLUME_INFORMATION", 0x80: "$DATA", 0x90: "$INDEX_ROOT",
    0xA0: "$INDEX_ALLOCATION", 0xB0: "$BITMAP", 0xC0: "$REPARSE_POINT",
    0x100: "$LOGGED_UTILITY_STREAM",
}
ROOT_RECORD = 5
NS_NAMES = {0: "POSIX", 1: "Win32", 2: "DOS", 3: "Win32&DOS"}


class NtfsError(Exception):
    pass


# ---------------------------------------------------------------- pure helpers
def decode_runs(data):
    """Decode an NTFS data-run list into [(lcn_or_None, length_in_clusters)].

    Header byte: low nibble = bytes of the length field, high nibble = bytes of the
    (signed, relative to the previous run) LCN offset. An offset size of 0 = sparse run.
    """
    runs, pos, lcn = [], 0, 0
    while pos < len(data) and data[pos] != 0:
        header = data[pos]
        len_size, off_size = header & 0x0F, header >> 4
        pos += 1
        if len_size == 0 or pos + len_size + off_size > len(data):
            raise NtfsError("data run corrupto")
        length = int.from_bytes(data[pos:pos + len_size], "little")
        pos += len_size
        if off_size == 0:
            runs.append((None, length))
        else:
            delta = int.from_bytes(data[pos:pos + off_size], "little", signed=True)
            lcn += delta
            runs.append((lcn, length))
        pos += off_size
    return runs


def apply_fixups(buf, stride=SECTOR):
    """Apply the Update Sequence Array. Returns (fixed_bytes, ok, usn, saved_values)."""
    uso, usc = struct.unpack_from("<HH", buf, 4)
    if usc < 1 or uso + usc * 2 > len(buf):
        raise NtfsError("USA invalida")
    usn = buf[uso:uso + 2]
    saved = [buf[uso + 2 * i:uso + 2 * i + 2] for i in range(1, usc)]
    out, ok = bytearray(buf), True
    for i, sv in enumerate(saved, start=1):
        end = i * stride
        if end > len(out):
            break
        if out[end - 2:end] != usn:
            ok = False
        out[end - 2:end] = sv
    return bytes(out), ok, usn, saved


def filetime(value):
    if value == 0:
        return "-"
    try:
        dt = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=value // 10)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except OverflowError:
        return "fuera de rango"


def le_hex(raw):
    """'88 04 -> 0488h = 1160d' style rendering of a little-endian field."""
    value = int.from_bytes(raw, "little")
    spaced = " ".join(f"{b:02X}" for b in raw)
    return f"{spaced} -> {value:0{len(raw) * 2}X}h = {value}d"


def parse_file_name(buf):
    parent = int.from_bytes(buf[0:6], "little")
    parent_seq = int.from_bytes(buf[6:8], "little")
    ctime, mtime, _, atime = struct.unpack_from("<QQQQ", buf, 8)
    alloc, real, flags = struct.unpack_from("<QQI", buf, 0x28)
    nlen, ns = buf[0x40], buf[0x41]
    name = buf[0x42:0x42 + nlen * 2].decode("utf-16-le", "replace")
    return {"parent": parent, "parent_seq": parent_seq, "ctime": ctime, "mtime": mtime,
            "atime": atime, "alloc": alloc, "size": real, "flags": flags,
            "namespace": ns, "name": name}


def best_name(names):
    """Prefer Win32/Win32&DOS/POSIX over the DOS 8.3 alias."""
    for ns in (1, 3, 0, 2):
        for n in names:
            if n["namespace"] == ns:
                return n
    return None


# ---------------------------------------------------------------- records
class Attribute:
    def __init__(self, buf, offset):
        self.offset = offset
        self.type, self.length = struct.unpack_from("<II", buf, offset)
        self.non_resident = buf[offset + 8]
        name_len, name_off = buf[offset + 9], struct.unpack_from("<H", buf, offset + 10)[0]
        self.flags, self.attr_id = struct.unpack_from("<HH", buf, offset + 12)
        self.name = buf[offset + name_off:offset + name_off + name_len * 2].decode("utf-16-le")
        self.runs, self.content = [], b""
        if not self.non_resident:
            size, coff = struct.unpack_from("<IH", buf, offset + 0x10)
            self.content_offset = coff
            self.content = buf[offset + coff:offset + coff + size]
            self.real_size = self.init_size = self.alloc_size = size
        else:
            self.start_vcn, self.end_vcn, roff = struct.unpack_from("<QQH", buf, offset + 0x10)
            self.alloc_size, self.real_size, self.init_size = struct.unpack_from("<QQQ", buf, offset + 0x28)
            self.run_offset = roff
            self.runs = decode_runs(buf[offset + roff:offset + self.length])

    @property
    def type_name(self):
        return ATTR_NAMES.get(self.type, f"0x{self.type:X}")


class Record:
    def __init__(self, vol, number, raw, abs_offset):
        self.vol, self.number, self.abs_offset = vol, number, abs_offset
        self.raw = raw
        if raw[0:4] != b"FILE":
            self.valid = False
            self.in_use = self.is_dir = False
            self.attrs, self.names = [], []
            return
        self.valid = True
        self.buf, self.fixup_ok, self.usn, self.saved = apply_fixups(raw)
        b = self.buf
        self.uso, self.usc = struct.unpack_from("<HH", b, 4)
        self.lsn = struct.unpack_from("<Q", b, 8)[0]
        self.seq, self.links, self.first_attr, self.flags = struct.unpack_from("<HHHH", b, 0x10)
        self.used, self.alloc = struct.unpack_from("<II", b, 0x18)
        self.base_ref = int.from_bytes(b[0x20:0x26], "little")
        self.in_use, self.is_dir = bool(self.flags & 1), bool(self.flags & 2)
        self.attrs = []
        pos = self.first_attr
        while pos + 8 <= len(b):
            atype = struct.unpack_from("<I", b, pos)[0]
            if atype == 0xFFFFFFFF:
                break
            a = Attribute(b, pos)
            if a.length == 0:
                break
            self.attrs.append(a)
            pos += a.length
        self.names = [parse_file_name(a.content) for a in self.attrs if a.type == ATTR_FILE_NAME]

    def attr(self, atype, name=""):
        for a in self.attrs:
            if a.type == atype and a.name == name:
                return a
        return None

    @property
    def streams(self):
        return [a for a in self.attrs if a.type == ATTR_DATA]

    @property
    def name(self):
        n = best_name(self.names)
        return n["name"] if n else None

    @property
    def sector(self):
        return self.abs_offset // SECTOR


# ---------------------------------------------------------------- volume
class Volume:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        self.part_start, self.mbr_info = self._find_partition()
        self._parse_boot()
        self._load_mft_runs()
        self._cache = {}

    def close(self):
        self.f.close()

    # -- low level
    def read(self, offset, n):
        self.f.seek(offset)
        return self.f.read(n)

    def _find_partition(self):
        mbr = self.read(0, SECTOR)
        if mbr[3:11] == b"NTFS    ":  # bare volume image
            return 0, None
        if mbr[510:512] != b"\x55\xaa":
            raise NtfsError("ni volumen NTFS ni MBR valido")
        for i in range(4):
            e = mbr[0x1BE + 16 * i:0x1BE + 16 * (i + 1)]
            ptype = e[4]
            start, count = struct.unpack_from("<II", e, 8)
            if ptype == 0x07 and self.read(start * SECTOR + 3, 8) == b"NTFS    ":
                return start, {"index": i, "entry_offset": 0x1BE + 16 * i, "raw": e,
                               "type": ptype, "start": start, "count": count,
                               "boot": e[0]}
        raise NtfsError("no se encontro particion NTFS")

    def _parse_boot(self):
        raw = self.read(self.part_start * SECTOR, SECTOR)
        self.boot_raw = raw
        if raw[3:11] != b"NTFS    ":
            raise NtfsError("OEM ID 'NTFS' no encontrado")
        self.bytes_per_sector = struct.unpack_from("<H", raw, 0x0B)[0]
        self.sectors_per_cluster = raw[0x0D]
        self.total_sectors = struct.unpack_from("<Q", raw, 0x28)[0]
        self.mft_lcn = struct.unpack_from("<Q", raw, 0x30)[0]
        self.mftmirr_lcn = struct.unpack_from("<Q", raw, 0x38)[0]
        cpr = struct.unpack_from("<b", raw, 0x40)[0]
        cluster = self.bytes_per_sector * self.sectors_per_cluster
        self.cluster_size = cluster
        self.record_size = (2 ** -cpr) if cpr < 0 else cpr * cluster
        ipb = struct.unpack_from("<b", raw, 0x44)[0]
        self.index_block_size = (2 ** -ipb) if ipb < 0 else ipb * cluster
        self.clusters_per_record_raw, self.clusters_per_index_raw = cpr, ipb
        self.serial = struct.unpack_from("<Q", raw, 0x48)[0]
        self.boot_signature = raw[0x1FE:0x200]

    def boot_fields(self):
        """Table of (name, offset, raw_bytes, rendering)."""
        r = self.boot_raw
        def f(name, off, size, extra=""):
            return (name, off, r[off:off + size], le_hex(r[off:off + size]) + extra)
        cpr = self.clusters_per_record_raw
        return [
            ("OEM ID", 0x03, r[3:11], "'" + r[3:11].decode() + "'"),
            f("Bytes por sector", 0x0B, 2),
            f("Sectores por cluster", 0x0D, 1),
            f("Total de sectores", 0x28, 8),
            f("Cluster inicial de $MFT (LCN)", 0x30, 8),
            f("Cluster inicial de $MFTMirr (LCN)", 0x38, 8),
            ("Clusters por registro MFT", 0x40, r[0x40:0x41],
             f"{r[0x40]:02X} -> {cpr}d con signo -> 2^{-cpr} = {self.record_size} bytes" if cpr < 0
             else f"{r[0x40]:02X} -> {cpr} clusters"),
            ("Clusters por bloque de indice", 0x44, r[0x44:0x45],
             f"{r[0x44]:02X} -> {self.clusters_per_index_raw}d -> {self.index_block_size} bytes"
             if self.clusters_per_index_raw < 0 else f"{r[0x44]:02X} -> {self.index_block_size} bytes"),
            f("Numero de serie del volumen", 0x48, 8),
            ("Firma del sector de arranque", 0x1FE, r[0x1FE:0x200],
             " ".join(f"{b:02X}" for b in r[0x1FE:0x200]) + (" (OK)" if r[0x1FE:0x200] == b"\x55\xaa" else " (INVALIDA)")),
        ]

    # -- addressing
    def lcn_to_sector(self, lcn):
        return self.part_start + lcn * self.sectors_per_cluster

    def lcn_to_offset(self, lcn):
        return self.lcn_to_sector(lcn) * SECTOR

    @property
    def mft_sector(self):
        return self.lcn_to_sector(self.mft_lcn)

    def _load_mft_runs(self):
        raw = self.read(self.mft_sector * SECTOR, self.record_size)
        rec = Record(self, 0, raw, self.mft_sector * SECTOR)
        if not rec.valid or not rec.fixup_ok:
            raise NtfsError("registro $MFT (0) invalido")
        data = rec.attr(ATTR_DATA)
        self.mft_record0 = rec
        self.mft_runs = data.runs
        self.mft_size = data.real_size
        self.mft_contiguous = len(self.mft_runs) == 1
        self.record_count = self.mft_size // self.record_size

    def record_offset(self, n):
        """Absolute byte offset of record n, mapped through $MFT's own data runs."""
        pos = n * self.record_size
        for lcn, length in self.mft_runs:
            span = length * self.cluster_size
            if pos < span:
                if lcn is None:
                    raise NtfsError("registro en zona dispersa")
                return self.lcn_to_offset(lcn) + pos
            pos -= span
        raise NtfsError(f"registro {n} fuera del $MFT")

    def naive_record_sector(self, n):
        return self.mft_sector + n * (self.record_size // SECTOR)

    def record(self, n):
        if n not in self._cache:
            off = self.record_offset(n)
            self._cache[n] = Record(self, n, self.read(off, self.record_size), off)
        return self._cache[n]

    # -- data
    def read_attr(self, attr, limit=None):
        """Content of a $DATA-like attribute (resident or via data runs)."""
        size = attr.real_size if limit is None else min(limit, attr.real_size)
        if not attr.non_resident:
            return attr.content[:size]
        out = bytearray()
        for lcn, length in attr.runs:
            if len(out) >= size:
                break
            n = length * self.cluster_size
            if lcn is None:
                out += b"\0" * n
            else:
                out += self.read(self.lcn_to_offset(lcn), min(n, size - len(out)))
        return bytes(out[:size])

    def read_file(self, path_or_record, stream=""):
        rec = self.record(path_or_record) if isinstance(path_or_record, int) else self.resolve(path_or_record)[0]
        a = rec.attr(ATTR_DATA, stream)
        if a is None:
            raise NtfsError("sin atributo $DATA")
        return self.read_attr(a)

    # -- directories
    def list_dir(self, rec):
        """Entries of a directory's $I30 index (INDEX_ROOT + INDX blocks)."""
        entries, seen = [], set()
        root = rec.attr(ATTR_INDEX_ROOT, "$I30")
        if root is None:
            return entries
        c = root.content
        block_size = struct.unpack_from("<I", c, 8)[0]
        flags = struct.unpack_from("<I", c, 0x1C)[0]
        self_large = bool(flags & 1)

        def parse(buf, start, end, where):
            pos = start
            while pos + 16 <= end:
                ref = int.from_bytes(buf[pos:pos + 6], "little")
                seq = struct.unpack_from("<H", buf, pos + 6)[0]
                elen, klen, eflags = struct.unpack_from("<HHH", buf, pos + 8)
                if elen == 0:
                    break
                if klen and not (eflags & 2):
                    fn = parse_file_name(buf[pos + 16:pos + 16 + klen])
                    key = (ref, fn["name"], fn["namespace"])
                    if key not in seen:
                        seen.add(key)
                        entries.append({"ref": ref, "seq": seq, "where": where, **fn})
                if eflags & 2:
                    break
                pos += elen

        eoff, esize = struct.unpack_from("<II", c, 0x10)
        parse(c, 0x10 + eoff, 0x10 + esize, "INDEX_ROOT")
        alloc = rec.attr(ATTR_INDEX_ALLOC, "$I30")
        if self_large and alloc is not None:
            data = self.read_attr(alloc)
            unit = self.cluster_size if block_size >= self.cluster_size else SECTOR
            for i in range(0, len(data), block_size):
                blk = data[i:i + block_size]
                if blk[0:4] != b"INDX":
                    continue
                fixed, ok, _, _ = apply_fixups(blk)
                vcn = struct.unpack_from("<Q", fixed, 0x10)[0]
                noff, nsize = struct.unpack_from("<II", fixed, 0x18)
                where = {"block": "INDX", "vcn": vcn, "sector": self._vcn_sector(alloc, i // unit), "fixup_ok": ok}
                parse(fixed, 0x18 + noff, 0x18 + nsize, where)
        return entries

    def _vcn_sector(self, attr, vcn_clusters):
        pos = vcn_clusters
        for lcn, length in attr.runs:
            if pos < length:
                return self.lcn_to_sector(lcn) + (pos * self.cluster_size) // SECTOR
            pos -= length
        return None

    @staticmethod
    def _visible(entries):
        return [e for e in entries if e["namespace"] != 2]

    def resolve(self, path):
        """Walk a path from the root. Returns (record, steps). ':stream' suffix is ignored here."""
        steps, rec = [], self.record(ROOT_RECORD)
        steps.append({"name": "/ (raiz)", "record": ROOT_RECORD, "sector": rec.sector,
                      "offset": rec.abs_offset, "found_in": "-", "seq": rec.seq})
        parts = [p for p in path.split("/") if p]
        if parts and ":" in parts[-1]:
            parts[-1] = parts[-1].split(":", 1)[0]
        for part in parts:
            entries = self._visible(self.list_dir(rec))
            match = next((e for e in entries if e["name"] == part), None) or \
                next((e for e in entries if e["name"].lower() == part.lower()), None)
            if match is None:
                raise NtfsError(f"no se encontro '{part}' en el registro {rec.number}")
            rec = self.record(match["ref"])
            steps.append({"name": part, "record": rec.number, "sector": rec.sector,
                          "offset": rec.abs_offset, "found_in": match["where"], "seq": match["seq"],
                          "parent_record": steps[-1]["record"]})
        return rec, steps

    def tree(self, rec=None, name="/", depth=0):
        rec = rec or self.record(ROOT_RECORD)
        node = {"name": name, "record": rec.number, "seq": rec.seq, "is_dir": rec.is_dir,
                "size": next((a.real_size for a in rec.streams if a.name == ""), 0),
                "streams": [{"name": a.name, "size": a.real_size, "resident": not a.non_resident}
                            for a in rec.streams if a.name], "children": []}
        if rec.is_dir and depth < 32:
            entries = sorted(self._visible(self.list_dir(rec)), key=lambda e: e["name"].lower())
            for e in entries:
                if e["ref"] == rec.number or e["ref"] < 16 and rec.number == ROOT_RECORD:
                    continue  # '.' and system files hidden in the root
                node["children"].append(self.tree(self.record(e["ref"]), e["name"], depth + 1))
        return node

    def deleted(self):
        """Scan the whole $MFT for FILE records with the in-use flag cleared."""
        out = []
        for n in range(self.record_count):
            try:
                rec = self.record(n)
            except NtfsError:
                continue
            data = rec.attr(ATTR_DATA) if rec.valid else None
            if rec.valid and not rec.in_use and (rec.names or (data and data.real_size > 0)):
                # Some drivers (Linux ntfs3) strip $FILE_NAME on delete: then only $DATA survives.
                nm = best_name(rec.names) or {"name": f"(sin $FILE_NAME) registro-{n}", "parent": None}
                out.append({"record": n, "seq": rec.seq, "flags": rec.flags, "name": nm["name"],
                            "parent": nm["parent"], "has_name": bool(rec.names), "size": data.real_size if data else 0,
                            "resident": bool(data and not data.non_resident),
                            "runs": data.runs if data else [], "is_dir": rec.is_dir,
                            "sector": rec.sector, "path": self.parent_path(nm) if rec.names else nm["name"],
                            "preview": self.read_attr(data, 64) if data else b""})
        return out

    def parent_path(self, nm):
        parts, ref, guard = [nm["name"]], nm["parent"], 0
        while ref != ROOT_RECORD and guard < 32:
            try:
                p = self.record(ref)
            except NtfsError:
                parts.append("?")
                break
            pn = best_name(p.names)
            if pn is None:
                parts.append("?")
                break
            parts.append(pn["name"])
            ref, guard = pn["parent"], guard + 1
        return "/" + "/".join(reversed(parts))


# ---------------------------------------------------------------- reports (Spanish)
def hexdump(data, base=0, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hx = " ".join(f"{b:02X}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {base + i:010X}  {hx:<{width * 3}} {asc}")
    return "\n".join(lines)


SIGNATURES = [(b"\xff\xd8\xff", "JPEG"), (b"%PDF-", "PDF"), (b"\x89PNG\r\n\x1a\n", "PNG"),
              (b"MZ", "Ejecutable Windows (PE/MZ)"), (b"\x7fELF", "ELF"), (b"PK\x03\x04", "ZIP/DOCX"),
              (b"SQLite format 3\0", "SQLite 3")]


def signature_of(data):
    for sig, name in SIGNATURES:
        if data.startswith(sig):
            return name
    return None


def runs_report(vol, runs, indent="    "):
    lines = []
    vcn = 0
    for lcn, length in runs:
        if lcn is None:
            lines.append(f"{indent}VCN {vcn}-{vcn + length - 1}: dispersa (sparse), {length} clusteres")
        else:
            s = vol.lcn_to_sector(lcn)
            lines.append(f"{indent}VCN {vcn}-{vcn + length - 1}: LCN {lcn} longitud {length} clusteres -> "
                         f"sectores absolutos {s}-{s + length * vol.sectors_per_cluster - 1} "
                         f"(byte 0x{s * SECTOR:X})")
        vcn += length
    return lines


def report_boot(vol):
    out = ["== MBR y particion =="]
    if vol.mbr_info:
        m = vol.mbr_info
        out.append(f"  Entrada de particion #{m['index']} en offset 0x{m['entry_offset']:X}: "
                   + " ".join(f"{b:02X}" for b in m["raw"]))
        out.append(f"  Tipo 0x{m['type']:02X} (NTFS/HPFS/exFAT); LBA inicio: {le_hex(m['raw'][8:12])}")
        out.append(f"  Sectores de la particion: {le_hex(m['raw'][12:16])}")
    else:
        out.append("  Imagen de volumen sin MBR (particion en el sector 0)")
    out.append(f"  Inicio de particion = sector {vol.part_start} (byte {vol.part_start * SECTOR})")
    out.append("")
    out.append("== Boot Sector NTFS ==")
    for name, off, _, text in vol.boot_fields():
        out.append(f"  0x{off:03X}  {name}: {text}")
    out.append("")
    out.append("== Formulas ==")
    out.append(f"  Tamano de cluster = {vol.bytes_per_sector} x {vol.sectors_per_cluster} = {vol.cluster_size} bytes")
    out.append(f"  Sector del $MFT = inicio_particion + LCN x SPC = {vol.part_start} + {vol.mft_lcn} x "
               f"{vol.sectors_per_cluster} = {vol.mft_sector}")
    out.append(f"  Sector de $MFTMirr = {vol.part_start} + {vol.mftmirr_lcn} x {vol.sectors_per_cluster} = "
               f"{vol.lcn_to_sector(vol.mftmirr_lcn)}")
    out.append(f"  Sector del registro N = sector_MFT + N x ({vol.record_size}/512) = "
               f"{vol.mft_sector} + N x {vol.record_size // SECTOR}")
    out.append(f"  $MFT: {vol.mft_size} bytes = {vol.record_count} registros; "
               + ("contiguo (1 data run), la formula directa es exacta" if vol.mft_contiguous
                  else f"FRAGMENTADO en {len(vol.mft_runs)} runs: se mapea por los data runs de $MFT"))
    out += runs_report(vol, vol.mft_runs, "  ")
    return "\n".join(out)


def report_record(vol, n):
    rec = vol.record(n)
    out = [f"== Registro MFT {n} =="]
    naive = vol.naive_record_sector(n)
    out.append(f"  Sector absoluto: {rec.sector} (offset 0x{rec.abs_offset:X}); formula directa: {naive} "
               + ("(coincide)" if naive == rec.sector else "(NO coincide: $MFT fragmentado)"))
    if not rec.valid:
        out.append(f"  Firma: {rec.raw[:4]!r} (no es 'FILE')")
        return "\n".join(out)
    out.append(f"  Firma: 'FILE' (OK)   numero de secuencia: {rec.seq}   enlaces: {rec.links}")
    out.append(f"  Flags: 0x{rec.flags:04X} -> " + ("en uso" if rec.in_use else "BORRADO (no en uso)")
               + (", directorio" if rec.is_dir else ", archivo"))
    out.append(f"  Fixup: USA en offset 0x{rec.uso:X}, {rec.usc} entradas, USN={rec.usn.hex(' ').upper()}; "
               f"valores originales de los ultimos 2 bytes de cada sector: "
               + ", ".join(s.hex(' ').upper() for s in rec.saved)
               + ("; verificacion OK" if rec.fixup_ok else "; verificacion FALLIDA"))
    out.append(f"  Bytes usados/asignados: {rec.used}/{rec.alloc}; primer atributo en 0x{rec.first_attr:X}")
    for a in rec.attrs:
        nm = f" '{a.name}'" if a.name else ""
        kind = "no residente" if a.non_resident else "residente"
        out.append(f"  - Atributo 0x{a.type:02X} {a.type_name}{nm} @0x{a.offset:X} len {a.length} [{kind}]")
        if a.type == ATTR_STD_INFO:
            c, m, mm, ac = struct.unpack_from("<QQQQ", a.content, 0)
            out.append(f"      creado {filetime(c)}; modificado {filetime(m)}; acceso {filetime(ac)}")
        elif a.type == ATTR_FILE_NAME:
            fn = parse_file_name(a.content)
            out.append(f"      nombre '{fn['name']}' ({NS_NAMES.get(fn['namespace'])}); padre = registro {fn['parent']} "
                       f"(seq {fn['parent_seq']}); tamano {fn['size']}")
        elif a.type == ATTR_DATA or a.type in (ATTR_INDEX_ALLOC, ATTR_BITMAP):
            if a.non_resident:
                out.append(f"      tamano real {a.real_size}, asignado {a.alloc_size}, run list @0x{a.run_offset:X}")
                out += runs_report(vol, a.runs, "      ")
            else:
                out.append(f"      residente: {a.real_size} bytes dentro del registro (offset del contenido 0x{a.content_offset:X})")
        elif a.type == ATTR_INDEX_ROOT:
            ents = [e for e in vol.list_dir(rec) if e["where"] == "INDEX_ROOT"]
            flags = struct.unpack_from("<I", a.content, 0x1C)[0]
            out.append(f"      bloque de indice {struct.unpack_from('<I', a.content, 8)[0]} bytes; "
                       f"flag 0x{flags:02X} ({'grande: usa INDEX_ALLOCATION' if flags & 1 else 'pequeno: todo en INDEX_ROOT'}); "
                       f"{len(ents)} entradas en INDEX_ROOT")
    return "\n".join(out)


def report_path(vol, path):
    rec, steps = vol.resolve(path)
    stream = path.split("/")[-1].split(":", 1)[1] if ":" in path.split("/")[-1] else ""
    out = [f"== Recorrido de {path} =="]
    for i, s in enumerate(steps):
        where = f", encontrado en {s['found_in']}" if i else ""
        if isinstance(s["found_in"], dict):
            w = s["found_in"]
            where = f", entrada hallada en bloque INDX VCN {w['vcn']} (sector {w['sector']})"
        out.append(f"  [{i}] {s['name']}: registro {s['record']} (seq {s['seq']}), sector {s['sector']}, "
                   f"offset 0x{s['offset']:X}{where}")
    out.append("")
    out.append(report_record(vol, rec.number))
    a = rec.attr(ATTR_DATA, stream)
    if a is not None:
        data = vol.read_attr(a, 64)
        out.append("")
        out.append(f"== Primeros bytes del flujo $DATA{(':' + stream) if stream else ''} ==")
        if a.non_resident and a.runs and a.runs[0][0] is not None:
            base = vol.lcn_to_sector(a.runs[0][0]) * SECTOR
        else:
            base = rec.abs_offset + a.offset + a.content_offset if not a.non_resident else 0
        out.append(hexdump(data, base))
        sig = signature_of(data)
        if sig:
            out.append(f"  Firma: {sig} (OK)")
        else:
            txt = data.decode("ascii", "ignore")
            out.append("  Firma: sin firma binaria conocida; texto: " + repr(txt[:40]) if txt.isprintable() or "\n" in txt else "  Firma: desconocida")
    return "\n".join(out)


def print_tree(node, prefix="", last=True, root=True, lines=None):
    lines = [] if lines is None else lines
    if root:
        lines.append(f"/  [registro {node['record']}]")
    else:
        mark = "└── " if last else "├── "
        kind = "[DIR] " if node["is_dir"] else ""
        size = "" if node["is_dir"] else f"  {node['size']} B"
        lines.append(f"{prefix}{mark}{kind}{node['name']}  [reg {node['record']}]{size}")
    kids = node["children"]
    # keep the output readable: compress huge folders
    shown = kids if len(kids) <= 12 else kids[:3]
    for i, k in enumerate(shown):
        np = prefix if root else prefix + ("    " if last else "│   ")
        print_tree(k, np, i == len(shown) - 1 and len(shown) == len(kids), False, lines)
    if len(shown) != len(kids):
        np = prefix if root else prefix + ("    " if last else "│   ")
        lines.append(f"{np}└── ... ({len(kids) - len(shown)} entradas mas; total {len(kids)})")
    for s in node["streams"]:
        np = prefix if root else prefix + ("    " if last else "│   ")
        lines.append(f"{np}ADS ':{s['name']}' ({s['size']} B)")
    return lines


def report_deleted(vol):
    items = vol.deleted()
    out = ["== Registros borrados (flag 'en uso' = 0, firma FILE, con datos o $FILE_NAME) =="]
    if not items:
        out.append("  (ninguno)")
    for d in items:
        runs = "residente" if d["resident"] else (
            "runs " + ", ".join(f"(LCN {l}, {n})" for l, n in d["runs"]))
        out.append(f"  registro {d['record']} (seq {d['seq']}, flags 0x{d['flags']:04X}, sector {d['sector']}): "
                   f"{d['path']}  {d['size']} B  [{runs}]")
        if d["preview"]:
            out.append(f"      primeros bytes: {d['preview'][:48]!r}")
    return "\n".join(out)


def to_jsonable(o):
    if isinstance(o, bytes):
        return o.hex()
    raise TypeError(type(o))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analizador NTFS (laboratorio 2)")
    ap.add_argument("image")
    ap.add_argument("--tree", action="store_true", help="arbol de directorios desde el registro 5")
    ap.add_argument("--record", type=int, metavar="N", help="detalle del registro MFT N")
    ap.add_argument("--path", help="recorrido paso a paso de una ruta (ej. /Documentos/nota.txt)")
    ap.add_argument("--deleted", action="store_true", help="listar registros borrados")
    ap.add_argument("--json", metavar="FILE", help="volcar el resultado a JSON")
    args = ap.parse_args(argv)
    try:
        vol = Volume(args.image)
    except (NtfsError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    result = {"partition_start": vol.part_start, "bytes_per_sector": vol.bytes_per_sector,
              "sectors_per_cluster": vol.sectors_per_cluster, "cluster_size": vol.cluster_size,
              "total_sectors": vol.total_sectors, "mft_lcn": vol.mft_lcn, "mft_sector": vol.mft_sector,
              "mftmirr_lcn": vol.mftmirr_lcn, "record_size": vol.record_size,
              "index_block_size": vol.index_block_size, "serial": f"{vol.serial:016X}",
              "mft_runs": vol.mft_runs, "mft_contiguous": vol.mft_contiguous}
    try:
        if not (args.tree or args.record is not None or args.path or args.deleted):
            print(report_boot(vol))
        if args.tree:
            tree = vol.tree()
            result["tree"] = tree
            print("\n".join(print_tree(tree)))
        if args.record is not None:
            print(report_record(vol, args.record))
        if args.path:
            print(report_path(vol, args.path))
            rec, steps = vol.resolve(args.path)
            result["path"] = {"path": args.path, "steps": steps, "record": rec.number}
        if args.deleted:
            print(report_deleted(vol))
            result["deleted"] = vol.deleted()
        if args.json:
            with open(args.json, "w") as f:
                json.dump(result, f, indent=2, default=to_jsonable)
            print(f"JSON escrito en {args.json}")
    except NtfsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

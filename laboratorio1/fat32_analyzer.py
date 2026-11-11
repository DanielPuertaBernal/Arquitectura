#!/usr/bin/env python3
"""FAT32 image analyzer (stdlib only).

Reads a raw FAT32 image (no partition table: boot sector at byte 0) and prints:

* boot sector (BPB) fields with offset, raw little-endian bytes and decoded value,
* the Root Directory location formula,
* the cluster chain of the Root Directory and how many 32-byte slots each
  cluster holds (live / LFN / deleted / free),
* the full recursive tree with long file names (LFN) reconstructed,
* per file: attributes, start cluster, size, absolute sector, byte offset,
  FAT cluster chain and file-signature check,
* deleted entries (first byte 0xE5), listed separately.

Usage:
    python3 fat32_analyzer.py IMAGE [--tree] [--find EXT ...] [--json out.json]
"""

import argparse
import json
import struct
import sys
from array import array
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

DIR_ENTRY_SIZE = 32
EOC_MIN = 0x0FFFFFF8  # >= this value: end of chain
BAD_CLUSTER = 0x0FFFFFF7
FAT_MASK = 0x0FFFFFFF

ATTR_READ_ONLY = 0x01
ATTR_HIDDEN = 0x02
ATTR_SYSTEM = 0x04
ATTR_VOLUME_ID = 0x08
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20
ATTR_LFN = 0x0F

ATTR_NAMES = [
    (ATTR_READ_ONLY, "R"),
    (ATTR_HIDDEN, "H"),
    (ATTR_SYSTEM, "S"),
    (ATTR_VOLUME_ID, "V"),
    (ATTR_DIRECTORY, "D"),
    (ATTR_ARCHIVE, "A"),
]


class NotFat32Error(Exception):
    """Raised when the image is not a FAT32 volume."""


# --------------------------------------------------------------------------
# Boot sector
# --------------------------------------------------------------------------

# (name, offset, size, kind) ; kind: 'u' unsigned int, 's' ascii text, 'b' raw
BOOT_FIELDS = [
    ("Jump (JMP)", 0, 3, "b"),
    ("OEM Name", 3, 8, "s"),
    ("Bytes per sector", 11, 2, "u"),
    ("Sectors per cluster", 13, 1, "u"),
    ("Reserved sectors", 14, 2, "u"),
    ("Number of FATs", 16, 1, "u"),
    ("Root entries (FAT12/16, must be 0)", 17, 2, "u"),
    ("Total sectors 16", 19, 2, "u"),
    ("Media descriptor", 21, 1, "u"),
    ("Sectors per FAT (FAT12/16, must be 0)", 22, 2, "u"),
    ("Sectors per track", 24, 2, "u"),
    ("Number of heads", 26, 2, "u"),
    ("Hidden sectors", 28, 4, "u"),
    ("Total sectors 32", 32, 4, "u"),
    ("Sectors per FAT (FAT32)", 36, 4, "u"),
    ("Extended flags", 40, 2, "u"),
    ("FS version", 42, 2, "u"),
    ("Root cluster", 44, 4, "u"),
    ("FSInfo sector", 48, 2, "u"),
    ("Backup boot sector", 50, 2, "u"),
    ("Drive number", 64, 1, "u"),
    ("Boot signature (0x29)", 66, 1, "u"),
    ("Volume ID (serial)", 67, 4, "u"),
    ("Volume label", 71, 11, "s"),
    ("FS type string", 82, 8, "s"),
    ("Sector signature (55 AA)", 510, 2, "b"),
]


@dataclass
class BootField:
    name: str
    offset: int
    size: int
    raw_hex: str
    value: object
    text: str  # human readable "88 04 -> 0488h = 1160d"


@dataclass
class BootSector:
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    num_fats: int
    sectors_per_fat: int
    root_cluster: int
    total_sectors: int
    fs_type: str
    volume_label: str
    fields: List[BootField] = field(default_factory=list)

    @property
    def bytes_per_cluster(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def fat_start_sector(self) -> int:
        return self.reserved_sectors

    @property
    def data_start_sector(self) -> int:
        return self.reserved_sectors + self.num_fats * self.sectors_per_fat

    @property
    def total_clusters(self) -> int:
        return (self.total_sectors - self.data_start_sector) // self.sectors_per_cluster


def _format_field(name: str, raw: bytes, kind: str) -> Tuple[object, str]:
    hexs = " ".join(f"{b:02X}" for b in raw)
    if kind == "u":
        value = int.from_bytes(raw, "little")
        digits = len(raw) * 2
        return value, f"{hexs} -> {value:0{digits}X}h = {value}d"
    if kind == "s":
        value = raw.decode("cp437", errors="replace")
        return value, f"{hexs} -> '{value}'"
    return raw.hex(), f"{hexs}"


def parse_boot_sector(data: bytes, image_size: Optional[int] = None) -> BootSector:
    """Parse and validate a 512+ byte boot sector. Raises NotFat32Error."""
    if len(data) < 512:
        raise NotFat32Error("Boot sector incompleto (menos de 512 bytes).")
    if data[510:512] != b"\x55\xaa":
        raise NotFat32Error(
            "Firma 55 AA ausente en el offset 510: no es un sector de arranque valido."
        )
    bps = struct.unpack_from("<H", data, 11)[0]
    spc = data[13]
    reserved = struct.unpack_from("<H", data, 14)[0]
    nfats = data[16]
    root_entries = struct.unpack_from("<H", data, 17)[0]
    total16 = struct.unpack_from("<H", data, 19)[0]
    spf16 = struct.unpack_from("<H", data, 22)[0]
    total32 = struct.unpack_from("<I", data, 32)[0]
    spf32 = struct.unpack_from("<I", data, 36)[0]
    root_cluster = struct.unpack_from("<I", data, 44)[0]
    fs_type = data[82:90].decode("cp437", errors="replace")

    if bps not in (512, 1024, 2048, 4096) or spc == 0 or spc & (spc - 1):
        raise NotFat32Error(
            f"BPB invalido (bytes/sector={bps}, sectores/cluster={spc}): "
            "no parece un volumen FAT."
        )
    if root_entries != 0 or spf16 != 0 or spf32 == 0:
        if root_entries != 0 or spf16 != 0:
            fs16 = data[54:62].decode("cp437", errors="replace").strip()
            raise NotFat32Error(
                "La imagen NO es FAT32: es FAT12/FAT16 "
                f"(entradas de raiz={root_entries}, sectores/FAT16={spf16}, "
                f"cadena FS en offset 54='{fs16}'). FAT32 exige ambos en 0."
            )
        raise NotFat32Error("La imagen NO es FAT32: sectores/FAT32 = 0 en el offset 36.")
    total = total32 if total32 else total16
    data_start = reserved + nfats * spf32
    if total <= data_start or nfats == 0:
        raise NotFat32Error("BPB inconsistente: el area de datos no existe.")
    clusters = (total - data_start) // spc
    if clusters < 65525:
        raise NotFat32Error(
            f"La imagen NO es FAT32: solo tiene {clusters} clusters de datos (< 65525)."
        )
    if root_cluster < 2 or root_cluster >= clusters + 2:
        raise NotFat32Error(f"Cluster raiz invalido: {root_cluster}.")

    bs = BootSector(
        bytes_per_sector=bps,
        sectors_per_cluster=spc,
        reserved_sectors=reserved,
        num_fats=nfats,
        sectors_per_fat=spf32,
        root_cluster=root_cluster,
        total_sectors=total,
        fs_type=fs_type,
        volume_label=data[71:82].decode("cp437", errors="replace"),
    )
    for name, off, size, kind in BOOT_FIELDS:
        raw = data[off : off + size]
        value, text = _format_field(name, raw, kind)
        bs.fields.append(BootField(name, off, size, raw.hex(), value, text))
    return bs


# --------------------------------------------------------------------------
# Name helpers
# --------------------------------------------------------------------------


def lfn_checksum(short_name_11: bytes) -> int:
    """Checksum stored in every LFN slot, computed over the 11-byte 8.3 name."""
    if len(short_name_11) != 11:
        raise ValueError("El nombre corto debe tener exactamente 11 bytes")
    total = 0
    for byte in short_name_11:
        total = (((total & 1) << 7) + (total >> 1) + byte) & 0xFF
    return total


def decode_short_name(raw11: bytes, nt_flags: int = 0) -> str:
    """Decode an 8.3 name ('FOO     TXT' -> 'FOO.TXT')."""
    base = bytearray(raw11[:8])
    if base and base[0] == 0x05:  # 0x05 stands for a real 0xE5 first byte
        base[0] = 0xE5
    base_s = bytes(base).decode("cp437", errors="replace").rstrip(" ")
    ext_s = raw11[8:11].decode("cp437", errors="replace").rstrip(" ")
    if nt_flags & 0x08:
        base_s = base_s.lower()
    if nt_flags & 0x10:
        ext_s = ext_s.lower()
    return f"{base_s}.{ext_s}" if ext_s else base_s


def attr_string(attr: int) -> str:
    return "".join(ch for bit, ch in ATTR_NAMES if attr & bit) or "-"


def decode_fat_datetime(date: int, time: int) -> str:
    if date == 0:
        return "-"
    year, month, day = 1980 + (date >> 9), (date >> 5) & 0xF, date & 0x1F
    hour, minute, sec = time >> 11, (time >> 5) & 0x3F, (time & 0x1F) * 2
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}"


def _lfn_chars(slot: bytes) -> str:
    raw = slot[1:11] + slot[14:26] + slot[28:32]
    chars = []
    for i in range(0, 26, 2):
        code = raw[i] | (raw[i + 1] << 8)
        if code in (0x0000, 0xFFFF):
            break
        chars.append(code)
    return b"".join(c.to_bytes(2, "little") for c in chars).decode(
        "utf-16-le", errors="replace"
    )


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Entry:
    name: str  # long name if present, otherwise the short name
    short_name: str
    lfn: Optional[str]
    lfn_slots: int
    lfn_checksum_stored: Optional[int]
    lfn_checksum_computed: Optional[int]
    lfn_checksum_ok: Optional[bool]
    attr: int
    attr_str: str
    first_cluster: int
    size: int
    modified: str
    created: str
    deleted: bool
    is_dir: bool
    is_volume_label: bool
    path: str
    entry_offset: int  # absolute byte offset of the 32-byte entry in the image
    children: List["Entry"] = field(default_factory=list)
    info: Dict[str, object] = field(default_factory=dict)  # chain/signature, filled lazily

    @property
    def extension(self) -> str:
        if self.is_dir or "." not in self.name:
            return ""
        return self.name.rsplit(".", 1)[1].lower()

    @property
    def is_dot(self) -> bool:
        return self.short_name in (".", "..")


@dataclass
class ClusterStats:
    cluster: int
    sector: int
    slots: int = 0
    live: int = 0  # 8.3 entries not deleted (files, dirs, volume label, dots)
    lfn: int = 0  # live LFN slots
    deleted: int = 0  # deleted slots (short or LFN)
    free: int = 0  # slots whose first byte is 0x00


@dataclass
class Chain:
    clusters: List[int]
    end: str  # EOC | BAD | FREE | LOOP | OUT_OF_RANGE
    runs: List[Tuple[int, int]]

    @property
    def contiguous(self) -> bool:
        return len(self.runs) <= 1


# --------------------------------------------------------------------------
# FAT32 volume
# --------------------------------------------------------------------------


class Fat32:
    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "rb")
        try:
            self._fh.seek(0, 2)
            self.image_size = self._fh.tell()
            self._fh.seek(0)
            self.boot = parse_boot_sector(self._fh.read(512), self.image_size)
            self._load_fat()
        except Exception:
            self._fh.close()
            raise

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- geometry ---------------------------------------------------------

    def cluster_to_sector(self, cluster: int) -> int:
        return cluster_to_sector(self.boot, cluster)

    def sector_offset(self, sector: int) -> int:
        return sector * self.boot.bytes_per_sector

    @property
    def root_sector(self) -> int:
        return self.cluster_to_sector(self.boot.root_cluster)

    # -- raw reads --------------------------------------------------------

    def read_sector(self, sector: int, count: int = 1) -> bytes:
        self._fh.seek(sector * self.boot.bytes_per_sector)
        return self._fh.read(count * self.boot.bytes_per_sector)

    def read_cluster(self, cluster: int) -> bytes:
        return self.read_sector(
            self.cluster_to_sector(cluster), self.boot.sectors_per_cluster
        )

    def _load_fat(self) -> None:
        b = self.boot
        size = b.sectors_per_fat * b.bytes_per_sector
        raw = self.read_sector(b.fat_start_sector, b.sectors_per_fat)
        if len(raw) < size:
            raise NotFat32Error("La imagen esta truncada: la FAT no cabe en el archivo.")
        fat = array("I")
        fat.frombytes(raw[: size - size % 4])
        if sys.byteorder == "big":
            fat.byteswap()
        self.fat = fat
        self.fat_copies_identical: Optional[bool] = None
        if b.num_fats >= 2:
            raw2 = self.read_sector(b.fat_start_sector + b.sectors_per_fat, b.sectors_per_fat)
            self.fat_copies_identical = raw == raw2

    def fat_entry(self, cluster: int) -> int:
        if cluster < 0 or cluster >= len(self.fat):
            raise IndexError(f"Cluster {cluster} fuera de la FAT")
        return self.fat[cluster] & FAT_MASK

    # -- chains -----------------------------------------------------------

    def follow_chain(self, start: int, limit: Optional[int] = None) -> Chain:
        """Follow the FAT chain from `start` with loop protection."""
        max_cluster = self.boot.total_clusters + 1
        limit = limit if limit is not None else self.boot.total_clusters + 1
        seen = set()
        clusters: List[int] = []
        current = start
        end = "EOC"
        while True:
            if current < 2 or current > max_cluster or current >= len(self.fat):
                end = "OUT_OF_RANGE" if clusters or current != 0 else "FREE"
                break
            if current in seen or len(clusters) >= limit:
                end = "LOOP"
                break
            seen.add(current)
            clusters.append(current)
            nxt = self.fat_entry(current)
            if nxt >= EOC_MIN:
                end = "EOC"
                break
            if nxt == BAD_CLUSTER:
                end = "BAD"
                break
            if nxt == 0:
                end = "FREE"
                break
            current = nxt
        return Chain(clusters, end, compute_runs(clusters))

    # -- directories ------------------------------------------------------

    def read_directory(
        self, start_cluster: int, path: str
    ) -> Tuple[List[Entry], List[ClusterStats], Chain]:
        """Parse one directory. Returns (entries, per-cluster stats, chain).

        Deleted entries are included in `entries` with deleted=True.
        """
        chain = self.follow_chain(start_cluster)
        entries: List[Entry] = []
        stats: List[ClusterStats] = []
        pending_live: List[bytes] = []
        pending_del: List[bytes] = []
        ended = False
        bps_cluster = self.boot.bytes_per_cluster
        for cl in chain.clusters:
            data = self.read_cluster(cl)
            st = ClusterStats(cl, self.cluster_to_sector(cl))
            base_off = self.sector_offset(st.sector)
            for pos in range(0, min(len(data), bps_cluster), DIR_ENTRY_SIZE):
                slot = data[pos : pos + DIR_ENTRY_SIZE]
                if len(slot) < DIR_ENTRY_SIZE:
                    break
                st.slots += 1
                first = slot[0]
                attr = slot[11]
                if first == 0x00:
                    st.free += 1
                    ended = True
                    continue
                is_lfn = (attr & 0x3F) == ATTR_LFN
                deleted = first == 0xE5
                if deleted:
                    st.deleted += 1
                elif is_lfn:
                    st.lfn += 1
                else:
                    st.live += 1
                if ended:
                    continue  # garbage after the end marker is counted but not parsed
                if is_lfn:
                    (pending_del if deleted else pending_live).append(slot)
                    continue
                pend = pending_del if deleted else pending_live
                entries.append(
                    self._build_entry(slot, pend, deleted, path, base_off + pos)
                )
                pending_live, pending_del = [], []
            stats.append(st)
        return entries, stats, chain

    def _build_entry(
        self, slot: bytes, lfn_slots: List[bytes], deleted: bool, path: str, offset: int
    ) -> Entry:
        raw11 = slot[0:11]
        attr = slot[11]
        short = decode_short_name(raw11, slot[12])
        if deleted:
            short = "?" + short[1:]  # the first byte was overwritten by 0xE5
        hi = struct.unpack_from("<H", slot, 20)[0]
        lo = struct.unpack_from("<H", slot, 26)[0]
        size = struct.unpack_from("<I", slot, 28)[0]
        ctime, cdate = struct.unpack_from("<HH", slot, 14)
        mtime, mdate = struct.unpack_from("<HH", slot, 22)

        lfn = None
        stored = computed = ok = None
        if lfn_slots:
            # Slots are stored in reverse order (last part first).
            lfn = "".join(_lfn_chars(s) for s in reversed(lfn_slots))
            stored = lfn_slots[0][13]
            computed = lfn_checksum(raw11)
            checks = {s[13] for s in lfn_slots}
            ok = checks == {computed}
            if deleted and not ok:
                # First name byte was overwritten with 0xE5: try every candidate.
                tail = raw11[1:]
                ok = any(
                    lfn_checksum(bytes([c]) + tail) in checks and len(checks) == 1
                    for c in range(256)
                )
            if not deleted:
                # Ordinals must go N|0x40, N-1, ..., 1
                ords = [s[0] for s in lfn_slots]
                expected = list(range(len(ords), 0, -1))
                expected[0] |= 0x40
                if ords != expected:
                    ok = False
        name = lfn if lfn else short
        is_volume = bool(attr & ATTR_VOLUME_ID) and not attr & ATTR_DIRECTORY
        join = path.rstrip("/") + "/" + name if not is_volume else name
        return Entry(
            name=name,
            short_name=short,
            lfn=lfn,
            lfn_slots=len(lfn_slots),
            lfn_checksum_stored=stored,
            lfn_checksum_computed=computed,
            lfn_checksum_ok=ok,
            attr=attr,
            attr_str=attr_string(attr),
            first_cluster=(hi << 16) | lo,
            size=size,
            modified=decode_fat_datetime(mdate, mtime),
            created=decode_fat_datetime(cdate, ctime),
            deleted=deleted,
            is_dir=bool(attr & ATTR_DIRECTORY),
            is_volume_label=is_volume,
            path=join,
            entry_offset=offset,
        )

    # -- tree ---------------------------------------------------------------

    def walk(self) -> "Walk":
        """Read the whole tree starting at the root directory."""
        result = Walk()
        visited = set()
        root_entries, root_stats, root_chain = self.read_directory(self.boot.root_cluster, "")
        result.root_stats, result.root_chain = root_stats, root_chain
        visited.add(self.boot.root_cluster)
        result.root_entries = root_entries
        self._recurse(root_entries, visited, result)
        return result

    def _recurse(self, entries: List[Entry], visited: set, result: "Walk") -> None:
        for e in entries:
            if e.deleted:
                result.deleted.append(e)
                continue
            if e.is_volume_label:
                result.volume_label = e.short_name
                continue
            if not e.is_dir or e.is_dot:
                continue
            if e.first_cluster < 2 or e.first_cluster in visited:
                result.warnings.append(f"Directorio {e.path}: cluster {e.first_cluster} invalido o repetido")
                continue
            visited.add(e.first_cluster)
            kids, stats, chain = self.read_directory(e.first_cluster, e.path)
            e.children = kids
            e.info["dir_stats"] = [asdict(s) for s in stats]
            e.info["dir_chain_len"] = len(chain.clusters)
            self._recurse(kids, visited, result)

    # -- per entry details --------------------------------------------------

    def describe(self, e: Entry) -> Dict[str, object]:
        """Compute cluster/sector/offset/chain/signature info for an entry."""
        b = self.boot
        info: Dict[str, object] = {}
        cl = e.first_cluster
        info["first_cluster"] = cl
        info["cluster_high"] = cl >> 16
        info["cluster_low"] = cl & 0xFFFF
        if cl >= 2:
            sec = self.cluster_to_sector(cl)
            info["sector"] = sec
            info["byte_offset"] = sec * b.bytes_per_sector
            info["sector_formula"] = (
                f"{b.reserved_sectors} + ({b.num_fats}*{b.sectors_per_fat}) + "
                f"({cl}-2)*{b.sectors_per_cluster} = {sec}"
            )
        else:
            info["sector"] = None
            info["byte_offset"] = None
        info["entry_sector"] = e.entry_offset // b.bytes_per_sector
        info["entry_byte_offset"] = e.entry_offset
        if not e.deleted and cl >= 2:
            chain = self.follow_chain(cl)
            info["chain_len"] = len(chain.clusters)
            info["chain_first"] = chain.clusters[:8]
            info["chain_end"] = chain.end
            info["contiguous"] = chain.contiguous
            info["runs"] = [list(r) for r in chain.runs]
            if not e.is_dir:
                needed = -(-e.size // b.bytes_per_cluster) if e.size else 0
                info["clusters_expected"] = needed
                info["chain_matches_size"] = needed == len(chain.clusters)
        elif e.deleted:
            info["chain_len"] = None
            info["chain_note"] = "entrada borrada: la FAT ya liberó la cadena (datos posiblemente intactos)"
        if not e.is_dir and not e.is_volume_label and cl >= 2 and e.size > 0:
            info["signature"] = self.check_signature(e)
        return info

    def check_signature(self, e: Entry) -> Dict[str, object]:
        sector = self.cluster_to_sector(e.first_cluster)
        if sector * self.boot.bytes_per_sector >= self.image_size:
            return {"expected": "-", "found": "", "status": "FUERA_DE_IMAGEN"}
        head = self.read_sector(sector)
        return signature_check(e.extension, head[: min(len(head), e.size)])


@dataclass
class Walk:
    root_entries: List[Entry] = field(default_factory=list)
    root_stats: List[ClusterStats] = field(default_factory=list)
    root_chain: Optional[Chain] = None
    deleted: List[Entry] = field(default_factory=list)
    volume_label: str = ""
    warnings: List[str] = field(default_factory=list)

    def iter_live(self, entries: Optional[List[Entry]] = None):
        """Yield every live entry (not '.'/'..', not volume label) depth-first."""
        for e in self.root_entries if entries is None else entries:
            if e.deleted or e.is_volume_label or e.is_dot:
                continue
            yield e
            if e.is_dir:
                yield from self.iter_live(e.children)


# --------------------------------------------------------------------------
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------


def cluster_to_sector(boot: BootSector, cluster: int) -> int:
    """Absolute sector = Reserved + NFATs*SectorsPerFAT + (cluster-2)*SPC."""
    if cluster < 2:
        raise ValueError(f"Los clusters de datos empiezan en 2 (recibido {cluster})")
    return boot.data_start_sector + (cluster - 2) * boot.sectors_per_cluster


def compute_runs(clusters: List[int]) -> List[Tuple[int, int]]:
    """Collapse a cluster list into contiguous (first, last) runs."""
    runs: List[Tuple[int, int]] = []
    for c in clusters:
        if runs and runs[-1][1] + 1 == c:
            runs[-1] = (runs[-1][0], c)
        else:
            runs.append((c, c))
    return runs


SIGNATURES = {
    "pdf": (b"%PDF", "%PDF"),
    "jpg": (b"\xff\xd8\xff", "FF D8 FF"),
    "jpeg": (b"\xff\xd8\xff", "FF D8 FF"),
    "png": (b"\x89PNG", "89 50 4E 47"),
    "gif": (b"GIF8", "GIF8"),
    "docx": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "xlsx": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "pptx": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "zip": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "apk": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "jar": (b"PK\x03\x04", "50 4B 03 04 (PK)"),
    "exe": (b"MZ", "4D 5A (MZ)"),
    "dll": (b"MZ", "4D 5A (MZ)"),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "D0 CF 11 E0 A1 B1 1A E1"),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "D0 CF 11 E0 A1 B1 1A E1"),
    "ppt": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "D0 CF 11 E0 A1 B1 1A E1"),
}
TEXT_EXTENSIONS = {"asm", "txt", "c", "h", "inc", "s", "md", "bat", "py", "cpp", "java", "csv", "log", "xml"}


def signature_check(ext: str, head: bytes) -> Dict[str, object]:
    """Compare the first bytes of a file against the expected signature."""
    ext = ext.lower()
    found = " ".join(f"{b:02X}" for b in head[:8])
    if ext in SIGNATURES:
        magic, label = SIGNATURES[ext]
        return {
            "expected": label,
            "found": found,
            "status": "OK" if head.startswith(magic) else "NO_COINCIDE",
        }
    if ext in TEXT_EXTENSIONS:
        sample = head[:256]
        # Text: no control bytes other than TAB/LF/CR; high bytes are allowed
        # because ".asm"/".txt" files are often UTF-8 or ANSI (accents).
        printable = all(b in (9, 10, 13) or (b >= 32 and b != 127) for b in sample)
        return {
            "expected": "texto (ASCII/ANSI/UTF-8)",
            "found": found + " | " + sample[:24].decode("ascii", "replace").replace("\n", " ").replace("\r", " "),
            "status": "OK" if printable and sample else "NO_COINCIDE",
        }
    return {"expected": "-", "found": found, "status": "SIN_REGLA"}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _fmt_size(n: int) -> str:
    return f"{n} B"


def chain_text(info: Dict[str, object]) -> str:
    if info.get("chain_len") is None:
        return str(info.get("chain_note", "n/a"))
    first = " -> ".join(str(c) for c in info["chain_first"])  # type: ignore[union-attr]
    n = info["chain_len"]
    more = " -> ..." if n > len(info["chain_first"]) else ""  # type: ignore[arg-type]
    runs = info["runs"]
    cont = "contigua" if len(runs) <= 1 else f"fragmentada en {len(runs)} tramos"  # type: ignore[arg-type]
    return f"{first}{more} ({n} clusters, {cont}, fin={info['chain_end']})"


def print_boot(fs: Fat32, out=print) -> None:
    b = fs.boot
    out("=" * 78)
    out(f"IMAGEN: {fs.path}  ({fs.image_size} bytes, {fs.image_size / 1024 / 1024:.1f} MiB)")
    out("=" * 78)
    out("\n[1] SECTOR DE ARRANQUE (sector 0, byte 0) - bytes en little-endian")
    out(f"{'Offset':>8}  {'Tam':>3}  {'Campo':<40} Valor")
    for f in b.fields:
        out(f"{f.offset:>4} 0x{f.offset:03X}  {f.size:>3}  {f.name:<40} {f.text}")
    out(f"\nClusters de datos: {b.total_clusters}  |  Bytes por cluster: {b.bytes_per_cluster}")
    out(f"Inicio FAT1: sector {b.fat_start_sector} (byte {b.fat_start_sector * b.bytes_per_sector})")
    if b.num_fats >= 2:
        out(
            f"Inicio FAT2: sector {b.fat_start_sector + b.sectors_per_fat}  "
            f"(copias identicas: {'SI' if fs.fat_copies_identical else 'NO'})"
        )
    out(f"Inicio area de datos (cluster 2): sector {b.data_start_sector} (byte {b.data_start_sector * b.bytes_per_sector})")


def print_root(fs: Fat32, walk: Walk, out=print) -> None:
    b = fs.boot
    rc = b.root_cluster
    out("\n[2] UBICACION DEL DIRECTORIO RAIZ")
    out("Formula: RootSector = Reserved + NFATs*SectorsPerFAT + (RootCluster-2)*SPC")
    out(
        f"         RootSector = {b.reserved_sectors} + {b.num_fats}*{b.sectors_per_fat} + "
        f"({rc}-2)*{b.sectors_per_cluster} = {fs.root_sector}"
    )
    out(f"         Byte offset = {fs.root_sector} * {b.bytes_per_sector} = {fs.root_sector * b.bytes_per_sector} (0x{fs.root_sector * b.bytes_per_sector:X})")

    chain = walk.root_chain
    slots_per_cluster = b.bytes_per_cluster // DIR_ENTRY_SIZE
    out("\n[3] CADENA DEL DIRECTORIO RAIZ (por que no se ven todas las entradas)")
    out(
        f"Un cluster = {b.bytes_per_cluster} bytes = {slots_per_cluster} entradas de {DIR_ENTRY_SIZE} bytes. "
        "Cada nombre largo consume 1 + ceil(len/13) ranuras."
    )
    if chain is not None:
        runs = ", ".join(f"{a}-{z}" if a != z else str(a) for a, z in chain.runs)
        out(f"Cadena en la FAT: {len(chain.clusters)} clusters, fin={chain.end}, tramos: {runs}")
    out(f"{'Cluster':>8} {'Sector':>8} {'Offset':>10} {'Ranuras':>8} {'Vivas':>6} {'LFN':>5} {'Borr.':>6} {'Libres':>7}  FAT[cluster]")
    tot = [0, 0, 0, 0, 0]
    for s in walk.root_stats:
        nxt = fs.fat_entry(s.cluster)
        nxt_s = "EOC" if nxt >= EOC_MIN else f"-> {nxt}"
        out(
            f"{s.cluster:>8} {s.sector:>8} {s.sector * b.bytes_per_sector:>10} {s.slots:>8} "
            f"{s.live:>6} {s.lfn:>5} {s.deleted:>6} {s.free:>7}  {nxt_s}"
        )
        for i, v in enumerate((s.slots, s.live, s.lfn, s.deleted, s.free)):
            tot[i] += v
    out(f"{'TOTAL':>8} {'':>8} {'':>10} {tot[0]:>8} {tot[1]:>6} {tot[2]:>5} {tot[3]:>6} {tot[4]:>7}")
    visible = sum(1 for e in walk.root_entries if not e.deleted and not e.is_volume_label)
    out(
        f"Entradas 8.3 visibles en la raiz: {visible}; ranuras LFN vivas: {tot[2]}; "
        f"ranuras borradas: {tot[3]}."
    )


def print_tree(fs: Fat32, walk: Walk, out=print) -> None:
    out("\n[4] ARBOL COMPLETO (nombre largo | 8.3 | attr | cluster | sector | offset | tamano | cadena | firma)")
    if walk.volume_label:
        out(f"[VOLUMEN] etiqueta: {walk.volume_label}")
    _print_children(fs, walk.root_entries, "", out)


def _print_children(fs: Fat32, entries: List[Entry], indent: str, out) -> None:
    for e in entries:
        if e.deleted or e.is_volume_label:
            continue
        info = fs.describe(e)
        if e.is_dot:
            out(f"{indent}{e.short_name:<12} [DIR] cluster={e.first_cluster}")
            continue
        sec = info.get("sector")
        off = info.get("byte_offset")
        sig = info.get("signature")
        sig_s = f" firma={sig['status']}" if isinstance(sig, dict) else ""  # type: ignore[index]
        tag = "[DIR] " if e.is_dir else ""
        short = f" ({e.short_name})" if e.lfn else ""
        out(
            f"{indent}{tag}{e.name}{short} attr={e.attr_str} cl={e.first_cluster} "
            f"sec={sec} off={off} size={e.size} | {chain_text(info)}{sig_s}"
        )
        if e.is_dir:
            _print_children(fs, e.children, indent + "    ", out)


def print_summary(walk: Walk, out=print) -> None:
    counts: Dict[str, int] = {}
    dirs = 0
    for e in walk.iter_live():
        if e.is_dir:
            dirs += 1
        else:
            counts[e.extension or "(sin ext)"] = counts.get(e.extension or "(sin ext)", 0) + 1
    out("\n[5] RESUMEN POR EXTENSION")
    out(f"Carpetas: {dirs}   Archivos: {sum(counts.values())}   Borradas: {len(walk.deleted)}")
    for ext in sorted(counts):
        out(f"  .{ext:<8} {counts[ext]}")
    for w in walk.warnings:
        out(f"  AVISO: {w}")


def print_deleted(fs: Fat32, walk: Walk, exts: Optional[List[str]] = None, out=print) -> None:
    out("\n[6] ENTRADAS BORRADAS (primer byte 0xE5)")
    shown = 0
    for e in walk.deleted:
        if e.is_dot or (exts and e.extension not in exts and not e.is_dir):
            continue
        shown += 1
        info = fs.describe(e)
        kind = "DIR" if e.is_dir else "ARCH"
        chk = "" if e.lfn_checksum_ok is None else f" lfn_chk={'OK' if e.lfn_checksum_ok else 'NO'}"
        sig = info.get("signature")
        sig_s = f" firma={sig['status']}" if isinstance(sig, dict) else ""  # type: ignore[index]
        out(
            f"  [{kind}] {e.path}{" (8.3 " + e.short_name + ")" if e.lfn else ""} cl={e.first_cluster} "
            f"sec={info.get('sector')} size={e.size}{chk}{sig_s}"
        )
    if not shown:
        out("  (ninguna)")


def print_detail(fs: Fat32, e: Entry, out=print) -> None:
    info = fs.describe(e)
    out("-" * 78)
    out(f"Ruta            : {e.path}{'/' if e.is_dir else ''}")
    out(f"Nombre largo    : {e.lfn if e.lfn else '(sin LFN)'}")
    out(f"Nombre 8.3      : {e.short_name}")
    if e.lfn:
        ok = "OK" if e.lfn_checksum_ok else "NO COINCIDE"
        out(
            f"Checksum LFN    : almacenado=0x{e.lfn_checksum_stored:02X} "
            f"calculado=0x{e.lfn_checksum_computed:02X} -> {ok}  ({e.lfn_slots} ranuras LFN)"
        )
    out(f"Atributos       : 0x{e.attr:02X} ({e.attr_str})")
    out(f"Modificado      : {e.modified}   Creado: {e.created}")
    out(
        f"Cluster inicial : {e.first_cluster} = (0x{info['cluster_high']:04X}<<16)|0x{info['cluster_low']:04X} "
        f"[Hi @0x14, Lo @0x1A]"
    )
    out(f"Tamano          : {e.size} bytes")
    if info.get("sector") is not None:
        out(f"Sector absoluto : {info['sector_formula']}")
        out(f"Offset (hex ed.): {info['sector']} * {fs.boot.bytes_per_sector} = {info['byte_offset']} (0x{info['byte_offset']:X})")  # type: ignore[str-bytes-safe]
    out(
        f"Entrada de dir. : sector {info['entry_sector']}, byte {info['entry_byte_offset']} "
        f"(0x{info['entry_byte_offset']:X})"
    )
    if "chain_len" in info:
        out(f"Cadena FAT      : {chain_text(info)}")
        if "chain_matches_size" in info:
            out(
                f"Clusters segun tamano: {info['clusters_expected']} "
                f"({'coincide' if info['chain_matches_size'] else 'NO coincide'})"
            )
        if info.get("runs") and len(info["runs"]) > 1:  # type: ignore[arg-type]
            out(f"Tramos          : {info['runs']}")
    sig = info.get("signature")
    if isinstance(sig, dict):
        out(f"Firma           : esperada {sig['expected']} | encontrada {sig['found']} -> {sig['status']}")
    if e.is_dir:
        n = sum(1 for c in e.children if not c.is_dot and not c.deleted)
        out(f"Contenido       : {n} elementos")


def print_find(fs: Fat32, walk: Walk, exts: List[str], out=print) -> None:
    out("\n[7] DETALLE POR EXTENSION: " + ", ".join("." + x for x in exts))
    for ext in exts:
        matches = [e for e in walk.iter_live() if e.extension == ext]
        out(f"\n== .{ext}: {len(matches)} archivo(s) vivo(s) ==")
        for e in matches:
            print_detail(fs, e, out)


def entry_to_dict(fs: Fat32, e: Entry, with_info: bool = True) -> Dict[str, object]:
    d = asdict(e)
    d.pop("children", None)
    d.pop("info", None)
    if with_info and not e.is_dot and not e.is_volume_label:
        d["details"] = fs.describe(e)
    if e.children:
        d["children"] = [entry_to_dict(fs, c, with_info) for c in e.children if not c.deleted]
    return d


def build_json(fs: Fat32, walk: Walk) -> Dict[str, object]:
    b = fs.boot
    return {
        "image": fs.path,
        "boot_sector": {f.name: {"offset": f.offset, "raw_hex": f.raw_hex, "value": f.value} for f in b.fields},
        "geometry": {
            "bytes_per_sector": b.bytes_per_sector,
            "sectors_per_cluster": b.sectors_per_cluster,
            "reserved_sectors": b.reserved_sectors,
            "num_fats": b.num_fats,
            "sectors_per_fat": b.sectors_per_fat,
            "root_cluster": b.root_cluster,
            "root_sector": fs.root_sector,
            "root_byte_offset": fs.root_sector * b.bytes_per_sector,
            "data_start_sector": b.data_start_sector,
        },
        "root_chain": {
            "clusters": walk.root_chain.clusters if walk.root_chain else [],
            "end": walk.root_chain.end if walk.root_chain else None,
            "per_cluster": [asdict(s) for s in walk.root_stats],
        },
        "volume_label": walk.volume_label,
        "tree": [entry_to_dict(fs, e) for e in walk.root_entries if not e.deleted],
        "deleted": [entry_to_dict(fs, e) for e in walk.deleted],
        "warnings": walk.warnings,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Analizador de imagenes FAT32 (solo biblioteca estandar).")
    ap.add_argument("image", help="imagen .img/.iso con sistema de archivos FAT32 (sin tabla de particiones)")
    ap.add_argument("--tree", action="store_true", help="imprime el arbol completo con datos por archivo")
    ap.add_argument("--find", nargs="+", metavar="EXT", help="detalle de archivos con estas extensiones (ej. pdf jpg asm)")
    ap.add_argument("--json", metavar="OUT", help="guarda todo el analisis en un archivo JSON")
    args = ap.parse_args(argv)

    try:
        fs = Fat32(args.image)
    except FileNotFoundError:
        print(f"Error: no existe el archivo '{args.image}'.", file=sys.stderr)
        return 1
    except NotFat32Error as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error de lectura: {exc}", file=sys.stderr)
        return 1

    with fs:
        walk = fs.walk()
        print_boot(fs)
        print_root(fs, walk)
        if args.tree:
            print_tree(fs, walk)
        print_summary(walk)
        exts = [x.lower().lstrip(".") for x in args.find] if args.find else None
        if args.tree or exts:
            print_deleted(fs, walk, exts)
        if exts:
            print_find(fs, walk, exts)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump(build_json(fs, walk), fh, indent=2, ensure_ascii=False)
            print(f"\nJSON escrito en {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Render the hex-editor figures of the NTFS guide from REAL sectors of lab_ntfs_guia.img.

Same approach as capturas_ntfs.py: offsets come from the parsed structures
(ntfs_analyzer.py), so every highlight points at real bytes.
Usage: python3 capturas_guia.py [IMAGE] [OUT_DIR]
"""
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from capturas import render_hex, render_text  # noqa: E402
import ntfs_analyzer as na  # noqa: E402

TEST_FILE = "/LAB_NTFS.txt"
BIG_FILE = "/Proyectos/2025/Lab2/informe/datos_largo.bin"


def hx(raw):
    return " ".join(f"{b:02X}" for b in raw)


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "lab_ntfs_guia.img")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "capturas_guia")
    out.mkdir(exist_ok=True)
    name = Path(image).name
    v = na.Volume(image)
    P = v.part_start
    b = v.boot_raw

    def t(sector, extra):
        return f"sector {sector} (offset 0x{sector * 512:X}) - {extra}"

    print("Generando capturas de la guia NTFS:")
    # g01 MBR: where the volume starts (V)
    e = v.mbr_info["entry_offset"]
    render_hex(image, 0, out / "g01_mbr.png", t(0, "MBR del disco"), [
        (e + 4, e + 5, "Tipo de particion: 07 (NTFS)"),
        (e + 8, e + 12, f"LBA inicial: {hx(v.mbr_info['raw'][8:12])} -> {P} -> V = {P} x 512 = {P * 512} B"),
        (e + 12, e + 16, f"Sectores de la particion: {v.mbr_info['count']}"),
        (0x1FE, 0x200, "Firma del MBR: 55 AA"),
    ], rows=32)

    # g02 VBR (NTFS boot sector), the fields asked by the guide
    render_hex(image, P, out / "g02_vbr.png", t(P, "sector de arranque NTFS (VBR)"), [
        (0x03, 0x0B, "OEM ID: 'NTFS    '"),
        (0x0B, 0x0D, f"Bytes por sector: {hx(b[0x0B:0x0D])} -> {v.bytes_per_sector}"),
        (0x0D, 0x0E, f"Sectores por cluster: {hx(b[0x0D:0x0E])} -> {v.sectors_per_cluster}"),
        (0x28, 0x30, f"Total de sectores: {v.total_sectors}"),
        (0x30, 0x38, f"LCN de $MFT: {v.mft_lcn}"),
        (0x38, 0x40, f"LCN de $MFTMirr: {v.mftmirr_lcn}"),
        (0x40, 0x41, f"Registro MFT: {hx(b[0x40:0x41])} = {v.clusters_per_record_raw} -> 2^10 = {v.record_size} B"),
        (0x48, 0x50, f"Numero de serie: {v.serial:016X}"),
        (0x1FE, 0x200, "Firma de arranque: 55 AA"),
    ], rows=32)

    # g03 MFT record 0 at OffsetMFT
    r0 = v.record(0)
    a80 = r0.attr(na.ATTR_DATA)
    sec_i, o = divmod(a80.offset, 512)
    hl = [(0, 4, "Firma 'FILE' en OffsetMFT")] if sec_i == 0 else []
    hl += [(o, o + 4, "Atributo 0x80 ($DATA) de $MFT"), (o + 8, o + 9, "01 = no residente"),
           (o + a80.run_offset, o + a80.run_offset + 4, f"Data run: {hx(r0.buf[a80.offset + a80.run_offset:a80.offset + a80.run_offset + 4])}"
            f" -> {a80.runs[0][1]} clusters desde LCN {a80.runs[0][0]}")]
    render_hex(image, r0.sector + sec_i, out / "g03_mft_registro0.png",
               t(r0.sector + sec_i, "registro 0 ($MFT) en OffsetMFT"), [h for h in hl if h[1] <= 512], rows=32)

    # g04 root record 5: header + $INDEX_ROOT + $INDEX_ALLOCATION
    r5 = v.record(5)
    ir = r5.attr(na.ATTR_INDEX_ROOT, "$I30")
    ia = r5.attr(na.ATTR_INDEX_ALLOC, "$I30")
    for i in range(2):
        hl = []
        if i == 0:
            hl += [(0, 4, "Firma 'FILE'"), (0x10, 0x12, f"Numero de secuencia: {r5.seq}"),
                   (0x16, 0x18, "Flags 03 00 = en uso + directorio")]
        for a, label in ((ir, "Tipo 0x90 ($INDEX_ROOT), residente"), (ia, "Tipo 0xA0 ($INDEX_ALLOCATION), no residente")):
            s, o = divmod(a.offset, 512)
            if s == i:
                hl.append((o, o + 4, label))
                if a is ia:
                    ro = o + a.run_offset
                    hl.append((ro, ro + 4, f"Data run del indice -> LCN {a.runs[0][0]}"))
                else:
                    c = o + a.content_offset
                    hl.append((c + 0x1C, c + 0x1D, "Flag 01: indice grande (usa INDEX_ALLOCATION)"))
        if hl:
            render_hex(image, r5.sector + i, out / f"g04_raiz_registro5_{i + 1}.png",
                       t(r5.sector + i, f"registro 5 (raiz), sector {i + 1} de 2"), [h for h in hl if h[1] <= 512], rows=32)

    # g05 root INDX block: entry of LAB_NTFS.txt
    lab, steps = v.resolve(TEST_FILE)
    where = steps[-1]["found_in"]
    blk_sector = where["sector"]
    blk = v.read(blk_sector * 512, v.index_block_size)
    key = "LAB_NTFS.txt".encode("utf-16-le")
    name_pos = blk.index(key)
    ent = name_pos - 0x10 - 0x42  # entry header (16 B) + $FILE_NAME up to the name
    s_i, o = divmod(ent, 512)
    row0 = max(0, o // 16 - 1)
    render_hex(image, blk_sector + s_i, out / "g05_raiz_indx_lab.png",
               t(blk_sector + s_i, f"INDX de la raiz (VCN {where['vcn']}): LAB_NTFS.txt"), [
        (o, o + 6, f"Referencia MFT: {hx(blk[ent:ent + 6])} -> registro {lab.number}"),
        (o + 6, o + 8, f"Secuencia: {lab.seq}"),
        (o + 8, o + 10, "Longitud de la entrada"),
        (o + 0x10, o + 0x16, "$FILE_NAME: padre = registro 5"),
        (o + 0x10 + 0x40, o + 0x10 + 0x41, "Largo del nombre: 12"),
        (o + 0x10 + 0x42, o + 0x10 + 0x42 + len(key), "Nombre 'LAB_NTFS.txt' (UTF-16LE)"),
    ], rows=min(12, 32 - row0), row0=row0)

    # g06 test file record: header and attribute list
    si, fn, da = lab.attr(na.ATTR_STD_INFO), lab.attr(na.ATTR_FILE_NAME), lab.attr(na.ATTR_DATA)
    # Values that change when the image is rebuilt: the guide builder reads them from here
    (out / "valores.json").write_text(json.dumps({
        "registro": lab.number, "secuencia": lab.seq, "tamano": da.real_size,
        "modificado_utc": na.filetime(struct.unpack_from("<Q", si.content, 8)[0]),
    }, indent=2) + "\n")
    c = fn.offset + fn.content_offset
    render_hex(image, lab.sector, out / "g06_lab_registro.png",
               t(lab.sector, f"registro {lab.number} (LAB_NTFS.txt)"), [
        (0, 4, "Firma 'FILE'"),
        (0x10, 0x12, f"Secuencia: {lab.seq} (registro reutilizado)"),
        (0x14, 0x16, f"Primer atributo en 0x{lab.first_attr:X}"),
        (0x16, 0x18, "Flags 01 00 = archivo en uso"),
        (0x18, 0x1C, f"Bytes usados: {lab.used}"),
        (si.offset, si.offset + 4, "Atributo 0x10 $STANDARD_INFORMATION"),
        (fn.offset, fn.offset + 4, "Atributo 0x30 $FILE_NAME"),
        (c, c + 6, "Padre: registro 5 (raiz)"),
        (c + 0x42, c + 0x42 + len(key), "Nombre 'LAB_NTFS.txt'"),
        (da.offset, da.offset + 4, "Atributo 0x80 $DATA"),
    ], rows=24)

    # g07 test file record: resident $DATA with the known content
    cs = da.offset + da.content_offset
    render_hex(image, lab.sector, out / "g07_lab_datos_residentes.png",
               t(lab.sector, f"registro {lab.number}: $DATA residente"), [
        (da.offset, da.offset + 4, "Tipo 0x80 ($DATA)"),
        (da.offset + 8, da.offset + 9, "00 = residente"),
        (da.offset + 0x10, da.offset + 0x14, f"Tamano del contenido: {hx(lab.buf[da.offset + 0x10:da.offset + 0x14])} -> {da.real_size} B"),
        (da.offset + 0x14, da.offset + 0x16, f"Offset del contenido: 0x{da.content_offset:X}"),
        (cs, cs + da.real_size, "Contenido de LAB_NTFS.txt DENTRO del registro"),
    ], rows=10, row0=da.offset // 16)

    # g08 non-resident file: $DATA with data runs
    f, _ = v.resolve(BIG_FILE)
    fd = f.attr(na.ATTR_DATA)
    ro = fd.offset + fd.run_offset
    run_raw = f.buf[ro:ro + 4]
    s_i, o = divmod(fd.offset, 512)
    render_hex(image, f.sector + s_i, out / "g08_no_residente_runs.png",
               t(f.sector + s_i, f"registro {f.number}: $DATA no residente"), [
        (o, o + 4, "Tipo 0x80 ($DATA)"), (o + 8, o + 9, "01 = no residente"),
        (o + 0x10, o + 0x18, "VCN inicial: 0"), (o + 0x18, o + 0x20, f"VCN final: {fd.end_vcn}"),
        (o + 0x30, o + 0x38, f"Tamano real: {fd.real_size} B"),
        (o + fd.run_offset, o + fd.run_offset + 4, f"Data run: {hx(run_raw)} -> {fd.runs[0][1]} clusters desde LCN {fd.runs[0][0]}"),
    ], rows=6, row0=o // 16)

    # g09 first cluster of the non-resident file
    ds = v.lcn_to_sector(fd.runs[0][0])
    render_hex(image, ds, out / "g09_no_residente_cluster.png",
               t(ds, f"LCN {fd.runs[0][0]} (datos_largo.bin)"), [
        (0, 38, "Contenido real: 'linea 00000: contenido de relleno NTFS'"),
    ], rows=6)

    # Terminal renders
    for fname, args, title, limit in (
        ("g10_analizador_boot.png", [], "Terminal - ntfs_analyzer.py (sector de arranque)", 30),
        ("g11_analizador_lab.png", ["--path", TEST_FILE], "Terminal - ntfs_analyzer.py --path /LAB_NTFS.txt", 34),
        ("g12_analizador_runs.png", ["--record", str(f.number)], f"Terminal - ntfs_analyzer.py --record {f.number}", 34),
    ):
        res = run([sys.executable, "-I", str(HERE / "ntfs_analyzer.py"), image, *args])
        lines = [l.expandtabs(4).rstrip() for l in res.splitlines()][:limit]
        render_text([f"$ python3 ntfs_analyzer.py {name} {' '.join(args)}".rstrip(), ""] + lines, out / fname, title)

    # The Sleuth Kit contrast (only when installed)
    if shutil.which("fsstat"):
        for fname, cmd, limit in (
            ("g13_tsk_fsstat.png", ["fsstat", "-o", str(P), image], 30),
            ("g14_tsk_fls.png", ["fls", "-o", str(P), image], 30),
            ("g15_tsk_istat.png", ["istat", "-o", str(P), image, str(lab.number)], 40),
        ):
            res = run(cmd)
            lines = [l.expandtabs(4).rstrip() for l in res.splitlines()][:limit]
            render_text([f"$ {' '.join(cmd[:-1] + [Path(cmd[-1]).name] if cmd[-1] == image else cmd).replace(image, name)}", ""] + lines,
                        out / fname, f"Terminal - The Sleuth Kit ({cmd[0]})")
    else:
        print("  (sin The Sleuth Kit: se omiten g13-g15)")


if __name__ == "__main__":
    main()

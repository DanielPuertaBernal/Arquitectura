#!/usr/bin/env python3
"""Render hex-editor style screenshots of REAL sectors of lab_ntfs.img.

Reuses render_hex/render_text from ../capturas.py. Offsets are computed from the
parsed structures (ntfs_analyzer.py), so every highlight points at real bytes.
Usage: python3 capturas_ntfs.py [IMAGE] [OUT_DIR]
"""
import subprocess
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from capturas import render_hex, render_text  # noqa: E402
import ntfs_analyzer as na  # noqa: E402


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "lab_ntfs.img")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "capturas")
    out.mkdir(exist_ok=True)
    name = Path(image).name
    v = na.Volume(image)
    P = v.part_start

    def t(sector, extra):
        return f"{name} - sector {sector} (offset 0x{sector * 512:X}) - {extra}"

    print("Generando capturas NTFS:")
    # 01 MBR partition entry
    render_hex(image, 0, out / "01_mbr_particion.png", t(0, "MBR, tabla de particiones"), [
        (0x1BE, 0x1BF, "Estado de arranque: 00 (no activa)"),
        (0x1C2, 0x1C3, "Tipo de particion: 07 (NTFS)"),
        (0x1C6, 0x1CA, "LBA inicial: 00 08 00 00 -> 0800h = 2048"),
        (0x1CA, 0x1CE, "Sectores: 00 40 06 00 -> 064000h = 409600"),
        (0x1FE, 0x200, "Firma del MBR: 55 AA"),
    ], rows=32)

    # 02 boot sector
    render_hex(image, P, out / "02_boot_sector.png", t(P, "Boot Sector NTFS"), [
        (0x03, 0x0B, "OEM ID: 'NTFS    '"),
        (0x0B, 0x0D, "Bytes por sector: 00 02 -> 0200h = 512"),
        (0x0D, 0x0E, "Sectores por cluster: 08 -> 8 (cluster = 4096 B)"),
        (0x28, 0x30, "Total de sectores: FF 3F 06 00... -> 63FFFh = 409599"),
        (0x30, 0x38, "LCN de $MFT: 04 00... -> 4"),
        (0x38, 0x40, "LCN de $MFTMirr: FF 63 00... -> 63FFh = 25599"),
        (0x40, 0x41, "Clusters por registro MFT: F6 = -10 -> 2^10 = 1024 B"),
        (0x44, 0x45, "Clusters por bloque de indice: 01 -> 4096 B"),
        (0x48, 0x50, "Numero de serie del volumen"),
        (0x1FE, 0x200, "Firma: 55 AA"),
    ], rows=32)

    # 03 MFT record 0 (two sectors: header+attrs, then tail with fixup)
    r0 = v.record(0)
    s0 = r0.sector
    a80 = r0.attr(na.ATTR_DATA)
    hl = [(0, 4, "Firma 'FILE'"), (4, 6, f"Offset de la USA: 0x{r0.uso:X}"), (6, 8, f"Entradas de la USA: {r0.usc}"),
          (0x16, 0x18, f"Flags: {r0.flags:04X} -> en uso"),
          (r0.uso, r0.uso + 6, f"USA: USN {r0.usn.hex(' ').upper()} + 2 valores originales"),
          (0x1FE, 0x200, "Ultimos 2 bytes del sector = USN (reemplazados por la USA)")]
    render_hex(image, s0, out / "03_mft_registro0.png", t(s0, "registro 0 ($MFT), 1/2"), hl, rows=32)
    # 03b record 0 DATA attribute with data runs (find which sector)
    off = a80.offset
    sec_i, o = divmod(off, 512)
    hl = [(o, o + 4, "Tipo 0x80 ($DATA)"), (o + 8, o + 9, "No residente = 01"),
          (o + a80.run_offset, o + a80.run_offset + 4, "Run list: 12 20 01 04 -> longitud 0120h = 288 clusters, LCN 4")]
    hl = [h for h in hl if h[1] <= 512]
    render_hex(image, s0 + sec_i, out / "03b_mft_registro0_data.png",
               t(s0 + sec_i, "registro 0: $DATA y data run"), hl, rows=32)

    # 04 root record 5: INDEX_ROOT
    r5 = v.record(5)
    ir = r5.attr(na.ATTR_INDEX_ROOT, "$I30")
    ia = r5.attr(na.ATTR_INDEX_ALLOC, "$I30")
    sec_i, o = divmod(ir.offset, 512)
    hl = [(0, 4, "Firma 'FILE'"), (0x16, 0x18, "Flags 03 = en uso + directorio")]
    hl += [(o, o + 4, "Tipo 0x90 ($INDEX_ROOT)"), (o + ir.content_offset, o + ir.content_offset + 4, "Indexa atributo 0x30"),
           (o + ir.content_offset + 0x1C, o + ir.content_offset + 0x1D, "Flag 01: indice grande (usa INDEX_ALLOCATION)")]
    render_hex(image, r5.sector + sec_i, out / "04_raiz_index_root.png",
               t(r5.sector + sec_i, "registro 5 (raiz): $INDEX_ROOT"), [h for h in hl if h[1] <= 512 and (sec_i or h[0] < 0x200)], rows=32)

    # 05 INDX of the root and of /Muchos
    big, _ = v.resolve("/Muchos")
    alloc = big.attr(na.ATTR_INDEX_ALLOC, "$I30")
    isec = v._vcn_sector(alloc, 0)
    e0 = 0x18 + struct.unpack_from("<I", v.read(isec * 512 + 0x18, 4))[0]
    nl = v.read(isec * 512 + e0 + 0x10 + 0x40, 1)[0]
    render_hex(image, isec, out / "05_indx_muchos.png", t(isec, "bloque INDX (VCN 0) de /Muchos"), [
        (0, 4, "Firma 'INDX'"), (4, 6, "Offset de la USA"), (6, 8, "Entradas de la USA"),
        (0x10, 0x18, "VCN del bloque: 0"),
        (0x18, 0x1C, "Offset de la 1a entrada (desde 0x18)"),
        (e0, e0 + 6, "Entrada 1: referencia al registro (48 bits)"),
        (e0 + 8, e0 + 10, "Longitud de la entrada"),
        (e0 + 0x10 + 0x40, e0 + 0x10 + 0x42, f"Largo del nombre ({nl}) y namespace"),
        (e0 + 0x10 + 0x42, e0 + 0x10 + 0x42 + nl * 2, "Nombre UTF-16LE"),
    ], rows=16)

    # 06 file record 58: FILE_NAME + non-resident DATA
    f, _ = v.resolve("/Proyectos/2025/Lab2/informe/datos_largo.bin")
    fn, da = f.attr(na.ATTR_FILE_NAME), f.attr(na.ATTR_DATA)
    c = fn.offset + fn.content_offset
    hl = [(0, 4, "Firma 'FILE'"), (0x16, 0x18, "Flags 01 = archivo en uso"),
          (c, c + 6, "$FILE_NAME: registro padre (39 = informe)"),
          (c + 0x40, c + 0x42, "Largo del nombre y namespace (0 = POSIX)"),
          (c + 0x42, c + 0x42 + len(fn.content) - 0x42, "Nombre 'datos_largo.bin' (UTF-16LE)"),
          (da.offset, da.offset + 4, "Tipo 0x80 ($DATA)"),
          (da.offset + 8, da.offset + 9, "01 = no residente"),
          (da.offset + 0x30, da.offset + 0x38, "Tamano real: 39000"),
          (da.offset + da.run_offset, da.offset + da.run_offset + 4, "Data run: 21 0A 19 6A -> 10 clusters, LCN 27161")]
    render_hex(image, f.sector, out / "06_registro_archivo.png",
               t(f.sector, f"registro {f.number}: $FILE_NAME y $DATA"), hl, rows=32)

    # 07 resident tiny file
    p, _ = v.resolve("/Documentos/pequeno.txt")
    d = p.attr(na.ATTR_DATA)
    cs = d.offset + d.content_offset
    render_hex(image, p.sector, out / "07_residente.png",
               t(p.sector, f"registro {p.number}: $DATA residente"), [
        (d.offset, d.offset + 4, "Tipo 0x80 ($DATA)"), (d.offset + 8, d.offset + 9, "00 = residente"),
        (d.offset + 0x10, d.offset + 0x14, f"Tamano del contenido: {d.real_size}"),
        (cs, cs + d.real_size, "Contenido DENTRO del registro MFT"),
    ], rows=32)

    # 08 data start with signature (JPEG)
    j, _ = v.resolve("/Imagenes/tierra.jpg")
    jl = j.attr(na.ATTR_DATA).runs[0][0]
    js = v.lcn_to_sector(jl)
    render_hex(image, js, out / "08_datos_jpg.png",
               t(js, f"inicio de tierra.jpg (registro {j.number}, LCN {jl})"), [
        (0, 4, "Firma JPEG: FF D8 FF E2"), (6, 16, "Marcador APP2: ICC_PROFILE")], rows=4)

    # 09 deleted record
    dels = v.deleted()
    dr = v.record(dels[0]["record"])
    render_hex(image, dr.sector, out / "09_registro_borrado.png",
               t(dr.sector, f"registro {dr.number} borrado (flags=0)"), [
        (0, 4, "Firma 'FILE' sigue presente"), (0x16, 0x18, "Flags 00 00: NO en uso (antes 01 00)"),
        (0x12, 0x14, "Enlaces: 0"),
    ] + [(a.offset, a.offset + 4, "Tipo 0x80 ($DATA) aun presente") for a in dr.attrs if a.type == na.ATTR_DATA], rows=32)

    # 10 ADS
    n, _ = v.resolve("/Documentos/nota.txt")
    ads = n.attr(na.ATTR_DATA, "secreto")
    cs = ads.offset + ads.content_offset
    render_hex(image, n.sector, out / "10_ads.png",
               t(n.sector, f"registro {n.number}: $DATA 'secreto' (ADS)"), [
        (ads.offset, ads.offset + 4, "Tipo 0x80 ($DATA)"),
        (ads.offset + 9, ads.offset + 10, "Largo del nombre del stream: 07"),
        (ads.offset + 0x18, ads.offset + 0x18 + 14, "Nombre 'secreto' (UTF-16LE)"),
        (cs, cs + ads.real_size, "Contenido del ADS"),
    ], rows=32)

    # Terminal renders
    fls = subprocess.run(["fls", "-o", str(P), "-r", "-p", image], capture_output=True, text=True).stdout.splitlines()
    pick = [l for l in fls if not l.split(":", 1)[-1].strip().startswith("$") and "Muchos/" not in l and "OrphanFile-1" not in l][:34]
    pick += [l for l in fls if "OrphanFile-12" in l]
    render_text([f"$ fls -o {P} -r -p {name}", ""] + [l.expandtabs(4) for l in pick],
                out / "11_fls.png", "Terminal - The Sleuth Kit (fls)")
    res = subprocess.run([sys.executable, "-I", str(HERE / "ntfs_analyzer.py"), image, "--path",
                          "/Proyectos/2025/Lab2/informe/datos_largo.bin"], capture_output=True, text=True, check=True)
    lines = [l.expandtabs(4).rstrip() for l in res.stdout.splitlines()]
    render_text(["$ python3 ntfs_analyzer.py lab_ntfs.img --path /Proyectos/2025/Lab2/informe/datos_largo.bin", ""] + lines[:36],
                out / "12_analizador_path.png", "Terminal - ntfs_analyzer.py")
    res = subprocess.run([sys.executable, "-I", str(HERE / "ntfs_analyzer.py"), image, "--tree"],
                         capture_output=True, text=True, check=True)
    render_text(["$ python3 ntfs_analyzer.py lab_ntfs.img --tree", ""] + [l for l in res.stdout.splitlines()][:46],
                out / "13_analizador_tree.png", "Terminal - ntfs_analyzer.py --tree")


if __name__ == "__main__":
    main()

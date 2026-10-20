#!/usr/bin/env python3
"""Render hex-editor style screenshots of real sectors from the FAT32 image.

Every image is built from the bytes actually read from the image file, so the
evidence is reproducible: `python3 capturas.py [IMAGE] [OUT_DIR]`.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SECTOR = 512
FONT_PATH = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
FONT_SIZE = 18
PAD = 24

BG = (30, 30, 46)
FG = (205, 214, 244)
DIM = (127, 132, 156)
TITLE_BG = (49, 50, 68)
PALETTE = [
    (243, 139, 168),  # red
    (166, 227, 161),  # green
    (137, 180, 250),  # blue
    (249, 226, 175),  # yellow
    (203, 166, 247),  # mauve
    (148, 226, 213),  # teal
    (250, 179, 135),  # peach
    (245, 194, 231),  # pink
]


def read_sector(image, sector, count=1):
    with open(image, "rb") as f:
        f.seek(sector * SECTOR)
        return f.read(count * SECTOR)


def render_hex(image, sector, out, title, highlights, rows=None, row0=0, save=True):
    """Draw a hex dump of one sector.

    highlights: list of (start, end_exclusive, label) relative to the sector.
    rows: number of 16-byte rows to show (default: whole sector).
    row0: first 16-byte row to show (default 0).
    save: if False, return the PIL image instead of writing `out`.
    """
    data = read_sector(image, sector)
    rows = rows or len(data) // 16 - row0
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    cw = font.getbbox("0")[2]
    lh = FONT_SIZE + 8
    base = sector * SECTOR

    color_of = {}
    for i, (start, end, _) in enumerate(highlights):
        for b in range(start, end):
            color_of[b] = PALETTE[i % len(PALETTE)]

    off_cols, hex_cols, asc_cols = 10, 16 * 3 + 1, 16
    width = PAD * 2 + cw * (off_cols + 2 + hex_cols + 2 + asc_cols)
    title_h = lh + 16
    header_h = lh
    legend_h = lh * len(highlights) + (PAD if highlights else 0)
    height = title_h + header_h + lh * rows + legend_h + PAD * 2

    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, title_h], fill=TITLE_BG)
    d.text((PAD, 8), title, font=font, fill=FG)

    x_off = PAD
    x_hex = x_off + cw * (off_cols + 2)
    x_asc = x_hex + cw * (hex_cols + 2)
    y = title_h + PAD // 2
    d.text((x_off, y), "Offset", font=font, fill=DIM)
    for c in range(16):
        d.text((x_hex + cw * (c * 3 + (1 if c >= 8 else 0)), y), f"{c:02X}", font=font, fill=DIM)
    d.text((x_asc, y), "ASCII", font=font, fill=DIM)
    y += header_h

    for r in range(row0, row0 + rows):
        d.text((x_off, y), f"{base + r * 16:010X}", font=font, fill=DIM)
        for c in range(16):
            i = r * 16 + c
            b = data[i]
            xh = x_hex + cw * (c * 3 + (1 if c >= 8 else 0))
            xa = x_asc + cw * c
            col = color_of.get(i)
            if col:
                d.rectangle([xh - 2, y - 1, xh + cw * 2 + 2, y + lh - 5], fill=col)
                d.rectangle([xa, y - 1, xa + cw, y + lh - 5], fill=col)
            ink = BG if col else FG
            d.text((xh, y), f"{b:02X}", font=font, fill=ink)
            ch = chr(b) if 32 <= b < 127 else "."
            d.text((xa, y), ch, font=font, fill=ink if col else DIM)
        y += lh

    y += PAD // 2
    for i, (start, end, label) in enumerate(highlights):
        col = PALETTE[i % len(PALETTE)]
        d.rectangle([PAD, y + 3, PAD + cw * 2, y + lh - 7], fill=col)
        rng = f"0x{start:03X}" if end - start == 1 else f"0x{start:03X}-0x{end - 1:03X}"
        d.text((PAD + cw * 3, y), f"{rng}  {label}", font=font, fill=FG)
        y += lh

    if not save:
        return img
    img.save(out)
    print(f"  {out}")


def lfn_text(entries):
    """Decode a run of LFN slots (physical order: last slot first)."""
    name = ""
    for e in sorted(entries, key=lambda e: e[0] & 0x1F):
        raw = e[1:11] + e[14:26] + e[28:32]
        for i in range(0, len(raw), 2):
            ch = raw[i:i + 2]
            if ch in (b"\x00\x00", b"\xff\xff"):
                return name
            name += ch.decode("utf-16le")
    return name


def entry_info(image, sector, sfn_off):
    """Parse a short entry plus the LFN slots right before it (same sector)."""
    d = read_sector(image, sector)
    lfn = []
    o = sfn_off - 32
    while o >= 0 and d[o + 11] == 0x0F and d[o] != 0xE5:
        lfn.insert(0, d[o:o + 32])
        o -= 32
    e = d[sfn_off:sfn_off + 32]
    cl = (int.from_bytes(e[20:22], "little") << 16) | int.from_bytes(e[26:28], "little")
    return dict(lfn=lfn, lfn_start=sfn_off - 32 * len(lfn), sfn_off=sfn_off, name=lfn_text(lfn),
                short=e[:11].decode("ascii"), cluster=cl, size=int.from_bytes(e[28:32], "little"),
                attr=e[11], hi=e[20:22], lo=e[26:28])


def entry_highlights(info):
    """Highlights for one directory entry (LFN slots + 8.3 entry fields)."""
    o = info["sfn_off"]
    hl = []
    if info["lfn"]:
        hl.append((info["lfn_start"], o, f"{len(info['lfn'])} ranura(s) LFN (0x0F): '{info['name']}'"))
    hl += [
        (o, o + 11, f"Nombre 8.3: {info['short']}"),
        (o + 11, o + 12, f"Atributo 0x{info['attr']:02X} (archivo)"),
        (o + 20, o + 22, f"Cluster alto: {info['hi'].hex(' ').upper()} -> {int.from_bytes(info['hi'], 'little')}"),
        (o + 26, o + 28, f"Cluster bajo: {info['lo'].hex(' ').upper()} -> cluster {info['cluster']}"),
        (o + 28, o + 32, f"Tamano: {info['size']:,} bytes".replace(",", " ")),
    ]
    return hl


def stack(image, panels, out):
    """Stack several render_hex panels vertically into one image.

    panels: list of dicts with the render_hex arguments (sector, title, highlights, rows, row0).
    """
    imgs = [render_hex(image, save=False, out=None, **p) for p in panels]
    w = max(i.width for i in imgs)
    gap = 6
    img = Image.new("RGB", (w, sum(i.height for i in imgs) + gap * (len(imgs) - 1)), BG)
    y = 0
    for i in imgs:
        img.paste(i, (0, y))
        y += i.height + gap
    img.save(out)
    print(f"  {out}")


def render_text(lines, out, title):
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    cw = font.getbbox("0")[2]
    lh = FONT_SIZE + 8
    width = PAD * 2 + cw * max(len(l) for l in lines + [title])
    title_h = lh + 16
    height = title_h + PAD * 2 + lh * len(lines)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, title_h], fill=TITLE_BG)
    d.text((PAD, 8), title, font=font, fill=FG)
    y = title_h + PAD
    for line in lines:
        ink = PALETTE[1] if "OK" in line and "Firma" in line else FG
        d.text((PAD, y), line, font=font, fill=ink)
        y += lh
    img.save(out)
    print(f"  {out}")


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "Arqui22025.img"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "capturas")
    out.mkdir(exist_ok=True)
    name = Path(image).name

    def t(sector, extra):
        return f"{name} — sector {sector} (offset 0x{sector * SECTOR:X}) — {extra}"

    print("Generando capturas:")
    render_hex(image, 0, out / "01_boot_sector.png", t(0, "Boot Sector"), [
        (0x0B, 0x0D, "Bytes por sector: 00 02 -> 0x0200 = 512"),
        (0x0D, 0x0E, "Sectores por cluster: 01 -> 1"),
        (0x0E, 0x10, "Sectores reservados: 88 04 -> 0x0488 = 1160"),
        (0x10, 0x11, "Numero de FAT: 02 -> 2"),
        (0x24, 0x28, "Sectores por FAT: BC 1D 00 00 -> 0x1DBC = 7612"),
        (0x2C, 0x30, "Cluster del directorio raiz: 02 00 00 00 -> 2"),
        (0x52, 0x5A, "Tipo de sistema de archivos: 'FAT32   '"),
        (0x1FE, 0x200, "Firma del sector de arranque: 55 AA"),
    ])
    render_hex(image, 16384, out / "02_root_dir_inicio.png",
               t(16384, "Root Directory, cluster 2"), [
        (0x00, 0x20, "Ranura LFN de 'System Volume Information' (atributo 0x0F en 0x0B)"),
    ])
    render_hex(image, 1160, out / "03_fat_sector1160.png",
               t(1160, "FAT 1, inicio"), [
        (0x08, 0x0C, "FAT[2] = 5E 10 00 00 -> 4190 (siguiente cluster de la raiz)"),
        (0x18, 0x1C, "FAT[6] = 6F 7A 07 00 -> 490095 (siguiente cluster de la raiz)"),
    ], rows=4)
    render_hex(image, 20572, out / "04_root_cluster4190.png",
               t(20572, "Root Directory, 2do cluster (4190)"), [])
    render_hex(image, 16384, out / "05_entrada_documento.png",
               t(16384, "entrada 'Documento de Prueba.txt'"), [
        (0x120, 0x140, "LFN #2 (0x42): 'Prueba.txt', checksum 0x87 en 0x12D"),
        (0x140, 0x160, "LFN #1 (0x01): 'Documento de ', checksum 0x87"),
        (0x160, 0x16B, "Nombre 8.3: DOCUME~2TXT"),
        (0x16B, 0x16C, "Atributo 0x20 (archivo)"),
        (0x174, 0x176, "Cluster alto: 00 00"),
        (0x17A, 0x17C, "Cluster bajo: 3A 00 -> 58"),
        (0x17C, 0x180, "Tamano: 43 00 00 00 -> 67 bytes"),
    ])
    render_hex(image, 16440, out / "06_datos_documento.png",
               t(16440, "datos de 'Documento de Prueba.txt' (cluster 58)"), [
        (0x00, 0x43, "Contenido del archivo (67 bytes)"),
    ], rows=6)
    render_hex(image, 425076, out / "07_pdf_firma.png",
               t(425076, "inicio de PDF"), [
        (0x00, 0x08, "Firma %PDF-1.3"),
    ], rows=4)
    render_hex(image, 502037, out / "08_jpg_firma.png",
               t(502037, "inicio de Arquitecturas.jpg"), [
        (0x00, 0x04, "Firma JPEG: FF D8 FF E0"),
        (0x06, 0x0A, "Marcador JFIF"),
    ], rows=4)

    # ---- Capturas adicionales (10-19): entradas de directorio + datos, carpetas y cadena de la raiz ----
    def entry_panel(sector, sfn_off, what, extra=0):
        """Panel con la entrada de directorio (LFN + 8.3) ya resaltada; muestra las filas que la contienen."""
        info = entry_info(image, sector, sfn_off)
        first = info["lfn_start"] // 16
        last = (sfn_off + 31) // 16
        return dict(sector=sector, title=t(sector, f"entrada {what}"), highlights=entry_highlights(info),
                    rows=last - first + 1 + extra, row0=first)

    def data_panel(sector, what, hl, rows=4):
        return dict(sector=sector, title=t(sector, f"datos {what}"), highlights=hl, rows=rows)

    # aplicacion: Mars4_5.jar (CarpeDocu) -> cluster 490097
    stack(image, [entry_panel(352797, 0xA0, "Mars4_5.jar"),
           data_panel(506479, "Mars4_5.jar", [(0x00, 0x04, "Firma ZIP/JAR: 50 4B 03 04 ('PK')")])],
          out / "10_aplicacion_jar.png")
    # Word: Ordenadores De Placa Reducida.docx (Carpeta01/Docu) -> cluster 405883
    stack(image, [entry_panel(365206, 0xA0, ".docx (Word)"),
           data_panel(422265, ".docx (Word)", [(0x00, 0x04, "Firma ZIP/OOXML: 50 4B 03 04 ('PK')")])],
          out / "11_word_docx.png")
    # .asm: x2n.asm y ejemploSuma.asm (texto legible en la columna ASCII)
    stack(image, [entry_panel(352797, 0xC0, "x2n.asm"),
           data_panel(514622, "x2n.asm", [(0x00, 0x08, "Texto ensamblador: .data")], rows=6)],
          out / "12_asm_x2n.png")
    stack(image, [entry_panel(16388, 0x1A0, "ejemploSuma.asm"),
           data_panel(506476, "ejemploSuma.asm", [(0x00, 0x07, "Texto ensamblador: .data")], rows=6)],
          out / "13_asm_ejemplosuma.png")
    # segundo PDF y segundo JPEG
    stack(image, [entry_panel(365207, 0xA0, "PDF Montaje"),
           data_panel(434651, "PDF Montaje", [(0x00, 0x08, "Firma %PDF-1.4")])],
          out / "14_pdf_montaje.png")
    stack(image, [entry_panel(478822, 0xA0, "CPU.jpg"),
           data_panel(502732, "CPU.jpg", [(0x00, 0x03, "Firma JPEG: FF D8 FF"), (0x06, 0x0A, "Marcador JFIF")])],
          out / "15_jpg_cpu.png")

    # carpetas: cluster de directorio con '.', '..' y sus hijos
    def folder_hl(sector, entries):
        d = read_sector(image, sector)
        hl = []
        for o, what in entries:
            e = d[o:o + 32]
            cl = (int.from_bytes(e[20:22], "little") << 16) | int.from_bytes(e[26:28], "little")
            hl.append((o, o + 11, f"{what}: '{e[:11].decode('ascii').strip()}' cluster {cl}"))
        return hl
    render_hex(image, 352797, out / "16_carpeta_carpedocu.png",
               t(352797, "dir. CarpeDocu (cl. 336415)"),
               folder_hl(352797, [(0x00, "'.' (la propia carpeta)"), (0x20, "'..' (padre, cluster 0 = raiz)"),
                                  (0x60, "subcarpeta"), (0xA0, "archivo"), (0xC0, "archivo"), (0x140, "archivo")]),
               rows=22)
    render_hex(image, 357900, out / "17_carpeta_carpeta01.png",
               t(357900, "dir. Carpeta01 (cl. 341518)"),
               folder_hl(357900, [(0x00, "'.' (la propia carpeta)"), (0x20, "'..' (padre, cluster 0 = raiz)"),
                                  (0x60, "subcarpeta"), (0xA0, "archivo"), (0x100, "archivo"), (0x140, "subcarpeta Docu")]),
               rows=22)

    # cadena del Root Directory: FAT[4190]=6 y FAT[490095]=EOC; clusters 6 y 490095
    stack(image, [dict(sector=1192, title=t(1192, "FAT 1: FAT[4190]"), rows=3, row0=22, highlights=[
               (0x178, 0x17C, "FAT[4190] = 06 00 00 00 -> 6 (la raiz sigue en el cluster 6)")]),
           dict(sector=4988, title=t(4988, "FAT 1: FAT[490095]"), rows=2, row0=26, highlights=[
               (0x1BC, 0x1C0, "FAT[490095] = FF FF FF 0F -> fin de cadena (EOC)")])],
          out / "18_raiz_fat_cadena.png")
    stack(image, [dict(sector=16388, title=t(16388, "Root Directory, cluster 6"), rows=4, highlights=[
               (0x00, 0x20, "Primera entrada del cluster 6 (ranura LFN, atributo 0x0F)")]),
           dict(sector=506477, title=t(506477, "Root Dir., cluster 490095"), rows=4, highlights=[
               (0x00, 0x0B, "Primera entrada del cluster 490095: 'EJEMPL~3ASM'")])],
          out / "19_raiz_clusters_6_490095.png")

    cmd = [sys.executable, "-I", "fat32_analyzer.py", image, "--find", "pdf", "jpg", "asm"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = [l.expandtabs(4).rstrip() for l in res.stdout.splitlines()]
    start = next((i for i, l in enumerate(lines) if l.startswith("[7]")), 0)
    shown = lines[start:start + 34]
    render_text(["$ python3 fat32_analyzer.py " + name + " --find pdf jpg asm", ""] + shown,
                out / "09_analyzer_find.png", "Terminal — fat32_analyzer.py")


if __name__ == "__main__":
    main()

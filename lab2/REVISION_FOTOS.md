# Photo/screenshot review: Lab 2 (FAT32 + NTFS)

Date: 2026-10-14. Read-only review. Sources: `Laboratorio 2. Estructura de arcchivos FAT32.docx` (the official guide), `Laboratorio_NTFS_Guia_Completa.docx`, `capturas/`, `ntfs/capturas/`, `informe/diagramas/`. Sector numbers were checked with `fat32_analyzer.py --find` on `Arqui22025.img`.

## 1. What the official guide asks for

| Item | Weight | Evidence it requires |
|---|---|---|
| FAT32: Boot Sector parameters (bytes/sector, sectors/cluster, reserved sectors, FAT copies, sectors per FAT, Root Directory location) | part of 60 % | The calculation plus "images showing the sector or sectors where the information is" |
| FAT32: ≥2 .pdf, 1 application, ≥2 .jpeg, 1 Word file, ≥2 .asm, 2 folders with their structure | part of 60 % | The calculation for **each** file and folder, plus an image of the sector where each one is |
| Problem with Root Directory entries | 10 % | Explain why entries are missing and the procedure to find the rest |
| NTFS procedure | 20 % | "Images **and/or diagrams**" showing the procedure (so for this item the guide does accept diagrams) |
| Python bonus | bonus | A script that reads the .img and extracts all of the above |

The guide lists a hex editor (HxD/Bless/GHex/xxd) as equipment but does not demand screenshots of a particular program. Every image in `capturas/` and `ntfs/capturas/` is a hex dump of the real image rendered by `capturas.py` / `capturas_ntfs.py`, so it shows real bytes. **Risk:** none of them is a screenshot of HxD or GHex itself.

## 2. Requirement → evidence → status

Diagrams (`fat_d*`, `ntfs_d*`) are not counted as real evidence here, except for NTFS, where the guide explicitly accepts them.

| Requirement | Real evidence | Status |
|---|---|---|
| Boot Sector (all 6 parameters + signature) | `01_boot_sector` (fields highlighted with values) | ✅ Meets |
| Root Directory location (cluster 2 = sector 16384) | `02_root_dir_inicio` | ✅ Meets |
| FAT and the Root Directory cluster chain | `03_fat_sector1160` (FAT[2]=4190, FAT[6]=490095), `04_root_cluster4190` | 🟡 Partial: no image of FAT[4190]=6, the EOC of FAT[490095], or clusters 6 and 490095 of the root |
| Root Directory problem (10 %) | Only `fat_d3` (diagram) plus 03/04 | 🟡 Partial: the chain 2→4190→6→490095 is shown only in a diagram for its last two links |
| Example entry → data (full method) | `05_entrada_documento`, `06_datos_documento` (Documento de Prueba.txt) | ✅ Meets (it is a .txt, so it is not one of the required categories) |
| ≥2 PDF | `07_pdf_firma` (1 PDF, sector 425076) + `09_analyzer_find` (calculation for 2 PDFs) | 🟡 Partial: hex of only one PDF; no hex of the directory entry |
| 1 application | — | ❌ Missing |
| ≥2 JPEG | `08_jpg_firma` (Arquitecturas.jpg only) | 🟡 Partial: one image, and no directory entry |
| 1 Word file | — | ❌ Missing |
| ≥2 .asm | — (09 shows only PDFs) | ❌ Missing |
| 2 folders and their structure | Only `fat_d6` (diagram) | ❌ Missing as real evidence: no hex of any folder's directory cluster |
| NTFS (20 %) | `ntfs/capturas/01`–`13`: MBR, Boot Sector, MFT record 0 and data run, root $INDEX_ROOT, INDX block, file record, resident data, JPG data, deleted record, ADS, `fls`, path walk and tree from the analyzer, plus diagrams `ntfs_d1`–`d7` | ✅ Meets (real captures and diagrams) |
| Python bonus | `09_analyzer_find`, `ntfs/12`, `ntfs/13` | ✅ Meets |

### Defects in existing images

- `ntfs/capturas/08_datos_jpg.png`: the legend says "FF D8 FF E0 / JFIF", but the highlighted bytes are `FF D8 FF E2` / `ICC_PROFILE`. Fix the legend in `capturas_ntfs.py` and regenerate the image.
- `Laboratorio_NTFS_Guia_Completa.docx` still has empty "📷 ESPACIO PARA CAPTURA" boxes (VirtualBox, Kali, figures 5–23). Its numbers (manual.pdf, sectors 2216/2220/297600) do not match `lab_ntfs.img` (datos_largo.bin, record 58…). If this guide is part of the delivery, it is inconsistent with the captures. If it is not, ignore this point.

## 3. Missing photos (what to capture exactly)

Formula: sector = 16384 + (cluster − 2); offset = sector × 512.

1. **Application**: the entry for `/CarpeDocu/Mars4_5.jar` at offset 0xAC43AA0 (sector 352797), plus its data at sector 506479 (offset 0xF74DE00) showing the `50 4B 03 04` signature. Alternative: `quickshortcutmaker-2-4-0.apk` (entry 0x8001E0, data sector 16441).
2. **Word**: the entry for `/Carpeta01/Docu/Ordenadores De Placa Reducida.docx` at 0xB252CA0 (sector 365206), plus its data at sector 422265 (offset 0xCE2F200) showing `PK`.
3. **Two .asm files**: `/CarpeDocu/x2n.asm` (entry 0xAC43AC0, data sector 514622 = 0xFB47C00) and `/ejemploSuma.asm` (entry 0x8009A0, data sector 506476 = 0xF74D800). The asm text is readable in the ASCII column.
4. **Second PDF**: `Montaje_y_mantenimiento_de_equipos.pdf`, entry 0xB252EA0, data sector 434651 (0xD43B600), signature `%PDF-1.4`.
5. **Second JPEG**: `/Personal/Fotos/CPU.jpg`, entry 0xE9CCCA0, data sector 502732 (0xF579800), `FF D8 FF`. A directory entry for the jpg/pdf already captured also helps.
6. **Two folders**: the directory cluster of `CarpeDocu` (sector 352797, 0xAC43A00) and of `Carpeta01` (cluster 341518 → sector 357900, 0xAEC1800), showing the `.`/`..` entries and their children. Optionally, `Docu` at sector 365206.
7. **Root Directory (10 %)**: FAT[4190] at byte 593920 + 4190×4 = 0x95178 (sector 1192) showing `06 00 00 00`; the root's cluster 6 (sector 16388, 0x800800); cluster 490095 (sector 506477, 0xF74DA00); and FAT[490095] = `FF FF FF 0F` (sector 4988).
8. Optional (reduces risk): one real HxD/GHex screenshot, for example of the Boot Sector, so it is clear a hex editor was used.

## 4. Verdict

**Not enough to submit yet.** NTFS and the bonus are fine, but FAT32 (60 %) has no real evidence for the application, Word, .asm and the two folders, and the Root Directory item (10 %) is only partial.

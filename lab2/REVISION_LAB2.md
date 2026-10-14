# Laboratorio 2 — Revisión y estado del trabajo

Documento de seguimiento: qué hay, qué está bien, qué corregir y qué falta.

## 1. Archivos de la carpeta

| Archivo | Qué es | Estado |
|---|---|---|
| `Laboratorio 2. Estructura de arcchivos FAT32.docx` | Enunciado del profesor | Referencia |
| `Arqui22025.img` | Imagen **FAT32** de la microSD (la correcta) | Usar esta |
| `arqui.iso` | Imagen **FAT16** con otro contenido (ANDROID, LOST.DIR, mp4) | **No usar** — no es FAT32 |
| `Laboratorio_NTFS_Guia_Completa.docx` | Aporte del compañero (parte NTFS, 20 %) | Requiere correcciones (sección 3) |
| `fat32_analyzer.py` | Script Python que analiza la imagen FAT32 (bono) | Hecho y probado |
| `tests/test_fat32_analyzer.py` | 35 pruebas unitarias del script | Pasan |
| `resultados_fat32.md` | Resolución del problema FAT32 (60 %) y del 10 % con valores reales | Hecho, con 9 capturas y 6 diagramas Mermaid |
| `capturas.py` + `capturas/` | Genera las capturas hex FAT32 desde los bytes reales | Hecho |
| `ntfs/lab_ntfs.img` | Imagen NTFS propia (MBR + NTFS en sector 2048), creada con `ntfs/build_ntfs_image.sh` | Hecho, SHA-256 verificado |
| `ntfs/ntfs_analyzer.py` + `ntfs/tests/` | Analizador NTFS (MBR, boot sector, MFT, fixups, data runs, $I30, borrados, ADS); 18 pruebas | Pasan; cruzado con Sleuth Kit |
| `ntfs/resultados_ntfs.md` | Procedimiento NTFS (20 %) con valores reales, 14 capturas y 7 diagramas Mermaid | Hecho |

## 2. Cobertura del enunciado

| Punto | Peso | Estado |
|---|---|---|
| Localización de archivos en FAT32 | 60 % | Resuelto en `resultados_fat32.md` |
| Entradas faltantes en el Root Directory | 10 % | Resuelto en `resultados_fat32.md` |
| Localización de archivos en NTFS | 20 % | Resuelto con imagen propia en `ntfs/resultados_ntfs.md` (reemplaza los volcados inventados del doc del compañero) |
| Código Python | Bono | Hecho y probado |
| Condiciones de entrega (informe .docx/.pdf + comprimido) | 10 % | Pendiente |

## 3. Revisión del documento NTFS del compañero

**Veredicto:** técnicamente sólido. Se recalcularon todos los offsets, fórmulas, data runs, fixups y entradas `$I30` a partir de los volcados hexadecimales del documento, y coinciden. Los problemas son de ajuste al enunciado y de procedencia de la evidencia.

### Correcciones necesarias

| # | Severidad | Línea aprox. (texto extraído) | Problema | Corrección |
|---|---|---|---|---|
| 1 | Crítico | Portada, partes A–D, conclusiones | Está escrito como un "Laboratorio 3" completo, con instalación de VirtualBox y Kali, unos 38 recuadros de captura vacíos y conclusiones en blanco. El enunciado pide un **procedimiento** dentro del informe del Lab 2. | Extraer solo la localización manual (secciones 9.1–9.9, pasos F1–F10) y la verificación con The Sleuth Kit (E1–E5) como una sección del informe. Quitar "Laboratorio 3" y la ficha. |
| 2 | Crítico | Líneas 25 y 151 | Presenta las salidas como "resultado real obtenido", pero las marcas de tiempo del registro MFT 68 son del 2026-10-11, es decir, se generaron con IA hoy. Las salidas de VirtualBox (lsblk, parted, dd, mmls) no son verificables. | No presentarlas como evidencia propia. Hay que generar la imagen NTFS propia y reemplazar todos los hex y capturas por los reales. |
| 3 | Medio | Parte G (línea 3224 en adelante) | Cita un `analizador_ntfs.py` "entregado con la guía" que no existe ni en el docx ni en la carpeta. | Adjuntarlo y probarlo, o eliminar la Parte G. |
| 4 | Medio | Líneas 3157 y 3218 | `head -8` muestra hasta 0x70, pero la figura pide ver el texto, que está en ~0x170. | Usar `head -32`. |
| 5 | Menor | Líneas 2834 y 2860 | Indica flags `0x10000000` para la carpeta Reportes; el volcado da `20 00 00 10`. | Corregir a `0x10000020` (directorio + archivo). |
| 6 | Menor | Líneas 464 y 325 | El texto dice que el flag de directorio es `0x0003` y la Tabla 8 dice `0x0002`. | Aclarar: `0x0003` = en uso (0x1) + directorio (0x2). |
| 7 | Menor | Línea 168 | Atribuye a `mkntfs` que los archivos de usuario empiecen en el registro 64. | Avisar que los registros 64–77 y los LCN son propios de esa imagen y cambian con otra herramienta o driver. |
| 8 | Menor | Líneas 823–826 | El orden de la salida de `dd` está invertido. | Primero van "records in/out" y después los "bytes copied". |
| 9 | Menor | Anexo A | Solo ofrece la vía con `sudo` y `losetup`. | Mencionar `mkntfs -F -Q archivo.img`, sin root. Ojo: sin tabla de particiones, el inicio de partición es 0, no 2048. |

### Lo que está bien (verificado)

- Offsets del Boot Sector NTFS (0x0B, 0x0D, 0x28, 0x30, 0x38, 0x40 con signo, 0x44) y sus cálculos.
- Fórmulas de sector: `$MFT` = 2048 + 4×8 = 2080; registro N = 2080 + 2N.
- Cabecera de registro MFT, fixups, códigos de atributo (0x10, 0x30, 0x80, 0x90, 0xA0, 0xB0).
- Decodificación de data runs con desplazamientos con signo.
- Estructura de las entradas `$I30` (INDEX_ROOT / INDX).
- Tablas comparativas FAT32 vs NTFS.

### Límite de la prueba

En este equipo no están instaladas las herramientas NTFS (`mkntfs`, `fls`, `istat`), así que la revisión se hizo recalculando a mano los volcados del documento. No se ejecutaron los comandos.

## 4. Lo que se hizo (FAT32)

Detalle completo en `resultados_fat32.md`. Resumen:

- **Boot sector:** 512 bytes/sector, 1 sector/cluster, 1160 sectores reservados, 2 FAT de 7612 sectores, cluster raíz 2.
- **Root Directory:** sector 1160 + 2·7612 + (2−2)·1 = **16384** (byte 8 388 608).
- **Respuesta del 10 %:** con 1 sector por cluster, cada cluster de la raíz solo admite 16 entradas de 32 bytes, y los nombres largos (LFN) gastan varias entradas cada uno. Por eso la raíz ocupa **4 clusters no contiguos**: 2 → 4190 → 6 → 490095 → EOC. Quien lee solo el sector 16384 ve 5 elementos. Para encontrar el resto hay que seguir la cadena en la FAT.
- **Contenido:** 12 carpetas y 39 archivos. Hay 4 PDF, 5 DOCX, 5 JPG/JPEG, 7 ASM y 1 APK como aplicación. Todas las firmas se verificaron (`%PDF`, `FF D8 FF`, `PK`, texto ASM).
- **Sin `.exe`:** la imagen no tiene `.exe` ni `.doc` binario. Como aplicación se usa `quickshortcutmaker-2-4-0.apk` (y `Mars4_5.jar` como extra).

### Cómo probarlo

```bash
cd ~/Projects/Arquitectura
python3 -m unittest discover -s tests -v       # 35 pruebas, OK
python3 fat32_analyzer.py Arqui22025.img --tree
python3 fat32_analyzer.py Arqui22025.img --find pdf jpg asm docx apk
python3 fat32_analyzer.py arqui.iso            # debe rechazarla (no es FAT32)
dd if=Arqui22025.img bs=512 skip=16384 count=1 | od -A x -t x1z   # ver el Root Directory
```

## 5. Imagen NTFS propia

- Partición NTFS en el sector 2048 (409 600 sectores), clúster de 4096 B, registro MFT de 1024 B.
- `$MFT` en LCN 4 (sector 2080), `$MFTMirr` en LCN 25599. Raíz = registro 5 (sector 2090).
- Ejemplo trabajado: `/Proyectos/2025/Lab2/informe/datos_largo.bin`, que pasa por los registros 5 → 35 → 36 → 37 → 39 → 58. Los datos están en LCN 27161, sector 219336. Verificado contra `istat` de Sleuth Kit.
- `/Muchos` tiene 60 archivos y usa INDEX_ALLOCATION (5 bloques INDX): es el equivalente NTFS de la pregunta del 10 %.
- Incluye un archivo residente (`pequeno.txt`), un ADS (`nota.txt:secreto`) y 2 archivos borrados recuperados con `icat` (el hash coincide).
- Diferencia con el doc del compañero: con el driver `ntfs3` del kernel, los archivos de usuario empiezan en el registro 27, no en el 64. Además, al borrar, `ntfs3` elimina el `$FILE_NAME`, así que los borrados aparecen como `OrphanFile-N`.
- Reconstruir la imagen cambia el hash y las fechas; si se reconstruye, hay que regenerar las capturas con `python3 ntfs/capturas_ntfs.py`.

## 6. Pendientes

- [x] Capturas FAT32 generadas con `capturas.py` (bytes reales) e insertadas en `resultados_fat32.md`.
- [x] Imagen NTFS propia, analizador, pruebas, capturas y procedimiento (`ntfs/`).
- [x] Diagramas Mermaid en ambos resultados (validados con mermaid-cli).
- [ ] Decidir qué usar del doc del compañero: lo recomendable es tomar su parte teórica (sección 3, correcta) y reemplazar sus volcados por los de `ntfs/resultados_ntfs.md`.
- [x] Informe final en `informe/` (.docx + .pdf, 53 páginas). Falta: nombres, documentos y profesor en la portada. Los diagramas Mermaid van como imagen.
- [x] Comprimido en `entrega/Lab2_FAT32_NTFS.zip` (10 MB, 40 archivos, sin imágenes `.img` ni `__pycache__`; `ntfs/build_ntfs_image.sh` regenera la imagen NTFS). Regenerarlo después de completar la portada.
- [ ] Confirmar la fecha de entrega: el enunciado dice 6 de octubre de 2025.

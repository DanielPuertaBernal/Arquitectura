# Laboratorio 2: Exploración de discos y sistemas de archivos FAT32 y NTFS

Localización manual de archivos y carpetas en imágenes FAT32 y NTFS (sin montarlas), con analizadores en Python que comprueban los cálculos.

## Contenido

| Ruta | Qué es |
|---|---|
| `informe/Informe_Laboratorio2_FAT32_NTFS.pdf` | Informe final (también en `.docx`) |
| `GUIA_ESTUDIO.md` | Guía de estudio con conceptos, diagramas y preguntas probables |
| `enunciado/` | Enunciado oficial del laboratorio |
| `fat32_analyzer.py`, `tests/` | Analizador FAT32 y sus pruebas |
| `ntfs/` | Analizador NTFS, script que crea la imagen, pruebas y resultados |
| `capturas/`, `ntfs/capturas/` | Figuras tipo editor hexadecimal generadas desde los bytes reales |
| `capturas.py`, `ntfs/capturas_ntfs.py` | Generadores de esas figuras |
| `resultados_fat32.md`, `ntfs/resultados_ntfs.md` | Resultados detallados |
| `informe/build_informe.js` | Genera el informe `.docx` (requiere `npm install docx`) |

## Imágenes de disco

Las imágenes superan el límite de 100 MB de GitHub, así que se publican comprimidas en el Release [`lab2-imagenes`](https://github.com/DanielPuertaBernal/Arquitectura/releases/tag/lab2-imagenes):

| Imagen | Sistema | Tamaño | Descarga | Destino |
|---|---|---|---|---|
| `Arqui22025.img` | FAT32 | 507 MB (469 MB comprimida) | `Arqui22025.img.zst` | `laboratorio2/` |
| `lab_ntfs.img` | NTFS | 211 MB (2.3 MB comprimida) | `lab_ntfs.img.zst` | `laboratorio2/ntfs/` |

Descargar, descomprimir y verificar (desde `laboratorio2/`):

```bash
gh release download lab2-imagenes -p '*.zst'
zstd -d Arqui22025.img.zst && sha256sum -c Arqui22025.img.sha256
zstd -d lab_ntfs.img.zst -o ntfs/lab_ntfs.img && (cd ntfs && sha256sum -c lab_ntfs.img.sha256)
```

Sin `gh`, se descargan desde la página del Release. La imagen NTFS también se puede recrear con `ntfs/build_ntfs_image.sh`.

Ojo: `arqui.iso` es FAT16 y **no** es la imagen del laboratorio.

## Uso rápido

```bash
cd laboratorio2
python3 fat32_analyzer.py Arqui22025.img --tree
python3 fat32_analyzer.py Arqui22025.img --find pdf jpg asm docx
python3 ntfs/ntfs_analyzer.py ntfs/lab_ntfs.img --tree
python3 -m unittest discover -s tests
(cd ntfs && python3 -m unittest discover -s tests)
```

Para repetir el ejercicio a mano, seguir la sección "Cómo replicar el ejercicio" de `GUIA_ESTUDIO.md`.

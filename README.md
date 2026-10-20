# Arquitectura de Computadores

Laboratorios del curso de Arquitectura de Computadores (UCO, 2025-2).

## Laboratorios

| Carpeta | Tema | Entregable |
|---|---|---|
| [`laboratorio2/`](laboratorio2/) | Exploración de discos y sistemas de archivos FAT32 y NTFS | [Informe PDF](laboratorio2/informe/Informe_Laboratorio2_FAT32_NTFS.pdf) |

Cada carpeta tiene su propio `README.md` con el contenido, cómo obtener los archivos grandes y cómo ejecutar el código.

## Archivos grandes

Las imágenes de disco superan el límite de 100 MB por archivo de GitHub, así que no están en el historial de git. Se publican comprimidas como assets de un [Release](https://github.com/DanielPuertaBernal/Arquitectura/releases) por laboratorio.

## Requisitos

- Python 3.10+ (los analizadores solo usan la biblioteca estándar).
- `zstd` para descomprimir las imágenes.
- Node.js y `npm install docx` solo si se quiere regenerar el informe `.docx`.

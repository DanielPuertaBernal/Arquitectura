# Arquitectura de Computadores

Laboratorios del curso de Arquitectura de Computadores (UCO, 2025-2).

## Laboratorios

| Carpeta | Tema | Entregable |
|---|---|---|
| [`laboratorio1/`](laboratorio1/) | Exploración de discos y sistemas de archivos FAT32 y NTFS | [Informe PDF](laboratorio1/informe/Informe_Laboratorio2_FAT32_NTFS.pdf) |
| [`laboratorio2/`](laboratorio2/) | Construcción de un clúster con Docker Swarm | Guía de laboratorio (en curso, ver [guía de trabajo](laboratorio2/GUIA_TRABAJO.md)) |

Cada carpeta tiene su propio `README.md` con el contenido, cómo obtener los archivos grandes y cómo ejecutar el código.

## Archivos grandes

Las imágenes de disco superan el límite de 100 MB por archivo de GitHub, así que no están en el historial de git. Se publican comprimidas como assets de un [Release](https://github.com/DanielPuertaBernal/Arquitectura/releases) por laboratorio.

## Requisitos

- Python 3.10+ (los analizadores solo usan la biblioteca estándar).
- `zstd` para descomprimir las imágenes.
- Node.js y `npm install docx` solo si se quiere regenerar el informe `.docx`.

## Contenidos de clase

La carpeta [`contenidos-clase/`](contenidos-clase/) reúne las diapositivas vistas en el curso, en orden de clase:

| N.º | Tema |
|---|---|
| 01 | Historia del computador |
| 02 | Organización de computadoras |
| 03 | CPU |
| 04 | Lenguaje ensamblador: fundamentos y aplicaciones |
| — | Repaso Assembler · Instrucciones MIPS (`.xlsx`) |
| 05 | ALU |
| 06 | RISC, CISC y elementos de microarquitectura |
| 07 | Ejecución de instrucciones |
| 08 | Pipelining y multicore |
| 09 | Jerarquía de memoria · Raspberry 3 y Raspberry 4 |
| 10 | Unidades de almacenamiento y sistemas de archivos · 10.1 Sistema de archivos FAT16 |
| 11 | Discos de estado sólido (11 y 11.1) |
| 12 | Entrada y salida · 12.1 IRQ |
| 13 | Protocolo I2C |
| 14 | Protocolo SPI |
| 15 | Protocolo USB |

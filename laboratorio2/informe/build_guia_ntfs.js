// Generador de la guia de laboratorio NTFS (enunciado nuevo: "Exploración de discos y NTFS").
// Uso: cd informe && NODE_PATH=<ruta>/node_modules node build_guia_ntfs.js   (requiere: npm install docx)
// Antes: ntfs/build_guia_image.sh (imagen) y ntfs/capturas_guia.py (figuras).
// Salida: Guia_Laboratorio_NTFS.docx
const fs = require("fs");
const path = require("path");
const {
  ROOT, H1, H2, H3, B, P, numList, gap, note, table, figure, cover, ref, writeDocx, counts,
} = require("./docx_comun");

const CAP = "ntfs/capturas_guia/";
const hasTsk = fs.existsSync(path.join(ROOT, CAP, "g13_tsk_fsstat.png"));

// =====================================================================
// PORTADA (replica de la plantilla UCO)
// =====================================================================
const coverChildren = cover(["GUÍA DE LABORATORIO", "ARQUITECTURA DE COMPUTADORES"], "Exploración de discos y NTFS");

// =====================================================================
// CUERPO
// =====================================================================
const body = [];
const add = (...x) => x.forEach((e) => Array.isArray(e) ? body.push(...e) : body.push(e));

// ---------------- Introduccion y objetivos ----------------
add(
  H1("Introducción"),
  P("Esta guía enseña a recorrer por dentro un volumen NTFS sin montarlo: se parte del sector de arranque, se calcula dónde está la tabla maestra de archivos (MFT), se busca el registro de un archivo y se llega a su contenido. Cada valor se obtiene a mano con un editor hexadecimal y se comprueba con una herramienta independiente."),
  P("Todo el procedimiento se realizó sobre `lab_ntfs_guia.img`, una imagen de disco de laboratorio con un MBR y una partición NTFS de 200 MiB. Quien siga la guía con la misma imagen debe obtener exactamente los mismos números; con otra imagen, los pasos son los mismos y solo cambian los valores."),

  H1("Objetivos"),
  H2("Objetivo general"),
  P("Comprender cómo NTFS organiza la información de un volumen, localizando los metadatos y el contenido de un archivo a partir de los bytes del disco."),
  H2("Objetivos específicos"),
  B("Explicar la arquitectura general de NTFS y sus principales estructuras de metadatos."),
  B("Identificar el sector de arranque del volumen NTFS y analizar sus campos en hexadecimal."),
  B("Comparar la función del directorio raíz en FAT con el mecanismo de organización de directorios en NTFS."),
  B("Localizar los registros de metadatos de archivos mediante la MFT."),
  B("Interpretar los atributos que describen un archivo y determinar cómo se localizan sus datos."),
  B("Documentar un procedimiento técnico reproducible mediante evidencias, capturas y análisis hexadecimal."),
);

// ---------------- Fundamentos ----------------
add(
  H1("Fundamentos teóricos de NTFS"),
  H2("Sistema de archivos"),
  P("Un sistema de archivos es el conjunto de estructuras y reglas que usa el sistema operativo para guardar, nombrar y recuperar información en un dispositivo. Sin él, un disco sería solo una secuencia de bytes: el sistema de archivos decide qué espacio ocupa cada archivo, guarda sus metadatos (nombre, tamaño, fechas, permisos) y organiza los archivos en carpetas."),
  H2("NTFS"),
  P("NTFS (New Technology File System) es el sistema de archivos nativo de Windows desde Windows NT y lo usan todas las versiones actuales de Windows y Windows Server. Linux lo lee y escribe con los controladores `ntfs3` y `ntfs-3g`, y macOS lo lee. A diferencia de FAT, NTFS tiene registro de transacciones (journaling), permisos por archivo, nombres Unicode largos, compresión y cifrado (Microsoft, s. f.-a)."),
  ...table("Diferencias entre FAT16, FAT32 y NTFS", ["Característica", "FAT16", "FAT32", "NTFS"], [
    ["Estructura principal", "FAT de 16 bits", "FAT de 32 bits", "MFT: un registro por archivo"],
    ["Tamaño máximo de archivo", "2 GB (4 GB con clusters de 64 KB)", "4 GB - 1 byte", "16 TB o más (límite práctico de la implementación)"],
    ["Directorio raíz", "Zona fija de tamaño fijo", "Cadena de clusters, como una carpeta", "Registro 5 de la MFT"],
    ["Ubicación de los datos", "Cadena en la FAT", "Cadena en la FAT", "Data runs o dentro del registro"],
    ["Permisos y journaling", "No", "No", "Sí (ACL y $LogFile)"],
    ["Nombres", "8.3 (+ nombres largos)", "8.3 (+ nombres largos)", "Unicode, hasta 255 caracteres"],
  ], [2100, 2200, 2300, 2760]),
  H2("Metadatos"),
  P("Los metadatos son datos sobre los datos: describen un archivo sin ser parte de su contenido. Son necesarios porque, sin saber el nombre, el tamaño y la ubicación de un archivo, el sistema no podría encontrarlo ni protegerlo."),
  H2("Sectores, clusters, archivos y directorios"),
  P("El **sector** es la unidad mínima de lectura del disco (512 bytes en esta imagen). El **cluster** agrupa varios sectores y es la unidad mínima que se asigna a un archivo (8 sectores = 4096 bytes). Un **archivo** ocupa uno o más clusters, o ninguno si es tan pequeño que cabe en su registro de la MFT. Un **directorio** es un archivo especial cuyo contenido es un índice de nombres que apuntan a otros registros."),
  H2("MFT, atributos y registros de directorio"),
  B("**MFT (Master File Table).** Es la tabla central de NTFS. Tiene un registro de tamaño fijo (1024 bytes) por cada archivo y carpeta, y es en sí misma un archivo: el registro 0 (`$MFT`) describe dónde está la propia MFT."),
  B("**Atributos.** Todo lo que se sabe de un archivo se guarda como atributos dentro de su registro: `$STANDARD_INFORMATION` (fechas), `$FILE_NAME` (nombre y carpeta padre), `$DATA` (contenido), entre otros. Un atributo es **residente** si su contenido está dentro del registro y **no residente** si el registro solo guarda dónde están sus clusters."),
  B("**Registros de directorio.** Una carpeta guarda sus entradas en los atributos de índice `$INDEX_ROOT` y, si no caben, `$INDEX_ALLOCATION`. Cada entrada tiene el nombre del hijo y el número de su registro en la MFT."),
  P("Por eso NTFS no guarda todo en una sola estructura: el nombre y las fechas están en atributos del registro, el índice de la carpeta padre apunta a ese registro, y el contenido puede estar dentro del registro o en clusters aparte, según su tamaño."),
  ...figure("informe/diagramas/ntfs_d2.png", "Organización lógica del disco y del volumen NTFS de la imagen", 3.0, 7.0),
);

// ---------------- Herramientas ----------------
add(
  H1("Herramientas, materiales y precauciones"),
  ...table("Herramientas utilizadas", ["Herramienta", "Uso en la guía"], [
    ["Imagen `lab_ntfs_guia.img` (201 MiB)", "Disco de laboratorio: MBR + partición NTFS desde el sector 2048"],
    ["Editor hexadecimal (GHex, HxD o `xxd`)", "Leer y señalar los bytes de cada estructura"],
    ["Python 3 y `ntfs/ntfs_analyzer.py`", "Analizador propio (sin dependencias) que repite los cálculos para verificarlos"],
    ["The Sleuth Kit (`mmls`, `fsstat`, `fls`, `istat`, `icat`) o Autopsy", "Contraste con una herramienta forense independiente"],
    ["`fsutil fsinfo ntfsinfo` (Windows)", "Alternativa para ver los parámetros de un volumen NTFS montado"],
  ], [3800, 5560], { mono: [] }),
  H2("Obtener la imagen"),
  ...numList([
    "Descargar `lab_ntfs.img.zst` del Release `lab2-imagenes` del repositorio y descomprimirla en `laboratorio2/ntfs/` con `zstd -d`.",
    "Verificar la integridad con `sha256sum -c lab_ntfs.img.sha256`.",
    "Ejecutar `ntfs/build_guia_image.sh`: copia la imagen, monta la partición sin privilegios de administrador (`udisksctl`) y crea `LAB_NTFS.txt` en la raíz. El resultado es `lab_ntfs_guia.img`.",
  ]),
  ...note("Precaución.", [
    "Todo el análisis se hace sobre una imagen de laboratorio, nunca sobre un disco real.",
    "No se deben modificar el sector de arranque, la MFT ni otros metadatos de un disco con información.",
    "El editor hexadecimal se abre en modo de solo lectura cuando sea posible.",
  ]),
);

// ---------------- Parte 2: VBR ----------------
add(
  H1("Análisis hexadecimal del sector de arranque"),
  H2("MBR y sector de arranque del volumen (VBR)"),
  P("Hay que distinguir dos estructuras. El **MBR** (Master Boot Record) es el primer sector del **disco**: tiene código de arranque y la tabla de particiones. El **VBR** o sector de arranque NTFS es el primer sector del **volumen**: tiene los parámetros que permiten interpretar el sistema de archivos, entre ellos la ubicación de la MFT. Lo que interesa para entender NTFS es el VBR."),
  P("En esta imagen el MBR indica que la partición NTFS empieza en el sector 2048. Ese desplazamiento es **V**, y hay que sumarlo a todas las posiciones del volumen."),
  ...figure(CAP + "g01_mbr.png", "MBR del disco (sector 0): la partición NTFS empieza en el sector 2048", 5.6, 6.6),
  ...note("Desplazamiento del volumen:", ["V = 2048 sectores x 512 bytes = 1 048 576 bytes = 0x100000"], true),
  H2("Procedimiento"),
  ...numList([
    "Abrir `lab_ntfs_guia.img` en el editor hexadecimal.",
    "Ir al offset 0 (MBR) y leer la entrada de partición en 0x1BE: tipo `07` (NTFS) y LBA inicial en 0x1C6.",
    "Calcular V = LBA inicial x 512 e ir a ese offset (0x100000): allí empieza el VBR.",
    "Examinar el rango 0x00 a 0x1FF relativo al inicio del volumen y registrar los campos de la tabla siguiente.",
    "Interpretar cada campo según su tamaño y en orden little-endian (el byte menos significativo va primero).",
    "Contrastar los valores con el analizador o con `fsstat`.",
  ]),
  ...note("Comando equivalente en terminal:", ["xxd -s 0x100000 -l 512 lab_ntfs_guia.img"], true),
  ...figure(CAP + "g02_vbr.png", "Sector de arranque NTFS (VBR) en el offset 0x100000, con los campos señalados", 5.6, 7.2),
  ...table("Campos del sector de arranque NTFS de la imagen", ["Offset", "Campo", "Bytes (little-endian)", "Interpretación"], [
    ["0x03-0x0A", "OEM ID", "4E 54 46 53 20 20 20 20", "'NTFS    ': identifica el formato"],
    ["0x0B-0x0C", "Bytes por sector", "00 02", "0x0200 = 512"],
    ["0x0D", "Sectores por cluster", "08", "8 (cluster = 4096 bytes)"],
    ["0x28-0x2F", "Total de sectores", "FF 3F 06 00 00 00 00 00", "0x63FFF = 409 599 (200 MiB)"],
    ["0x30-0x37", "LCN inicial de $MFT", "04 00 00 00 00 00 00 00", "Cluster 4"],
    ["0x38-0x3F", "LCN inicial de $MFTMirr", "FF 63 00 00 00 00 00 00", "Cluster 0x63FF = 25 599"],
    ["0x40", "Tamaño de registro MFT", "F6", "-10 con signo: 2^10 = 1024 bytes"],
    ["0x48-0x4F", "Número de serie", "3F B0 2D 7F 48 DF 3B 0B", "0B3BDF487F2DB03F"],
    ["0x1FE-0x1FF", "Firma de arranque", "55 AA", "Sector de arranque válido"],
  ], [1300, 2300, 2900, 2860], { mono: [0, 2] }),
  H2("Interpretación del byte 0x40"),
  P("El campo 0x40 no es directamente un tamaño. Si el valor, leído con signo, es positivo, indica cuántos clusters ocupa un registro. Si es negativo, el tamaño es 2 elevado al valor absoluto, en bytes. Aquí `F6` vale -10, así que cada registro mide 2^10 = **1024 bytes**. Leerlo como 246 clusters sería un error."),
  ...figure(CAP + "g10_analizador_boot.png", "Verificación del MBR y del sector de arranque con el analizador", 5.6, 5.0),
  P("**Resultado esperado:** reconocer el VBR por la firma `NTFS` y `55 AA`, y saber que con bytes por sector, sectores por cluster y LCN de `$MFT` ya se puede ubicar la MFT."),
);

// ---------------- Parte 3: raiz ----------------
add(
  H1("Comparación entre el directorio raíz FAT y NTFS"),
  ...table("Directorio raíz en FAT y en NTFS", ["Característica", "FAT16/FAT32", "NTFS"], [
    ["Registro de archivos", "Entrada de directorio de 32 bytes", "Registro de la MFT de 1024 bytes"],
    ["Directorio raíz", "FAT16: zona fija tras las FAT. FAT32: cadena de clusters", "Registro MFT número 5 (`.`, también llamado $Root)"],
    ["Organización", "Entradas consecutivas", "`$INDEX_ROOT` y, si no cabe, `$INDEX_ALLOCATION` (árbol B)"],
    ["Metadatos", "Campos fijos de la entrada", "Atributos del registro"],
    ["Localización del contenido", "Cluster inicial y cadena FAT", "Atributo `$DATA` y sus data runs"],
  ], [2300, 3400, 3660]),
  H2("Procedimiento"),
  ...numList([
    "Calcular OffsetMFT = V + LCN de $MFT x C = 1 048 576 + 4 x 4096 = 1 064 960 (0x104000).",
    "Calcular el offset del registro 5: 0x104000 + 5 x 1024 = 1 070 080 (0x105400).",
    "Comprobar la firma `FILE` al inicio del registro y que los flags en 0x16 valen `03 00` (en uso + directorio).",
    "Recorrer los atributos desde el offset indicado en 0x14. Cada atributo empieza con su tipo (4 bytes) y su longitud (4 bytes).",
    "Ubicar `$INDEX_ROOT` (tipo 0x90). Si su flag en el encabezado del índice vale 01, el directorio es grande y continúa en `$INDEX_ALLOCATION` (tipo 0xA0).",
    "Leer el data run de `$INDEX_ALLOCATION` para ubicar los bloques `INDX` y buscar allí el nombre del archivo.",
  ]),
  ...figure(CAP + "g04_raiz_registro5_1.png", "Registro 5 (raíz): firma FILE, $INDEX_ROOT y $INDEX_ALLOCATION", 5.6, 7.2),
  P("En la imagen, `$INDEX_ROOT` del registro 5 tiene la bandera de índice grande, y `$INDEX_ALLOCATION` es no residente: su data run `21 01 05 19` indica 1 cluster desde el LCN 0x1905 = 6405. El bloque INDX está en V + 6405 x 4096 = 0x1A05000 (sector 53 288)."),
  P("Cada entrada del índice tiene la referencia al registro del archivo (6 bytes de número + 2 de secuencia), la longitud de la entrada y una copia del `$FILE_NAME` del hijo: registro padre, fechas, tamaño y nombre en UTF-16LE."),
  ...figure(CAP + "g05_raiz_indx_lab.png", "Entrada de LAB_NTFS.txt en el bloque INDX de la raíz: apunta al registro 120", 5.6, 4.6),
  H2("Pregunta de análisis"),
  P("**¿Qué ventajas ofrece que NTFS represente el directorio raíz como un registro de la MFT?** En FAT32 la raíz se encuentra con el cluster que indica el Boot Sector y su cadena en la FAT; en nuestra imagen FAT32 del laboratorio anterior esa cadena fueron cuatro clusters no contiguos (2, 4190, 6 y 490 095). En NTFS la raíz es un registro más: se ubica con la misma fórmula que cualquier archivo, tiene los mismos atributos (fechas, permisos, índice) y su índice crece con `$INDEX_ALLOCATION` sin límite fijo de entradas. No hay casos especiales en el código ni una zona reservada que se pueda llenar."),
);

// ---------------- Parte 4: MFT y registro ----------------
add(
  H1("Procedimiento para localizar la MFT y un registro de archivo"),
  H2("Preparación del archivo de prueba"),
  P("En la raíz del volumen se creó `LAB_NTFS.txt` con el contenido siguiente (UTF-8, saltos de línea LF):"),
  ...note("Contenido de LAB_NTFS.txt:", [
    "Arquitectura del Computador",
    "Laboratorio de sistemas de archivos NTFS",
    "Archivo de prueba para análisis hexadecimal",
  ]),
  ...table("Datos del archivo de prueba", ["Dato", "Valor"], [
    ["Nombre", "`LAB_NTFS.txt`"],
    ["Ubicación", "Raíz del volumen (`/LAB_NTFS.txt`)"],
    ["Tamaño exacto", "114 bytes (la `á` ocupa 2 bytes en UTF-8)"],
    ["Fecha de modificación", "2026-10-24 11:10:32 (UTC-5)"],
    ["Registro MFT", "120 (secuencia 2)"],
  ], [3000, 6360]),
  H2("Cálculo de la posición de la MFT"),
  P("Del sector de arranque se toman B = 512 bytes por sector, S = 8 sectores por cluster y LCN de $MFT = 4."),
  ...note("Fórmulas con los valores de la imagen:", [
    "C = B x S = 512 x 8 = 4096 bytes",
    "OffsetMFT = V + (LCN_MFT x C) = 1 048 576 + (4 x 4096) = 1 064 960 bytes = 0x104000",
  ], true),
  P("Si se analiza una imagen del volumen solo (sin MBR), V = 0. En el offset 0x104000 debe aparecer la firma `FILE` del registro 0 (`$MFT`). Su atributo `$DATA` muestra un único data run (`12 20 01 04`: 288 clusters desde el LCN 4), es decir, la MFT es contigua y la fórmula directa sirve para cualquier registro de esta imagen."),
  ...figure(CAP + "g03_mft_registro0.png", "Registro 0 ($MFT) en OffsetMFT: atributo $DATA con un solo data run", 5.6, 7.2),
  H2("Identificación del registro MFT"),
  ...numList([
    "Obtener el número de registro del archivo. Con The Sleuth Kit, `fls -o 2048 lab_ntfs_guia.img` muestra la línea `r/r 120-128-2: LAB_NTFS.txt`: registro 120, atributo tipo 128 (`$DATA`) con identificador 2. A mano, se obtiene de la entrada del índice de la raíz (figura anterior): referencia `78 00 00 00 00 00` = 120.",
    "Tomar R = 1024 bytes (byte 0x40 del VBR).",
    "Calcular el offset del registro con la fórmula de abajo.",
    "Ir a ese offset en el editor y verificar la firma `FILE`.",
    "Interpretar la cabecera y recorrer los atributos hasta el marcador `FF FF FF FF`.",
  ]),
  ...note("Offset del registro 120:", [
    "Offset_registro = OffsetMFT + (N x R) = 1 064 960 + (120 x 1024) = 1 187 840 bytes = 0x122000",
  ], true),
  ...table("Cabecera del registro 120", ["Offset", "Bytes", "Significado"], [
    ["0x00", "46 49 4C 45", "Firma `FILE`"],
    ["0x04", "2A 00 / 03 00", "Offset y cantidad de entradas de la USA (fixup)"],
    ["0x10", "02 00", "Número de secuencia: 2 (el registro se reutilizó una vez)"],
    ["0x12", "01 00", "Enlaces: 1"],
    ["0x14", "30 00", "Primer atributo en 0x30"],
    ["0x16", "01 00", "Flags: en uso, archivo (no directorio)"],
    ["0x18", "18 02 00 00", "Bytes usados: 536 de 1024"],
  ], [1300, 2300, 5760], { mono: [0, 1] }),
  ...note("Fixup (USA):", [
    "Los dos últimos bytes de cada sector del registro se reemplazan en disco por un número de control.",
    "Los valores originales están en la USA; hay que restaurarlos antes de leer datos que crucen esa posición.",
  ]),
  ...figure(CAP + "g06_lab_registro.png", "Registro 120 (LAB_NTFS.txt): cabecera y atributos", 5.6, 6.4),
);

// ---------------- Atributos y datos ----------------
add(
  H1("Análisis de los atributos y localización de los datos"),
  H2("Atributos del registro"),
  ...table("Atributos encontrados en el registro 120", ["Offset", "Tipo", "Atributo", "Contenido en la imagen"], [
    ["0x30", "0x10", "$STANDARD_INFORMATION", "Fechas de creación, modificación y acceso (2026-10-24 16:10:32 UTC) y atributos DOS"],
    ["0x90", "0x30", "$FILE_NAME", "Nombre `LAB_NTFS.txt`, padre = registro 5 (raíz), tamaño 114"],
    ["0x108", "0x80", "$DATA", "Residente: los 114 bytes del archivo"],
    ["0x198", "0xD0", "$EA_INFORMATION", "Resumen de los atributos extendidos"],
    ["0x1B8", "0xE0", "$EA", "Atributos extendidos `$LXUID`, `$LXGID`, `$LXMOD` (dueño y permisos de Linux)"],
  ], [900, 900, 2600, 4960], { mono: [0, 1] }),
  P("No aparece `$ATTRIBUTE_LIST` (tipo 0x20): solo se crea cuando los atributos no caben en un registro y hay que repartirlos en registros de extensión. Aquí los cinco atributos usan 536 de los 1024 bytes."),
  P("Los atributos `$EA` los añadió el controlador `ntfs3` de Linux al crear el archivo. Son un ejemplo real de atributos extendidos, que el análisis manual debe saber reconocer."),
  H2("Archivo residente y no residente"),
  P("El byte 0x08 de cada atributo indica si es residente (`00`) o no residente (`01`). Hay que comprobarlo siempre: no se debe suponer que todo archivo pequeño es residente."),
  ...figure("informe/diagramas/ntfs_d5.png", "Decisión entre contenido residente y no residente", 4.0, 4.6),
  H3("Caso A: archivo residente (LAB_NTFS.txt)"),
  P("El `$DATA` del registro 120 es residente: tamaño del contenido `72 00 00 00` = 114 bytes, que comienza 0x18 bytes después del inicio del atributo. Los datos están en el offset 0x122000 + 0x108 + 0x18 = **0x122120** (1 188 128). No hay que buscar ningún cluster: el contenido está dentro del registro."),
  ...figure(CAP + "g07_lab_datos_residentes.png", "Contenido de LAB_NTFS.txt dentro del registro 120", 5.6, 4.4),
  P("**Verificación:** la columna ASCII muestra `Arquitectura del Computador`, `0A` (salto de línea), `Laboratorio de sistemas de archivos NTFS`, y `C3 A1` es la `á` en UTF-8. Son 114 bytes, igual al tamaño del archivo original, y el contenido extraído con el analizador es idéntico byte a byte al texto original (SHA-256 `ffef8fb0bb1ef274...`)."),
  H3("Caso B: archivo no residente (datos_largo.bin)"),
  P("Para mostrar el otro caso se usa `/Proyectos/2025/Lab2/informe/datos_largo.bin` (39 000 bytes, registro 58). Su `$DATA` es no residente: el registro solo guarda el tamaño y una lista de data runs."),
  ...figure(CAP + "g08_no_residente_runs.png", "Registro 58: $DATA no residente con su data run", 5.6, 3.6),
  P("**Cómo leer un data run.** El primer byte se divide en dos: el dígito bajo es cuántos bytes ocupa la longitud y el alto, cuántos ocupa el desplazamiento. En `21 0A 19 6A`: `1` byte de longitud (`0A` = 10 clusters) y `2` bytes de desplazamiento (`19 6A` en little-endian = 0x6A19 = 27 161). Un byte `00` termina la lista. Si hubiera más runs, cada desplazamiento es relativo al LCN del run anterior y con signo."),
  P("**VCN y LCN.** El VCN (Virtual Cluster Number) numera los clusters dentro del archivo (0, 1, 2...). El LCN (Logical Cluster Number) es el número del cluster dentro del volumen. Los data runs traducen uno en otro: aquí los VCN 0 a 9 corresponden a los LCN 27 161 a 27 170."),
  ...note("Posición del primer cluster de datos:", [
    "Offset = V + (LCN x C) = 1 048 576 + (27 161 x 4096) = 112 300 032 bytes = 0x6B19000",
  ], true),
  ...figure(CAP + "g09_no_residente_cluster.png", "Primer cluster de datos_largo.bin en el LCN 27161", 5.6, 3.0),
  ...figure(CAP + "g12_analizador_runs.png", "Registro 58 con el analizador: data run, VCN y LCN", 5.6, 5.0),
);

// ---------------- Evidencias ----------------
add(
  H1("Evidencias y tablas de valores"),
  ...table("Resumen de posiciones calculadas y verificadas", ["Estructura", "Fórmula", "Offset", "Verificación"], [
    ["MBR", "0", "0x0", "Partición tipo 07 desde el sector 2048"],
    ["VBR", "V = 2048 x 512", "0x100000", "OEM 'NTFS' y firma 55 AA"],
    ["$MFT (registro 0)", "V + 4 x 4096", "0x104000", "Firma FILE"],
    ["Raíz (registro 5)", "OffsetMFT + 5 x 1024", "0x105400", "FILE, flags 03"],
    ["INDX de la raíz", "V + 6405 x 4096", "0x1A05000", "Firma INDX, entrada de LAB_NTFS.txt"],
    ["LAB_NTFS.txt (registro 120)", "OffsetMFT + 120 x 1024", "0x122000", "FILE, $DATA residente"],
    ["Contenido de LAB_NTFS.txt", "registro + 0x108 + 0x18", "0x122120", "Texto conocido, 114 bytes"],
    ["datos_largo.bin (registro 58)", "OffsetMFT + 58 x 1024", "0x112800", "$DATA no residente"],
    ["Datos de datos_largo.bin", "V + 27 161 x 4096", "0x6B19000", "'linea 00000: ...'"],
  ], [2500, 2500, 1600, 2760], { mono: [2] }),
  P("El analizador `ntfs/ntfs_analyzer.py` repite todos los cálculos leyendo la imagen directamente, sin montarla, y llega a los mismos offsets. La figura siguiente muestra el recorrido completo hasta `LAB_NTFS.txt`."),
  ...figure(CAP + "g11_analizador_lab.png", "Recorrido de /LAB_NTFS.txt con el analizador", 5.6, 5.6),
  ...(hasTsk ? [
    P("Con The Sleuth Kit se obtuvieron los mismos valores sin ninguna discrepancia: `fsstat` confirma el número de serie, el cluster 4 de la MFT, el 25 599 de `$MFTMirr`, los registros de 1024 bytes y el directorio raíz en el registro 5; `fls` da el registro 120 de `LAB_NTFS.txt`, e `istat` lista los mismos cinco atributos residentes, con `$DATA` de 114 bytes. Además, el contenido extraído con `icat -o 2048 lab_ntfs_guia.img 120` tiene el mismo SHA-256 (`ffef8fb0bb1ef274...`) que el texto original."),
    ...figure(CAP + "g13_tsk_fsstat.png", "Parámetros del volumen con fsstat", 5.6, 5.0),
    ...figure(CAP + "g14_tsk_fls.png", "Entradas de la raíz con fls", 5.6, 5.0),
    ...figure(CAP + "g15_tsk_istat.png", "Atributos del registro 120 con istat", 5.6, 6.0),
  ] : [
    ...note("Contraste con The Sleuth Kit:", [
      "fsstat -o 2048 lab_ntfs_guia.img",
      "fls -o 2048 lab_ntfs_guia.img",
      "istat -o 2048 lab_ntfs_guia.img 120",
      "icat -o 2048 lab_ntfs_guia.img 120",
    ], true),
  ]),
);

// ---------------- Preguntas ----------------
const qa = (q, a) => [H3(q), P(a)];
add(
  H1("Preguntas de análisis"),
  ...qa("¿Por qué el MBR y el sector de arranque NTFS no son equivalentes?",
    "Están en niveles distintos. El MBR describe el disco completo y hay uno por disco; el VBR describe un volumen y hay uno por partición. En la imagen, el sector 0 es el MBR (tabla de particiones con la entrada tipo 07) y el VBR está en el sector 2048. Si se leyera el sector 0 como VBR no aparecería `NTFS` en 0x03 y todos los cálculos saldrían mal."),
  ...qa("¿Qué información del sector de arranque permite calcular la ubicación inicial de la MFT?",
    "Los bytes por sector (0x0B), los sectores por cluster (0x0D) y el LCN de `$MFT` (0x30), más el desplazamiento V del volumen que da el MBR. Con ellos: OffsetMFT = 1 048 576 + 4 x 512 x 8 = 0x104000, donde se verificó la firma `FILE`. El byte 0x40 da el tamaño de cada registro (1024 bytes) para pasar del registro 0 a cualquier otro."),
  ...qa("¿Por qué no es correcto buscar el directorio raíz de NTFS como si fuera una estructura fija de FAT16?",
    "Porque en NTFS la raíz no está en una zona fija después de las tablas: es el registro 5 de la MFT y su posición depende de dónde esté la MFT. Además su índice crece: en la imagen ya no cabe en `$INDEX_ROOT` y usa un bloque INDX en el LCN 6405, en medio del área de datos. Buscar una zona fija no encontraría nada."),
  ...qa("¿Qué diferencias existen entre un atributo residente y uno no residente?",
    "El residente guarda el contenido dentro del registro (byte 0x08 = 00; tamaño y offset del contenido en 0x10 y 0x14). El no residente guarda solo los VCN, los tamaños y la lista de data runs (byte 0x08 = 01), y el contenido está en clusters aparte. En la imagen, `$DATA` de `LAB_NTFS.txt` (114 bytes) es residente y el de `datos_largo.bin` (39 000 bytes) no lo es; también `$INDEX_ALLOCATION` de la raíz es no residente."),
  ...qa("¿Qué ocurriría si un archivo tiene tantos atributos que no caben en un único registro MFT?",
    "NTFS crea registros de extensión y añade al registro base un atributo `$ATTRIBUTE_LIST` (0x20) que indica en qué registro está cada atributo. Los registros de extensión apuntan al registro base en el campo 0x20 de su cabecera. En el registro 120 no hizo falta: usa 536 de 1024 bytes."),
  ...qa("¿Por qué un nombre de archivo visible en Windows no garantiza que sus datos estén almacenados de forma contigua?",
    "El nombre está en `$FILE_NAME` y la ubicación en los data runs de `$DATA`, que son independientes. Un archivo no residente puede tener varios runs separados si el espacio libre estaba fragmentado al escribirlo. `datos_largo.bin` tiene un solo run, pero la propia raíz muestra que las estructuras de un mismo objeto quedan lejos entre sí: su registro está en 0x105400 y su índice en 0x1A05000."),
  ...qa("¿Qué limitaciones presenta el análisis manual ante fragmentación, compresión, cifrado o atributos extendidos?",
    "Con fragmentación hay que decodificar cada run y sumar desplazamientos relativos con signo; un error en uno desplaza todo lo que sigue. Con compresión los bytes del disco no son el contenido y hay que descomprimir por unidades de 16 clusters. Con cifrado (EFS) el contenido es ilegible sin la clave. Los atributos extendidos y los flujos alternativos (ADS) añaden atributos que el Explorador no muestra: en `LAB_NTFS.txt` aparecieron `$EA_INFORMATION` y `$EA` sin pedirlos. Además, el fixup obliga a corregir los dos últimos bytes de cada sector antes de leer. Para estos casos conviene apoyarse en herramientas como The Sleuth Kit o un analizador propio."),
);

// ---------------- Conclusiones ----------------
add(
  H1("Conclusiones"),
  B("Con cuatro valores del sector de arranque (bytes por sector, sectores por cluster, LCN de `$MFT` y tamaño de registro) y el desplazamiento del volumen se puede ubicar cualquier registro de la MFT."),
  B("El MBR y el VBR cumplen funciones distintas: sin el desplazamiento V que da el MBR, ningún cálculo sobre la imagen del disco es correcto."),
  B("En NTFS la raíz es un registro como cualquier otro (el 5), y su índice crece de `$INDEX_ROOT` a bloques INDX sin límite fijo."),
  B("El contenido de un archivo puede estar dentro de su registro (`LAB_NTFS.txt`) o en clusters que se ubican con los data runs (`datos_largo.bin`); siempre hay que revisar el byte de residencia."),
  B("Todos los offsets calculados a mano coincidieron con los del analizador y con los bytes vistos en el editor hexadecimal."),
);

// ---------------- Referencias ----------------
add(
  H1("Referencias"),
  ref("Carrier, B. (2005). File System Forensic Analysis. Addison-Wesley."),
  ref("Linux kernel documentation. (s. f.). NTFS3 filesystem driver. https://docs.kernel.org/filesystems/ntfs3.html"),
  ref("Microsoft. (s. f.-a). Master File Table (Local File Systems). Microsoft Learn. https://learn.microsoft.com/en-us/windows/win32/fileio/master-file-table"),
  ref("Microsoft. (s. f.-b). How NTFS Works. Microsoft Learn. https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2003/cc781134(v=ws.10)"),
  ref("Microsoft. (s. f.-c). Master Boot Record. Microsoft Learn. https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-2000-server/cc976786(v=technet.10)"),
  ref("Microsoft. (s. f.-d). fsutil fsinfo. Microsoft Learn. https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-fsinfo"),
  ref("Russon, R. y Fledel, Y. (2004). NTFS Documentation. Linux-NTFS Project. https://flatcap.github.io/linux-ntfs/ntfs/"),
  ref("The Sleuth Kit. (s. f.). The Sleuth Kit commands. https://wiki.sleuthkit.org/The-Sleuth-Kit-commands/"),
  ref("The Sleuth Kit. (s. f.). NTFS Implementation Notes. https://wiki.sleuthkit.org/NTFS-Implementation-Notes/"),
);

// ---------------- Declaracion IA ----------------
add(
  H1("Declaración de uso de inteligencia artificial"),
  P("Para esta guía utilizamos un asistente de inteligencia artificial generativa (Claude, de Anthropic) como herramienta de consulta y apoyo. Lo usamos para aclarar conceptos de NTFS, revisar cálculos, recibir sugerencias sobre cómo organizar el documento y repasar la redacción y el código. El análisis, las decisiones y la verificación de los resultados con el editor hexadecimal y las demás herramientas los realizamos y revisamos nosotros, y nos hacemos responsables del contenido de esta guía."),
);

// =====================================================================
// DOCUMENTO
// =====================================================================
writeDocx({
  title: "Laboratorio 2 - Exploración de discos y NTFS",
  coverChildren, body, out: path.join(__dirname, "Guia_Laboratorio_NTFS.docx"),
}).then((out) => {
  const { figN, tabN } = counts();
  console.log("OK", out, "figuras:", figN, "tablas:", tabN, hasTsk ? "(con Sleuth Kit)" : "(sin Sleuth Kit)");
});

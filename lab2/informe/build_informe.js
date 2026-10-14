// Generador del informe del Laboratorio 2 (version corta).
// Uso: cd informe && NODE_PATH=<ruta>/node_modules node build_informe.js   (requiere: npm install docx)
// Salida: Informe_Laboratorio2_FAT32_NTFS.docx
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, Header,
  AlignmentType, BorderStyle, WidthType, LevelFormat, PageNumber, VerticalAlign,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const FONT = "Times New Roman";
const MONO = "Consolas";
const W = 9360; // ancho util (Letter, margenes 1")
const SZ = 24;  // 12 pt

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

// inline: **negrita**, `mono`
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, size: SZ, ...base }));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(new TextRun({ text: tok.slice(2, -2), bold: true, font: FONT, size: SZ, ...base }));
    else out.push(new TextRun({ text: tok.slice(1, -1), font: MONO, size: Math.max((base.size || SZ) - 2, 16), ...base, ...(base.size ? { size: base.size - 2 } : { size: SZ - 2 }) }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, size: SZ, ...base }));
  return out;
}

// Parrafo de cuerpo: 1.5 interlineado, izquierda, sangria de primera linea 0.5"
const P = (text) => new Paragraph({
  children: runs(text), alignment: AlignmentType.LEFT,
  spacing: { after: 0, line: 360 }, indent: { firstLine: 720 },
});
const H1 = (t) => new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 240, after: 0, line: 360 },
  children: [new TextRun({ text: t, bold: true, font: FONT, size: SZ })] });
const H2 = (t) => new Paragraph({ alignment: AlignmentType.LEFT, keepNext: true, spacing: { before: 120, after: 0, line: 360 },
  children: [new TextRun({ text: t, bold: true, font: FONT, size: SZ })] });
const H3 = (t) => new Paragraph({ alignment: AlignmentType.LEFT, keepNext: true, spacing: { before: 60, after: 0, line: 360 },
  children: [new TextRun({ text: t, bold: true, italics: true, font: FONT, size: SZ })] });
const B = (text) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(text), spacing: { after: 0, line: 360 } });
let numCount = 0; const numRefs = [];
function numList(items) {
  const ref = "n" + (numCount++); numRefs.push(ref);
  return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 0, line: 360 } }));
}
const gap = (n = 120) => new Paragraph({ children: [], spacing: { after: n, line: 240 } });

// nota: "Nota." en cursiva + texto, y lineas (formulas/comandos) sangradas, sin recuadro
function note(intro, lines = [], mono = false) {
  const head = new Paragraph({ keepNext: lines.length > 0, spacing: { before: 120, after: 60, line: 360 },
    children: [new TextRun({ text: "Nota. ", bold: true, font: FONT, size: SZ }), ...runs(intro, { bold: true })] });
  return [head, ...lines.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l, font: mono ? MONO : FONT, size: mono ? 20 : SZ })],
    spacing: { after: i === lines.length - 1 ? 160 : 0, line: 300 }, keepLines: true, keepNext: i < lines.length - 1,
    indent: { left: 720 },
  }))];
}

// ---- tablas y figuras APA ----
let figN = 0, tabN = 0;
const capLines = (kind, n, title, keepNext = true) => [
  new Paragraph({ keepNext: true, spacing: { before: 120, after: 0, line: 276 }, children: [new TextRun({ text: `${kind} ${n}`, bold: true, font: FONT, size: SZ })] }),
  new Paragraph({ keepNext, spacing: { after: 80, line: 276 }, children: [new TextRun({ text: title, italics: true, font: FONT, size: SZ })] }),
];
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const line = { style: BorderStyle.SINGLE, size: 8, color: "000000" };
function table(title, headers, rows, widths, opts = {}) {
  const size = opts.size || 20;
  const mono = new Set(opts.mono || []);
  const nr = rows.length;
  const cell = (txt, i, ri) => { // ri = -1 cabecera
    const head = ri === -1;
    const b = { top: line, left: line, right: line, bottom: line }; // tabla tradicional: todos los bordes
    return new TableCell({
      width: { size: widths[i], type: WidthType.DXA }, borders: b,
      margins: { top: 40, bottom: 40, left: 80, right: 80 }, verticalAlign: VerticalAlign.CENTER,
      children: String(txt).split("\n").map((l) => new Paragraph({
        spacing: { after: 0, line: 240 }, alignment: AlignmentType.LEFT, keepNext: ri !== nr - 1,
        children: head ? [new TextRun({ text: l, bold: true, font: FONT, size })]
          : mono.has(i) ? [new TextRun({ text: l, font: MONO, size: size - 2 })] : runs(l, { size }),
      })),
    });
  };
  const t = new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    alignment: AlignmentType.CENTER,
    rows: [
      new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, -1)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, ri)) })),
    ],
  });
  return [...capLines("Tabla", ++tabN, title), t, gap(160)];
}
function figure(file, title, maxWin = 6.0, maxHin = 4.0) {
  const f = path.isAbsolute(file) ? file : path.join(ROOT, file);
  if (!fs.existsSync(f)) throw new Error("falta imagen " + f);
  const { w, h } = pngSize(f);
  let wi = maxWin, hi = (h / w) * wi;
  if (hi > maxHin) { hi = maxHin; wi = (w / h) * hi; }
  return [
    ...capLines("Figura", ++figN, title),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 160 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: Math.round(wi * 96), height: Math.round(hi * 96) },
        altText: { title, description: title, name: path.basename(f) } })] }),
  ];
}

// =====================================================================
// PORTADA (replica de la plantilla UCO)
// =====================================================================
const cl = (t, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0, line: 480 },
  children: [new TextRun({ text: t, font: FONT, size: o.size || SZ, bold: o.bold })] });
const blank = (n = 1) => Array.from({ length: n }, () => cl(""));
const logo = (() => {
  const f = path.join(__dirname, "logo_uco.png");
  const { w, h } = pngSize(f);
  const wi = 3.0, hi = (h / w) * wi;
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0, line: 240 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: Math.round(wi * 96), height: Math.round(hi * 96) },
      altText: { title: "Logo UCO", description: "Universidad Católica de Oriente", name: "logo_uco.png" } })] });
})();
const cover = [
  cl("INFORME DE LABORATORIO"), cl("ARQUITECTURA DE COMPUTADORES"),
  ...blank(2),
  cl("LABORATORIO 2", { bold: true, size: 32 }),
  cl("Exploración de discos y sistemas de archivos FAT32 y NTFS", { bold: true }),
  ...blank(3),
  cl("Nombre del estudiante 1"), cl("Nombre del estudiante 2"), cl("Nombre del estudiante 3"),
  ...blank(3),
  logo,
  ...blank(1),
  cl("UNIVERSIDAD CATÓLICA DE ORIENTE"), cl("FACULTAD DE INGENIERÍAS"), cl("2026"),
];

// =====================================================================
// CUERPO
// =====================================================================
const body = [];
const add = (...x) => x.forEach((e) => Array.isArray(e) ? body.push(...e) : body.push(e));

add(
  H1("Introducción"),
  P("En este laboratorio se recorre a mano el contenido de dos discos: una imagen con formato FAT32 y una imagen NTFS creada para la práctica. Sin montar ninguno de los dos, se calculan posiciones, se leen bytes y se comprueba cada resultado con un editor hexadecimal. Al final, el mismo trabajo se automatiza con scripts en Python."),

  H1("Objetivos"),
  H2("Objetivo general"),
  P("Entender cómo se organizan los datos en un disco, ubicando archivos y carpetas dentro de imágenes FAT32 y NTFS."),
  H2("Objetivos específicos"),
  B("Leer el Boot Sector de FAT32 y calcular dónde está el directorio raíz."),
  B("Encontrar archivos de distintos tipos y dos carpetas en la imagen FAT32."),
  B("Explicar por qué el directorio raíz de FAT32 puede ocupar más de un cluster."),
  B("Crear una imagen NTFS y localizar en ella archivos y carpetas con ayuda de la MFT."),
  B("Automatizar el análisis con scripts en Python."),
);

// ---------------- Conceptos basicos ----------------
add(
  H1("Conceptos básicos"),
  B("**Sector y cluster.** El sector es la unidad mínima de lectura (512 bytes). El cluster es un grupo de sectores y es la unidad mínima que se asigna a un archivo."),
  B("**FAT32.** Usa una tabla (la FAT) que indica, para cada cluster, cuál es el siguiente del mismo archivo. Es simple y la leen casi todos los equipos (Microsoft Corporation, 2000)."),
  B("**NTFS.** Guarda cada archivo y carpeta como un registro en la tabla maestra (MFT). Incluso sus estructuras internas son archivos (Carrier, 2005)."),
  gap(60),
  ...table("Comparación entre FAT32 y NTFS", ["Característica", "FAT32", "NTFS"], [
    ["Estructura principal", "Tabla FAT con punteros a clusters", "MFT: un registro de 1 KB por archivo"],
    ["Directorio raíz", "Cluster indicado en el Boot Sector", "Siempre el registro 5"],
    ["Ubicación de los datos", "Cadena de clusters en la FAT", "Data runs, o dentro del propio registro"],
    ["Nombres", "Formato 8.3 y nombres largos (LFN)", "Hasta 255 caracteres UTF-16"],
    ["Archivo borrado", "Primer byte de la entrada = 0xE5", "Bandera \"en uso\" = 0"],
    ["Permisos y journaling", "No", "Sí"],
  ], [2400, 3400, 3560]),
  ...note("Fórmulas de FAT32 usadas en todo el informe (SPC = sectores por cluster, SPF = sectores por FAT):", [
    "Sector del cluster c = Reservados + NFAT x SPF + (c - 2) x SPC",
    "Sector de la raíz = Reservados + NFAT x SPF + (ClusterRaíz - 2) x SPC",
    "Cluster inicial = (High << 16) | Low",
  ]),
);

// ---------------- Parte 1 FAT32 ----------------
add(
  H1("Parte 1. Localización de archivos en FAT32 (60 %)"),
  P("Se trabajó con la imagen `Arqui22025.img` (507 201 024 bytes, 990 627 sectores), una copia de una memoria microSD sin tabla de particiones: el Boot Sector está en el byte 0. Los valores se obtuvieron con el analizador en Python y se comprobaron con `dd | od`."),
  H2("Boot Sector"),
  ...table("Valores del Boot Sector de la imagen FAT32", ["Campo", "Offset", "Valor"], [
    ["Bytes por sector", "0x0B", "512"],
    ["Sectores por cluster", "0x0D", "1"],
    ["Sectores reservados", "0x0E", "1160"],
    ["Número de FAT", "0x10", "2"],
    ["Sectores por FAT", "0x24", "7612"],
    ["Cluster del directorio raíz", "0x2C", "2"],
  ], [4200, 1800, 3360], { mono: [1] }),
  ...figure("capturas/01_boot_sector.png", "Sector 0 de la imagen con los campos resaltados", 4.0, 3.0),
  H2("Ubicación del directorio raíz"),
  B("Inicio de la zona de datos: 1160 + 2 x 7612 = **16384**."),
  B("Sector de la raíz: 16384 + (2 - 2) x 1 = **16384**, es decir el byte 8 388 608."),
  ...figure("capturas/02_root_dir_inicio.png", "Inicio del directorio raíz (sector 16384)", 4.0, 3.0),
  H2("Procedimiento general"),
  ...numList([
    "Leer el Boot Sector y calcular dónde empieza la zona de datos.",
    "Entrar al directorio (empezando por la raíz) y leer las entradas de 32 bytes. Si hay nombre largo, unir sus partes y comprobar el checksum.",
    "Sacar el cluster inicial con (High << 16) | Low y el tamaño del archivo.",
    "Convertir el cluster a sector con la fórmula del apartado de conceptos.",
    "Seguir la cadena en la FAT hasta el final del archivo.",
    "Comprobar los primeros bytes (la firma del tipo de archivo) con el editor hexadecimal.",
  ]),
  H2("Ejemplo: Documento de Prueba.txt"),
  B("Está en la raíz. Sus entradas de nombre largo se unen en \"Documento de Prueba.txt\"; el nombre corto es `DOCUME~2.TXT`. El checksum (0x87) coincide en las ranuras."),
  B("Cluster inicial: High = 0 y Low = 0x003A, o sea **58**. Tamaño: **67 bytes**."),
  B("Sector: 1160 + 2 x 7612 + (58 - 2) = **16440** (byte 8 417 280)."),
  B("FAT[58] marca fin de cadena, por lo que ocupa un solo cluster. El sector comienza con \"Esto es\", un texto."),
  H2("Archivos encontrados"),
  P("La tabla resume los archivos pedidos. Todas las firmas se verificaron en el primer sector de cada archivo."),
  ...table("Archivos y carpetas localizados en la imagen FAT32", ["Categoría", "Nombre", "Cluster", "Sector", "Tamaño (B)"], [
    ["PDF", "Organización y arquitectura de computadores.pdf", "408694", "425076", "4 902 329"],
    ["PDF", "Montaje_y_mantenimiento_de_equipos.pdf", "418269", "434651", "22 614 880"],
    ["Aplicación", "Mars4_5.jar", "490097", "506479", "4 169 142"],
    ["Aplicación", "quickshortcutmaker-2-4-0.apk", "59", "16441", "2 115 037"],
    ["JPEG", "Arquitecturas.jpg", "485655", "502037", "355 589"],
    ["JPEG", "CPU.jpg", "486350", "502732", "658 430"],
    ["Word", "Instructivo firma institucional.docx", "7", "16389", "372 099"],
    ["Word", "Ordenadores De Placa Reducida.docx", "405883", "422265", "1 439 229"],
    ["Ensamblador", "x2n.asm", "498240", "514622", "419"],
    ["Ensamblador", "ejemplo-saltos.asm", "490093", "506475", "426"],
    ["Ensamblador", "ejemploSuma.asm", "490094", "506476", "92"],
    ["Carpeta", "Personal", "462439", "478821", "0 (carpeta)"],
    ["Carpeta", "Carpeta01", "341518", "357900", "0 (carpeta)"],
  ], [1500, 3900, 1000, 1000, 1960], { size: 20, mono: [2, 3] }),
  B("La imagen no tiene archivos `.exe`; como aplicación se usó un paquete `.apk` (un archivo ZIP con firma `PK`)."),
  B("En total hay 4 PDF, 5 JPEG, 5 Word (.docx) y 7 archivos .asm. El Word del Instructivo está fragmentado (clusters 7 a 57 y 345745 a 346420), por eso hay que seguir la FAT."),
  B("`Personal` contiene `Fotos` (con las imágenes y los .asm de `Carpeta`) y dos PDF; `Carpeta01` contiene `Docu` y el PDF de Montaje."),
  H2("Evidencia en el editor hexadecimal"),
  P("Cada figura muestra la entrada del directorio (nombre largo, nombre 8.3, cluster y tamaño resaltados) y el primer sector de datos con su firma."),
  H3("PDF"),
  P("La primera figura muestra la firma `%PDF-1.3` del primer PDF; la segunda, la entrada y la firma `%PDF-1.4` del segundo."),
  ...figure("capturas/07_pdf_firma.png", "Firma %PDF (25 50 44 46) en el sector 425076", 5.2, 2.4),
  ...figure("capturas/14_pdf_montaje.png", "Entrada y datos de Montaje_y_mantenimiento_de_equipos.pdf", 5.5, 4.0),
  H3("Aplicación"),
  P("El archivo `Mars4_5.jar` (carpeta `CarpeDocu`) empieza con la firma ZIP `50 4B 03 04` en el sector 506479."),
  ...figure("capturas/10_aplicacion_jar.png", "Entrada y datos de la aplicación Mars4_5.jar", 5.5, 4.0),
  H3("Word"),
  P("El documento `.docx` también es un ZIP: su primer sector comienza con `PK`."),
  ...figure("capturas/11_word_docx.png", "Entrada y datos del Word Ordenadores De Placa Reducida.docx", 5.5, 4.0),
  H3("Ensamblador"),
  P("Los `.asm` son texto plano: el contenido se lee en la columna ASCII."),
  ...figure("capturas/12_asm_x2n.png", "Entrada y datos de x2n.asm", 5.5, 4.0),
  ...figure("capturas/13_asm_ejemplosuma.png", "Entrada y datos de ejemploSuma.asm", 5.5, 4.0),
  H3("JPEG"),
  P("Ambas imágenes empiezan con `FF D8 FF`; la segunda es `CPU.jpg`."),
  ...figure("capturas/08_jpg_firma.png", "Firma JPEG en el sector 502037 (Arquitecturas.jpg)", 5.2, 2.4),
  ...figure("capturas/15_jpg_cpu.png", "Entrada y datos de CPU.jpg", 5.5, 4.0),
  H3("Carpetas"),
  P("Un directorio es un cluster de entradas de 32 bytes que empieza con `.` (la propia carpeta) y `..` (el padre)."),
  ...figure("capturas/16_carpeta_carpedocu.png", "Cluster de directorio de CarpeDocu", 5.5, 4.0),
  ...figure("capturas/17_carpeta_carpeta01.png", "Cluster de directorio de Carpeta01", 5.5, 4.0),
);

// ---------------- Parte 2 ----------------
add(
  H1("Parte 2. Problema del Root Directory (10 %)"),
  H2("Respuesta"),
  B("En esta imagen cada cluster mide 512 bytes y solo guarda **16 entradas de 32 bytes**. Los nombres largos usan varias entradas cada uno, así que el cluster se llena rápido."),
  B("En FAT32 la raíz no es una zona fija: es un directorio normal que puede crecer enlazando más clusters en la FAT."),
  B("Esos clusters pueden estar lejos y fuera de orden, por eso al leer solo el sector 16384 se ven apenas 5 entradas de archivo."),
  B("**Solución:** leer la FAT del cluster actual para saber cuál es el siguiente y repetir hasta un valor de fin de cadena (0x0FFFFFF8 o mayor)."),
  H2("Procedimiento"),
  ...numList([
    "Tomar el cluster raíz (2) y leer su sector (16384).",
    "Leer FAT[2] en el byte 1160 x 512 + 2 x 4 = 593 928: el valor es 4190.",
    "Repetir con los clusters siguientes hasta el fin de cadena.",
    "Unir las entradas de todos los clusters.",
  ]),
  ...table("Cadena del directorio raíz", ["Cluster", "Sector", "Siguiente cluster (valor en la FAT)"], [
    ["2", "16384", "4190"],
    ["4190", "20572", "6"],
    ["6", "16388", "490095"],
    ["490095", "506477", "Fin de cadena (0x0FFFFFFF)"],
  ], [2000, 2000, 5360], { mono: [0, 1] }),
  P("La raíz tiene 14 entradas de archivo o carpeta vivas (5 carpetas y 9 archivos) y 2 borradas, repartidas en estos cuatro clusters."),
  P("Los enlaces se leen en la FAT: FAT[2] y FAT[6] en el sector 1160, FAT[4190] y FAT[490095] más adelante."),
  ...figure("capturas/03_fat_sector1160.png", "Sector 1160 (FAT 1) con FAT[2] y FAT[6]", 5.2, 2.4),
  ...figure("capturas/18_raiz_fat_cadena.png", "FAT[4190] = 6 y FAT[490095] = fin de cadena", 5.2, 3.0),
  P("Las entradas de la raíz están repartidas en los clusters 4190, 6 y 490095, además del cluster 2."),
  ...figure("capturas/04_root_cluster4190.png", "Segundo cluster de la raíz (cluster 4190, sector 20572)", 5.2, 4.0),
  ...figure("capturas/19_raiz_clusters_6_490095.png", "Clusters 6 y 490095 del directorio raíz", 5.2, 3.0),
);

// ---------------- Parte 3 NTFS ----------------
add(
  H1("Parte 3. Localización de archivos en NTFS (20 %)"),
  H2("Creación de la imagen"),
  P("Se creó `lab_ntfs.img` (200 MiB) con un script sin permisos de administrador: formatea con `mkntfs` (cluster de 4096 bytes, registro MFT de 1024), copia carpetas y archivos de prueba, y añade un MBR con la partición NTFS en el sector 2048. Antes de desmontar se borraron dos archivos y se añadió un flujo alternativo (ADS)."),
  H2("Procedimiento"),
  ...numList([
    "Leer el MBR (sector 0): la partición NTFS empieza en el sector 2048.",
    "Leer el Boot Sector (sector 2048): 8 sectores por cluster, MFT en el cluster 4, registros de 1024 bytes.",
    "Calcular el sector de un registro: 2080 + 2 x N (el registro N de la MFT).",
    "Leer el registro 5 (raíz) y buscar el nombre en su índice; si el directorio es grande, mirar también los bloques INDX.",
    "Repetir por cada carpeta de la ruta; la entrada indica el número de registro del hijo.",
    "En el registro del archivo mirar el atributo `$DATA`: si es residente, el contenido está dentro; si no, los data runs dan los clusters (sector = 2048 + LCN x 8).",
  ]),
  H2("Ejemplo: /Proyectos/2025/Lab2/informe/datos_largo.bin"),
  ...table("Recorrido de la ruta en la MFT", ["Elemento", "Registro", "Sector"], [
    ["Raíz", "5", "2090"],
    ["Proyectos", "35", "2150"],
    ["2025", "36", "2152"],
    ["Lab2", "37", "2154"],
    ["informe", "39", "2158"],
    ["datos_largo.bin", "58", "2196"],
  ], [4000, 2200, 3160], { mono: [1, 2] }),
  B("El registro 58 tiene `$DATA` **no residente**: tamaño 39 000 bytes y un data run de 10 clusters que empieza en el LCN **27161**."),
  B("Sector de los datos: 2048 + 27161 x 8 = **219336** (del 219336 al 219415)."),
  ...figure("ntfs/capturas/12_analizador_path.png", "Recorrido de la ruta con el analizador", 5.6, 3.6),
  P("Las figuras siguientes muestran el registro 0 con su data run, un bloque INDX y un registro borrado."),
  ...figure("ntfs/capturas/03b_mft_registro0_data.png", "Registro 0 de la MFT: atributo $DATA y data run", 5.0, 4.0),
  ...figure("ntfs/capturas/05_indx_muchos.png", "Bloque INDX del directorio /Muchos", 5.0, 3.6),
  ...figure("ntfs/capturas/09_registro_borrado.png", "Registro 120 borrado (bandera en uso = 0)", 5.0, 4.0),
  H2("Hallazgos"),
  B("**Residente y no residente:** `pequeno.txt` (60 bytes, registro 50) cabe dentro del registro; `datos_largo.bin` no, y usa clusters aparte."),
  B("**Directorio grande:** `/Muchos` (registro 59, 60 archivos) no cabe en `$INDEX_ROOT` y usa `$INDEX_ALLOCATION`, con 5 bloques INDX (sector del primero: 219416)."),
  B("**Archivo borrado:** los registros 120 y 121 quedaron con la bandera \"en uso\" en 0; sus datos siguen en el disco y se recuperaron (el hash coincide con el original). El driver `ntfs3` elimina el nombre, por eso Sleuth Kit los lista como `OrphanFile-120` y `-121`."),
  B("**Flujo alternativo (ADS):** `nota.txt` (registro 51) tiene un segundo `$DATA` llamado `secreto` que el Explorador no muestra."),
  H2("Validación con The Sleuth Kit"),
  P("Los comandos `mmls`, `fsstat`, `fls` e `icat -o 2048` dieron los mismos números de registro y el mismo contenido (hash SHA-256) que el analizador, para las 80 entradas asignadas, incluido el ADS."),
);

// ---------------- Parte 4 Python ----------------
add(
  H1("Parte 4. Código en Python (bono)"),
  B("`fat32_analyzer.py` lee la imagen FAT32 y muestra el Boot Sector, la cadena de la raíz, el árbol de carpetas, los archivos por extensión y los borrados."),
  B("`ntfs/ntfs_analyzer.py` hace lo propio con NTFS: MBR, Boot Sector, registros MFT, índices, rutas, borrados y flujos alternativos."),
  B("Ambos usan solo la biblioteca estándar y no montan la imagen."),
  ...note("Ejemplos de uso de los analizadores:", [
    "python3 fat32_analyzer.py Arqui22025.img --find pdf jpg docx apk asm",
    "python3 -I ntfs/ntfs_analyzer.py ntfs/lab_ntfs.img --path /Proyectos/2025/Lab2/informe/datos_largo.bin",
  ], true),
  P("Resultado de las pruebas automáticas: 35 pruebas en FAT32 y 18 en NTFS, todas correctas."),
);

// ---------------- Conclusiones ----------------
add(
  H1("Conclusiones"),
  B("Con unos pocos datos del Boot Sector (sectores reservados, tamaño de la FAT y cluster raíz) se puede calcular dónde está cualquier archivo de FAT32."),
  B("El directorio raíz de FAT32 es una cadena de clusters, no una zona fija. En la imagen fueron cuatro (2, 4190, 6 y 490095)."),
  B("Algunos archivos y carpetas están fragmentados, así que siempre hay que seguir la FAT."),
  B("En NTFS la búsqueda pasa por la MFT: se llega al archivo por el índice de cada carpeta y se leen sus datos en el registro o en los data runs."),
  B("Borrar un archivo no borra sus datos: en FAT32 solo se marca la entrada y en NTFS se baja la bandera de uso, por lo que se pudieron recuperar."),
  B("Automatizar el análisis y compararlo con Sleuth Kit dio confianza en los resultados obtenidos a mano."),
);

// ---------------- Referencias ----------------
const ref = (t) => new Paragraph({ children: runs(t), alignment: AlignmentType.LEFT, spacing: { after: 0, line: 360 },
  indent: { left: 720, hanging: 720 } });
add(
  H1("Referencias"),
  ref("Brown, R. (1994). Ralf Brown's interrupt list. http://www.ctyme.com/rbrown.htm"),
  ref("Carrier, B. (2005). File System Forensic Analysis. Addison-Wesley."),
  ref("Glendinning, G. A. (2010). The art of assembly language (2nd ed.). No Starch Press."),
  ref("Linux kernel documentation. (s. f.). NTFS3 filesystem driver. https://docs.kernel.org/filesystems/ntfs3.html"),
  ref("Microsoft Corporation. (2000). Microsoft Extensible Firmware Initiative FAT32 File System Specification, Version 1.03. Microsoft."),
  ref("Silberschatz, A., Galvin, P. B. y Gagne, G. (2018). Operating system concepts (10th ed.). Wiley."),
  ref("Tanenbaum, A. S. y Bos, H. (2015). Modern operating systems (4th ed.). Pearson Education."),
  ref("The Sleuth Kit. (s. f.). The Sleuth Kit documentation. https://www.sleuthkit.org/sleuthkit/docs.php"),
);

// ---------------- Declaracion IA ----------------
add(
  H1("Declaración de uso de inteligencia artificial"),
  P("Para este laboratorio utilizamos un asistente de inteligencia artificial generativa (Claude, de Anthropic) como herramienta de consulta y apoyo. Lo usamos para aclarar conceptos de FAT32 y NTFS, revisar cálculos, recibir sugerencias sobre cómo organizar el documento y repasar la redacción y el código. El análisis, las decisiones y la verificación de los resultados con el editor hexadecimal y las demás herramientas los realizamos y revisamos nosotros, y nos hacemos responsables del contenido de este informe."),
);

// =====================================================================
// DOCUMENTO
// =====================================================================
const mkNum = (r) => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] });
const doc = new Document({
  creator: "Laboratorio 2 - Arquitectura de Computadores",
  title: "Laboratorio 2 - Exploración de discos y sistemas de archivos FAT32 y NTFS",
  styles: { default: { document: { run: { font: FONT, size: SZ } } } },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ...numRefs.map(mkNum),
  ] },
  sections: [
    { // portada: margenes de la plantilla, sin encabezado ni pie
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1417, bottom: 1417, left: 1701, right: 1701 } } },
      children: cover,
    },
    { // cuerpo: numero de pagina arriba a la derecha (APA)
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SZ })] })] }) },
      children: body,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "Informe_Laboratorio2_FAT32_NTFS.docx");
  fs.writeFileSync(out, buf);
  console.log("OK", out, "figuras:", figN, "tablas:", tabN);
});

// Helpers compartidos por los generadores .docx del Laboratorio 2 (formato APA y portada UCO).
// Requiere: npm install docx (NODE_PATH apuntando a node_modules).
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
const cover = (titleLines, subtitle) => [
  ...titleLines.map((t) => cl(t)),
  ...blank(2),
  cl("LABORATORIO 2", { bold: true, size: 32 }),
  cl(subtitle, { bold: true }),
  ...blank(3),
  cl("Nombre del estudiante 1"), cl("Nombre del estudiante 2"), cl("Nombre del estudiante 3"),
  ...blank(3),
  logo,
  ...blank(1),
  cl("UNIVERSIDAD CATÓLICA DE ORIENTE"), cl("FACULTAD DE INGENIERÍAS"), cl("2026"),
];

const ref = (t) => new Paragraph({ children: runs(t), alignment: AlignmentType.LEFT, spacing: { after: 0, line: 360 },
  indent: { left: 720, hanging: 720 } });

// Documento: portada sin encabezado + cuerpo con numero de pagina arriba a la derecha (APA)
const mkNum = (r) => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] });
function writeDocx({ title, coverChildren, body, out }) {
  const doc = new Document({
    creator: "Laboratorio 2 - Arquitectura de Computadores",
    title,
    styles: { default: { document: { run: { font: FONT, size: SZ } } } },
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      ...numRefs.map(mkNum),
    ] },
    sections: [
      { // portada: margenes de la plantilla, sin encabezado ni pie
        properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1417, bottom: 1417, left: 1701, right: 1701 } } },
        children: coverChildren,
      },
      { // cuerpo: numero de pagina arriba a la derecha (APA)
        properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
        headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SZ })] })] }) },
        children: body,
      },
    ],
  });

  return Packer.toBuffer(doc).then((buf) => {
    fs.writeFileSync(out, buf);
    return out;
  });
}

module.exports = {
  Paragraph, TextRun, AlignmentType, ROOT, FONT, SZ,
  runs, P, H1, H2, H3, B, numList, gap, note, table, figure, cover, ref, writeDocx,
  counts: () => ({ figN, tabN }),
};

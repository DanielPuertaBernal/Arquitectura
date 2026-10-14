#!/usr/bin/env bash
# Builds ntfs/lab_ntfs.img: MBR + one NTFS partition (type 7) starting at sector 2048.
# Idempotent: rebuilds everything from scratch. No sudo: uses udisksctl loop + auto-mount (ntfs3).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-/tmp/ntfs_build}"
PART="$WORK/part.img"
IMG="$HERE/lab_ntfs.img"
SRC="$HERE/fuentes.txt"
PART_MIB=200
START_SECTOR=2048
UA="UCOLabBot/1.0 (https://uco.edu.co; sistemas.practica1@uco.edu.co) curl/8"
LOOP=""

cleanup() {
  set +e
  if [[ -n "$LOOP" ]]; then
    udisksctl unmount -b "$LOOP" --no-user-interaction >/dev/null 2>&1
    udisksctl loop-delete -b "$LOOP" --no-user-interaction >/dev/null 2>&1
  fi
}
trap cleanup EXIT

rm -rf "$WORK"; mkdir -p "$WORK/dl"
: > "$SRC"
echo "# Fuentes de los archivos descargados (generado por build_ntfs_image.sh)" >> "$SRC"

dl() { # dl URL DEST ; returns 0 on success
  curl -fsSL --max-time 90 -A "$UA" -o "$2" "$1"
}

# ---------- 1. Partition file ----------
truncate -s ${PART_MIB}M "$PART"
mkntfs -F -Q -L LABNTFS "$PART" >/dev/null

# ---------- 2. Mount and populate ----------
LOOP=$(udisksctl loop-setup -f "$PART" --no-user-interaction | sed -E 's/.* as (\/dev\/loop[0-9]+).*/\1/')
sleep 1
MNT=$(findmnt -n -o TARGET "$LOOP" || true)
if [[ -z "$MNT" ]]; then
  udisksctl mount -b "$LOOP" --no-user-interaction >/dev/null
  MNT=$(findmnt -n -o TARGET "$LOOP")
fi
echo "Montado $LOOP en $MNT"

mkdir -p "$MNT"/{Codigo/asm,Codigo/python,Codigo/c,BaseDatos,Documentos,Imagenes,Aplicaciones}
mkdir -p "$MNT/Proyectos/2025/Lab2/fuentes" "$MNT/Proyectos/2025/Lab2/informe"

# --- Code ---
cat > "$MNT/Codigo/asm/suma.asm" <<'EOF'
# suma.asm - MIPS: suma de dos enteros
        .data
a:      .word 7
b:      .word 35
        .text
main:   lw   $t0, a
        lw   $t1, b
        add  $t2, $t0, $t1
        move $a0, $t2
        li   $v0, 1
        syscall
        li   $v0, 10
        syscall
EOF
cat > "$MNT/Codigo/asm/factorial.asm" <<'EOF'
# factorial.asm - MIPS: factorial iterativo de 6
        .text
main:   li   $t0, 6
        li   $t1, 1
loop:   mul  $t1, $t1, $t0
        addi $t0, $t0, -1
        bgtz $t0, loop
        move $a0, $t1
        li   $v0, 1
        syscall
        li   $v0, 10
        syscall
EOF
cat > "$MNT/Codigo/python/hola.py" <<'EOF'
def saludo(nombre):
    return f"Hola, {nombre}! Laboratorio 2 - NTFS"

if __name__ == "__main__":
    print(saludo("UCO"))
EOF
cat > "$MNT/Codigo/c/hola.c" <<'EOF'
#include <stdio.h>
int main(void) {
    printf("Hola NTFS\n");
    return 0;
}
EOF

# --- Database ---
cat > "$MNT/BaseDatos/schema.sql" <<'EOF'
CREATE TABLE estudiante (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, programa TEXT);
CREATE TABLE curso (codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, creditos INTEGER);
CREATE TABLE matricula (id_estudiante INTEGER, codigo_curso TEXT, nota REAL,
  FOREIGN KEY(id_estudiante) REFERENCES estudiante(id),
  FOREIGN KEY(codigo_curso) REFERENCES curso(codigo));
EOF
cat > "$MNT/BaseDatos/datos.sql" <<'EOF'
INSERT INTO estudiante VALUES (1,'Ana Perez','Sistemas'),(2,'Luis Gomez','Sistemas'),(3,'Marta Ruiz','Electronica');
INSERT INTO curso VALUES ('ARQ01','Arquitectura de Computadores',3),('BD01','Bases de Datos',3);
INSERT INTO matricula VALUES (1,'ARQ01',4.5),(2,'ARQ01',3.8),(3,'BD01',4.1),(1,'BD01',4.9);
EOF
python3 - "$MNT/BaseDatos" <<'EOF'
import sqlite3, sys, pathlib
d = pathlib.Path(sys.argv[1]); db = d / "universidad.sqlite"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.executescript((d / "schema.sql").read_text()); con.executescript((d / "datos.sql").read_text())
con.commit(); con.close()
EOF

# --- Documents ---
pdf_ok() { head -c 5 "$1" | grep -q '%PDF-'; }
gen_pdf() { python3 - "$1" "$2" <<'EOF'
import sys
text = sys.argv[2]
objs = []
objs.append("<< /Type /Catalog /Pages 2 0 R >>")
objs.append("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET"
objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
out = b"%PDF-1.4\n"; offs = []
for i, o in enumerate(objs, 1):
    offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n".encode()
x = len(out)
out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
for o in offs: out += f"{o:010d} 00000 n \n".encode()
out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
open(sys.argv[1], "wb").write(out)
EOF
}
for n in 9293 9000; do
  f="$WORK/dl/rfc$n.pdf"
  if dl "https://www.rfc-editor.org/rfc/rfc$n.pdf" "$f" && pdf_ok "$f" && [[ $(stat -c %s "$f") -lt 3000000 ]]; then
    cp "$f" "$MNT/Documentos/rfc$n.pdf"
    echo "https://www.rfc-editor.org/rfc/rfc$n.pdf -> /Documentos/rfc$n.pdf" >> "$SRC"
  else
    echo "FALLBACK PDF generado para rfc$n.pdf" >&2
    gen_pdf "$MNT/Documentos/rfc$n.pdf" "Documento de prueba $n - generado con Python"
    echo "(generado localmente con Python) -> /Documentos/rfc$n.pdf  [descarga fallida]" >> "$SRC"
  fi
done
python3 - "$MNT/Documentos/informe.docx" <<'EOF'
import sys, zipfile
ct = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
rels = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
doc = '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Informe del Laboratorio 2 - NTFS</w:t></w:r></w:p></w:body></w:document>'
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", ct); z.writestr("_rels/.rels", rels); z.writestr("word/document.xml", doc)
EOF
# tiny resident file + file that will carry the ADS
printf 'Archivo residente: este texto cabe dentro del registro MFT.\n' > "$MNT/Documentos/pequeno.txt"
printf 'Nota publica del laboratorio NTFS.\n' > "$MNT/Documentos/nota.txt"

# --- Images ---
gen_jpg() { python3 - "$1" "$2" <<'EOF'
import sys
from PIL import Image, ImageDraw
im = Image.new("RGB", (320, 200), (30, 80, 160)); d = ImageDraw.Draw(im)
d.text((20, 90), sys.argv[2], fill=(255, 255, 255)); im.save(sys.argv[1], "JPEG", quality=85)
EOF
}
n=0
declare -A JP=(
  [tierra.jpg]="https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/The_Earth_seen_from_Apollo_17.jpg/500px-The_Earth_seen_from_Apollo_17.jpg"
  [luna.jpg]="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/FullMoon2010.jpg/500px-FullMoon2010.jpg"
)
for name in tierra.jpg luna.jpg; do
  f="$WORK/dl/$name"
  if dl "${JP[$name]}" "$f" && [[ "$(head -c 3 "$f" | od -An -tx1 | tr -d ' ')" == "ffd8ff" ]] && [[ $(stat -c %s "$f") -lt 300000 ]]; then
    cp "$f" "$MNT/Imagenes/$name"; echo "${JP[$name]} -> /Imagenes/$name" >> "$SRC"
  else
    echo "FALLBACK JPEG generado para $name" >&2
    gen_jpg "$MNT/Imagenes/$name" "Imagen $name (generada con PIL)"
    echo "(generado localmente con PIL) -> /Imagenes/$name  [descarga fallida]" >> "$SRC"
  fi
done
python3 - "$MNT/Imagenes/logo.png" <<'EOF'
import sys
from PIL import Image, ImageDraw
im = Image.new("RGB", (128, 128), (255, 255, 255)); d = ImageDraw.Draw(im)
d.ellipse((16, 16, 112, 112), fill=(200, 30, 60)); d.rectangle((48, 48, 80, 80), fill=(255, 255, 255))
im.save(sys.argv[1], "PNG")
EOF
echo "(generado localmente con PIL) -> /Imagenes/logo.png" >> "$SRC"

# --- Application ---
EXE="$WORK/dl/putty.exe"
if dl "https://the.earth.li/~sgtatham/putty/latest/w64/putty.exe" "$EXE" && [[ "$(head -c 2 "$EXE")" == "MZ" ]]; then
  cp "$EXE" "$MNT/Aplicaciones/putty.exe"
  echo "https://the.earth.li/~sgtatham/putty/latest/w64/putty.exe -> /Aplicaciones/putty.exe (firma MZ verificada)" >> "$SRC"
else
  echo "FALLBACK ELF copiado de /usr/bin" >&2
  cp /usr/bin/true "$MNT/Aplicaciones/true"
  [[ "$(head -c 4 "$MNT/Aplicaciones/true" | od -An -c | tr -d ' ')" == '177ELF' ]] || { echo "ELF invalido" >&2; exit 1; }
  echo "/usr/bin/true (ELF local) -> /Aplicaciones/true  [descarga de putty.exe fallida]" >> "$SRC"
fi

# --- Nested + many-entries folder + deleted file ---
printf 'int main(){return 0;}\n' > "$MNT/Proyectos/2025/Lab2/fuentes/main.c"
printf 'Informe final: localizacion de archivos en NTFS.\n' > "$MNT/Proyectos/2025/Lab2/informe/lab2_ntfs.txt"
python3 - "$MNT/Proyectos/2025/Lab2/informe/datos_largo.bin" <<'EOF'
import sys
# ~40 KiB of deterministic text => non-resident $DATA spanning several clusters
open(sys.argv[1], "wb").write(b"".join(b"linea %05d: contenido de relleno NTFS\n" % i for i in range(1000)))
EOF
mkdir -p "$MNT/Muchos"
for i in $(seq -w 1 60); do
  printf 'archivo numero %s\n' "$i" > "$MNT/Muchos/archivo_largo_nombre_numero_$i.txt"
done
printf 'Este archivo sera borrado para demostrar la recuperacion.\n' > "$MNT/Documentos/borrar_me.txt"
python3 - "$MNT/Documentos/borrar_grande.bin" <<'EOF2'
import sys
open(sys.argv[1], "wb").write(b"".join(b"BORRADO %05d: bloque recuperable\n" % i for i in range(700)))
EOF2
sync
rm "$MNT/Documentos/borrar_me.txt" "$MNT/Documentos/borrar_grande.bin"
sync

# ---------- 3. Unmount ----------
udisksctl unmount -b "$LOOP" --no-user-interaction >/dev/null
udisksctl loop-delete -b "$LOOP" --no-user-interaction >/dev/null
LOOP=""

# ADS (offline)
printf 'contenido oculto en un Alternate Data Stream\n' > "$WORK/secreto.txt"
ntfscp -N secreto "$PART" "$WORK/secreto.txt" /Documentos/nota.txt

# ---------- 4. Assemble disk ----------
rm -f "$IMG"
truncate -s $(( (START_SECTOR*512) + PART_MIB*1024*1024 )) "$IMG"
sfdisk -q "$IMG" <<EOF
label: dos
start=$START_SECTOR, type=7
EOF
dd if="$PART" of="$IMG" bs=512 seek=$START_SECTOR conv=notrunc status=none
(cd "$HERE" && sha256sum lab_ntfs.img > lab_ntfs.img.sha256)
rm -f "$PART"

# ---------- 5. Verify ----------
mmls "$IMG"
fls -o $START_SECTOR -r -p "$IMG" | head -20
echo "OK: $IMG"

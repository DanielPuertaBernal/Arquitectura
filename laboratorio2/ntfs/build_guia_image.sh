#!/usr/bin/env bash
# Builds ntfs/lab_ntfs_guia.img: a copy of lab_ntfs.img plus /LAB_NTFS.txt (test file of the NTFS guide).
# No sudo: mounts the partition (sector 2048) with udisksctl, the kernel ntfs3 driver writes the file.
# Note: ntfs3 reuses the lowest free MFT record, so LAB_NTFS.txt takes record 120
# (the deleted 58 B file of lab_ntfs.img); record 121 (deleted 23 800 B file) stays recoverable.
# The output hash changes on every run (LAB_NTFS.txt timestamps); offsets and record numbers do not.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HERE/lab_ntfs.img"
IMG="$HERE/lab_ntfs_guia.img"
OFFSET=$(( 2048 * 512 ))
LOOP=""

cleanup() {
  set +e
  if [[ -n "$LOOP" ]]; then
    udisksctl unmount -b "$LOOP" --no-user-interaction >/dev/null 2>&1
    udisksctl loop-delete -b "$LOOP" --no-user-interaction >/dev/null 2>&1
  fi
}
trap cleanup EXIT

(cd "$HERE" && sha256sum -c lab_ntfs.img.sha256) || { echo "lab_ntfs.img missing or modified" >&2; exit 1; }
cp "$BASE" "$IMG"

LOOP=$(udisksctl loop-setup -f "$IMG" --offset "$OFFSET" --no-user-interaction | sed -E 's/.* as (\/dev\/loop[0-9]+).*/\1/')
# udisks may auto-mount the new loop device asynchronously: wait for it before mounting ourselves
MNT=""
for _ in $(seq 20); do
  MNT=$(findmnt -n -o TARGET "$LOOP" || true)
  [[ -n "$MNT" ]] && break
  sleep 0.5
done
if [[ -z "$MNT" ]]; then
  udisksctl mount -b "$LOOP" --no-user-interaction >/dev/null
  MNT=$(findmnt -n -o TARGET "$LOOP")
fi

# Exact content from the guide (UTF-8, LF): 114 bytes
printf 'Arquitectura del Computador\nLaboratorio de sistemas de archivos NTFS\nArchivo de prueba para análisis hexadecimal\n' > "$MNT/LAB_NTFS.txt"
sync

udisksctl unmount -b "$LOOP" --no-user-interaction >/dev/null
udisksctl loop-delete -b "$LOOP" --no-user-interaction >/dev/null
LOOP=""

(cd "$HERE" && sha256sum lab_ntfs_guia.img > lab_ntfs_guia.img.sha256)
# The guide documents record 120 and the exact content: fail loudly if that no longer holds
python3 -I - "$HERE" "$IMG" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import ntfs_analyzer as na
v = na.Volume(sys.argv[2])
rec, _ = v.resolve("/LAB_NTFS.txt")
data = v.read_file("/LAB_NTFS.txt")
expected = "Arquitectura del Computador\nLaboratorio de sistemas de archivos NTFS\nArchivo de prueba para análisis hexadecimal\n".encode()
if rec.number != 120 or data != expected:
    sys.exit(f"unexpected result: record {rec.number}, {len(data)} bytes")
print(f"LAB_NTFS.txt: record {rec.number}, {len(data)} bytes, resident")
EOF
echo "OK: $IMG"

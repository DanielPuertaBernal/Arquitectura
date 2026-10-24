#!/usr/bin/env bash
# Builds ntfs/lab_ntfs_guia.img: a copy of lab_ntfs.img plus /LAB_NTFS.txt (test file of the NTFS guide).
# No sudo: mounts the partition (sector 2048) with udisksctl, the kernel ntfs3 driver writes the file.
# Note: ntfs3 reuses the lowest free MFT record, so LAB_NTFS.txt takes record 120
# (the deleted 58 B file of lab_ntfs.img); record 121 (deleted 23 800 B file) stays recoverable.
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
sleep 1
MNT=$(findmnt -n -o TARGET "$LOOP" || true)
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
python3 "$HERE/ntfs_analyzer.py" "$IMG" --path /LAB_NTFS.txt | head -4
echo "OK: $IMG"

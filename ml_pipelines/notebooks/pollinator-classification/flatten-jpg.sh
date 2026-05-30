#!/usr/bin/env bash
# Flatten every .JPG/.jpg/.jpeg under <source-dir> (recursive) into <dest-dir>.
# Subfolder path is preserved in the filename via '__' so files from different
# subfolders never collide.
#
# Default mode is symlinks (instant, ~zero disk). Use --copy for real copies
# when the dest needs to be portable (e.g. moving to an external drive).
#
# Usage (from fish, bash, or zsh):
#   bash flatten-jpg.sh [--copy|--symlink] <source-dir> <dest-dir>
#
# Examples:
#   bash flatten-jpg.sh ~/Documents/HDD_1_2025_backup ~/flat_jpgs
#   bash flatten-jpg.sh --copy ~/Documents/HDD_1_2025_backup /mnt/usb/flat_jpgs
#
# Existing entries in <dest-dir> are kept (no overwrite).

set -euo pipefail

MODE='symlink'

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--copy)    MODE='copy';    shift ;;
        -l|--symlink) MODE='symlink'; shift ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) break ;;
    esac
done

if [ $# -ne 2 ]; then
    echo "Usage: $0 [--copy|--symlink] <source-dir> <dest-dir>" >&2
    exit 1
fi

if [ ! -d "$1" ]; then
    echo "Error: source directory '$1' does not exist" >&2
    exit 1
fi

# Resolve to absolute paths so symlinks work regardless of caller's cwd.
SRC="$(cd "$1" && pwd)"
DST="${2%/}"
mkdir -p "$DST"
DST="$(cd "$DST" && pwd)"

total=$(find -L "$SRC" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) | wc -l)
verb=$([ "$MODE" = 'copy' ] && echo 'Copying' || echo 'Linking')
echo "Found $total .jpg files in $SRC"
echo "$verb into $DST (mode: $MODE)..."

done_n=0
skipped=0
while IFS= read -r -d '' src_file; do
    rel="${src_file#"$SRC"/}"
    flat_name="${rel//\//__}"
    dst_path="$DST/$flat_name"
    if [ -e "$dst_path" ] || [ -L "$dst_path" ]; then
        skipped=$((skipped + 1))
    else
        if [ "$MODE" = 'copy' ]; then
            cp "$src_file" "$dst_path"
        else
            ln -s "$src_file" "$dst_path"
        fi
        done_n=$((done_n + 1))
    fi
    interval=$([ "$MODE" = 'copy' ] && echo 100 || echo 500)
    if (( (done_n + skipped) % interval == 0 )); then
        printf '\r%s %d/%d (skipped %d)...' "$verb" "$done_n" "$total" "$skipped"
    fi
done < <(find -L "$SRC" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) -print0)

printf '\r%s %d/%d (skipped %d)\n' "$verb" "$done_n" "$total" "$skipped"
echo "Done. Output: $DST"

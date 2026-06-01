#!/bin/sh
# Helper invoked by feh-triage.sh actions. Modes:
#   toggle  flip flag state (used by `f`)
#   unflag  remove from flagged.txt only       (used by `u`)
mode="$1"
img="$2"
[ -z "$img" ] && { echo "no image" >&2; exit 1; }
flag_file="$(dirname "$img")/flagged.txt"

unflag() {
    [ -f "$flag_file" ] || { echo "not flagged"; return; }
    # awk (not grep) so an empty result doesn't fail and skip the mv —
    # which was the bug that made the very first flag impossible to remove.
    awk -v p="$img" '$0 != p' "$flag_file" > "$flag_file.new"
    mv "$flag_file.new" "$flag_file"
    [ -s "$flag_file" ] || rm -f "$flag_file"   # drop empty flagged.txt
    echo "unflagged: $(basename "$img")"
}

flag() {
    echo "$img" >> "$flag_file"
    echo "flagged: $(basename "$img")"
}

case "$mode" in
  toggle|flag)
    if grep -qxF "$img" "$flag_file" 2>/dev/null; then
        unflag
    else
        flag
    fi
    ;;
  unflag)
    unflag
    ;;
  bookmark)
    # $3 = path to a bookmark file. Silently records the current image so
    # the next launch can resume there. Echoes the flag indicator so feh's
    # --info caption shows "★ FLAGGED" / "·" for the current image.
    dest="$3"
    if [ -n "$dest" ]; then
        mkdir -p "$(dirname "$dest")"
        printf '%s\n' "$img" > "$dest"
    fi
    if [ -f "$flag_file" ] && grep -qxF "$img" "$flag_file"; then
        echo "★ FLAGGED"
    else
        echo "·"
    fi
    ;;
  *)
    echo "usage: $0 {toggle|flag|unflag|bookmark} IMAGE [BOOKMARK]" >&2
    exit 1
    ;;
esac

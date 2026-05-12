#!/bin/sh
# Pollinator triage: launch feh with hotkeys for flagging interesting frames.
#
#   f   toggle flag (first press flags, second press unflags)
#   u   explicit unflag (no-op if not flagged)
#
# Resumes at the last entry of the most recently edited flagged.txt under
# the search root. Delete or empty that file to start fresh.
#   Space / arrows / q etc. — feh defaults.
#
# The flagged.txt ends up alongside the images and is consumed by the
# pipeline (BATCH_CONFIG["frames_from"] in ls_v4.ipynb).
#
# Usage:
#   ./feh-triage.sh /path/to/camera/folder

dir="${1:-.}"

# Make sure feh has bindings for our actions. feh reads ~/.config/feh/keys —
# if action_1/action_2 aren't bound there, append our defaults so `f` and `u`
# trigger the flag/unflag actions.
keys_file="${XDG_CONFIG_HOME:-$HOME/.config}/feh/keys"
mkdir -p "$(dirname "$keys_file")"
if ! [ -f "$keys_file" ] || ! grep -qE '^action_1\b' "$keys_file"; then
    {
        echo ""
        echo "# pollinator triage — added by feh-triage.sh"
        echo "action_1 f"
        echo "action_2 u"
    } >> "$keys_file"
    echo "[feh-triage] added 'f' / 'u' bindings to $keys_file"
fi

# Delegate the actual flag/unflag logic to a helper script. feh's %F
# substitution lands on a clean argument boundary that way, dodging the
# inline-quoting problems we hit before.
script_dir="$(cd "$(dirname "$0")" && pwd)"
helper="$script_dir/_feh-action.sh"

# Resume from the most recently edited flagged.txt under $dir, picking up
# at its last entry. No separate bookmark file — the flag history is
# the bookmark. If nothing's been flagged yet, start from the beginning.
last_flagged=""
latest_flag_file=$(find "$dir" -name flagged.txt -printf '%T@ %p\n' 2>/dev/null \
                   | sort -nr | head -1 | cut -d' ' -f2-)
if [ -n "$latest_flag_file" ] && [ -s "$latest_flag_file" ]; then
    last_flagged=$(tail -1 "$latest_flag_file")
fi
if [ -n "$last_flagged" ] && [ -f "$last_flagged" ]; then
    echo "[feh-triage] resuming at $last_flagged"
    set -- --start-at "$last_flagged" "$dir"
else
    set -- "$dir"
fi

exec feh \
    --recursive \
    --fullscreen \
    --auto-zoom \
    --draw-filename \
    --action1 ";$helper toggle %F" \
    --action2 ";$helper unflag %F" \
    "$@"

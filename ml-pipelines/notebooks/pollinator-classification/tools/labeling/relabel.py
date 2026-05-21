#!/usr/bin/env python3
"""
relabel.py — Browse and relabel crops in labeled/ subfolders.

Two modes:

  CORRECT mode  (default, no --dest)
    Point --labeled at a folder with class subfolders (annotated_crops/ or an
    organised inference crops/ folder).  Press a key to move the selected crop
    to a different class subfolder.  Use this to fix wrong labels in place.

      python relabel.py --labeled path/to/annotated_crops

  REVIEW mode  (--dest)
    Point --labeled at an organised inference crops/ folder and --dest at
    annotated_crops/.  Pressing a key COPIES the crop to dest/{class}/ and
    records it in a reviewed.txt file so it is skipped on the next run.
    The original crop in --labeled is not deleted.
    Use this to turn raw inference output into training data incrementally.

      python relabel.py \\
          --labeled path/to/crop_results/run_01/camera_A/crops \\
          --dest    path/to/data/training/annotated_crops

    Rerun the same command later — already-reviewed crops are automatically
    skipped so you continue from where you left off.

Layout:
    Left sidebar  — folder list with crop counts, click to switch folder
    Main area     — grid of all crops in current folder, click to select
    Bottom bar    — send selected crop: b/1/2/3/4/u keys

Controls:
    Click folder  select folder
    Click crop    select crop (cyan border)
    b             background
    1             bumblebee
    2             fly
    3             butterfly
    4             other
    u             unsure
    a / Left      previous crop
    d / Right     next crop
    w / s         prev/next folder
    mouse wheel   scroll grid
    q / Esc       quit
"""

import argparse
import shutil
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

WINDOW = 'relabel'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
FOLDERS = ['background', 'bumblebee', 'fly', 'butterfly', 'other', 'unsure']

KEY_LABELS = {
    ord('b'): 'background',
    ord('1'): 'bumblebee',
    ord('2'): 'fly',
    ord('3'): 'butterfly',
    ord('4'): 'other',
    ord('u'): 'unsure',
}

LEFT_KEYS = {81, 2424832, 65361}
RIGHT_KEYS = {83, 2555904, 65363}

WIN_W = 1500
WIN_H = 920
SIDEBAR_W = 180
BOTTOM_H = 56
GRID_X0 = SIDEBAR_W + 4
GRID_W = WIN_W - GRID_X0
GRID_H = WIN_H - BOTTOM_H
THUMB_SIZE = 120
THUMB_PAD = 6
COLS = max(1, GRID_W // (THUMB_SIZE + THUMB_PAD))

state = {'folder_idx': 0, 'selected_idx': None, 'scroll_row': 0}
_thumb_cache = {}
_needs_refresh = [False]
_counts_cache = {}

# Globals set in main()
labeled_dir = None
dest_dir = None       # None = correct mode; Path = review mode
reviewed_file = None  # Path to reviewed.txt (review mode only)
reviewed_set = set()  # filenames already reviewed


# ── Reviewed tracking ─────────────────────────────────────────────────────

def load_reviewed(labeled_path: Path) -> set:
    """Load set of already-reviewed filenames from reviewed.txt."""
    rfile = labeled_path / 'reviewed.txt'
    if not rfile.exists():
        return set()
    return set(rfile.read_text().splitlines())


def mark_reviewed(labeled_path: Path, filename: str):
    """Append filename to reviewed.txt."""
    rfile = labeled_path / 'reviewed.txt'
    with open(rfile, 'a') as fh:
        fh.write(filename + '\n')
    reviewed_set.add(filename)


# ── File helpers ──────────────────────────────────────────────────────────

def list_crops(folder):
    """Return sorted list of crop paths, skipping reviewed files (review mode)."""
    if not folder.exists():
        return []
    all_crops = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if dest_dir is not None:
        # review mode: skip already-reviewed
        return [p for p in all_crops if p.name not in reviewed_set]
    return all_crops


def folder_counts(base_dir):
    if not _counts_cache:
        _counts_cache.update({f: len(list_crops(base_dir / f)) for f in FOLDERS})
    return _counts_cache


def invalidate_counts():
    _counts_cache.clear()


def get_thumb(path):
    key = str(path)
    if key in _thumb_cache:
        return _thumb_cache[key]
    img = cv2.imread(key)
    if img is None:
        thumb = np.zeros((THUMB_SIZE, THUMB_SIZE, 3), dtype=np.uint8)
        cv2.putText(
            thumb, '?', (THUMB_SIZE // 2 - 8, THUMB_SIZE // 2 + 8),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 200), 2,
        )
    else:
        h, w = img.shape[:2]
        scale = THUMB_SIZE / max(w, h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        thumb = np.zeros((THUMB_SIZE, THUMB_SIZE, 3), dtype=np.uint8)
        yo = (THUMB_SIZE - nh) // 2
        xo = (THUMB_SIZE - nw) // 2
        thumb[yo: yo + nh, xo: xo + nw] = resized
    _thumb_cache[key] = thumb
    return thumb


# ── Rendering ─────────────────────────────────────────────────────────────

def put(canvas, text, org, scale=0.48, color=(220, 220, 220), thickness=1):
    cv2.putText(canvas, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thickness, cv2.LINE_AA)


def render(base_dir, crops):
    canvas = np.full((WIN_H, WIN_W, 3), 22, dtype=np.uint8)
    counts = folder_counts(base_dir)
    folder_name = FOLDERS[state['folder_idx']]
    sel = state['selected_idx']

    # Header strip: show mode
    mode_label = (
        f'REVIEW MODE  →  {dest_dir}' if dest_dir else 'CORRECT MODE'
    )
    put(canvas, mode_label, (SIDEBAR_W + 8, 16), 0.40, (160, 200, 160) if dest_dir else (160, 160, 200))

    # Sidebar
    cv2.rectangle(canvas, (0, 0), (SIDEBAR_W, WIN_H), (32, 32, 32), -1)
    put(canvas, 'FOLDERS', (8, 22), 0.45, (160, 160, 160))
    for i, f in enumerate(FOLDERS):
        y0 = 32 + i * 52
        y1 = y0 + 46
        active = i == state['folder_idx']
        bg = (55, 90, 55) if active else (40, 40, 40)
        cv2.rectangle(canvas, (4, y0), (SIDEBAR_W - 4, y1), bg, -1)
        if active:
            cv2.rectangle(canvas, (4, y0), (SIDEBAR_W - 4, y1), (80, 160, 80), 1)
        col = (120, 220, 120) if active else (200, 200, 200)
        put(canvas, f, (10, y0 + 18), 0.50, col)
        put(canvas, f'{counts[f]} crops', (10, y0 + 36), 0.40, (140, 140, 140))

    # Grid
    if not crops:
        msg = 'Empty folder — all reviewed!' if dest_dir else 'Empty folder'
        put(canvas, msg, (GRID_X0 + 20, WIN_H // 2), 0.8, (120, 120, 120))
    else:
        n_rows = max(1, (len(crops) + COLS - 1) // COLS)
        visible_rows = GRID_H // (THUMB_SIZE + THUMB_PAD)
        state['scroll_row'] = max(
            0, min(state['scroll_row'], max(0, n_rows - visible_rows))
        )
        scroll_row = state['scroll_row']

        for idx in range(scroll_row * COLS, len(crops)):
            row = idx // COLS - scroll_row
            col = idx % COLS
            if row < 0:
                continue
            x = GRID_X0 + col * (THUMB_SIZE + THUMB_PAD) + THUMB_PAD
            y = row * (THUMB_SIZE + THUMB_PAD) + THUMB_PAD
            if y + THUMB_SIZE > GRID_H:
                break
            thumb = get_thumb(crops[idx])
            canvas[y: y + THUMB_SIZE, x: x + THUMB_SIZE] = thumb
            if idx == sel:
                cv2.rectangle(canvas, (x - 2, y - 2),
                               (x + THUMB_SIZE + 2, y + THUMB_SIZE + 2), (0, 220, 220), 3)
            else:
                cv2.rectangle(canvas, (x - 1, y - 1),
                               (x + THUMB_SIZE + 1, y + THUMB_SIZE + 1), (60, 60, 60), 1)

        if n_rows > visible_rows:
            bar_h = max(20, int(visible_rows / n_rows * GRID_H))
            bar_y = int(
                state['scroll_row'] / max(1, n_rows - visible_rows) * (GRID_H - bar_h)
            )
            cv2.rectangle(canvas, (WIN_W - 8, bar_y), (WIN_W - 2, bar_y + bar_h),
                           (100, 100, 100), -1)

    # Bottom bar
    cv2.rectangle(canvas, (0, WIN_H - BOTTOM_H), (WIN_W, WIN_H), (28, 28, 28), -1)
    cv2.line(canvas, (0, WIN_H - BOTTOM_H), (WIN_W, WIN_H - BOTTOM_H), (50, 50, 50), 1)
    if sel is not None and sel < len(crops):
        put(canvas, f'Selected: {crops[sel].name}',
            (GRID_X0, WIN_H - BOTTOM_H + 18), 0.42, (180, 180, 180))
    btn_labels = [
        ('b', 'background'), ('1', 'bumblebee'), ('2', 'fly'),
        ('3', 'butterfly'), ('4', 'other'), ('u', 'unsure'),
    ]
    bx = GRID_X0
    for key_ch, label in btn_labels:
        active = label == folder_name
        bg = (60, 120, 60) if active else (50, 50, 50)
        by = WIN_H - BOTTOM_H + 24
        cv2.rectangle(canvas, (bx, by), (bx + 110, by + 24), bg, -1)
        cv2.rectangle(canvas, (bx, by), (bx + 110, by + 24), (80, 80, 80), 1)
        put(canvas, f'{key_ch}={label[:8]}', (bx + 4, by + 17), 0.40,
            (200, 220, 200) if active else (190, 190, 190))
        bx += 114
    put(canvas, 'a/d=prev/next  w/s=folder  scroll=wheel  q=quit',
        (WIN_W - 420, WIN_H - 10), 0.40, (130, 130, 130))

    return canvas


# ── Mouse ─────────────────────────────────────────────────────────────────

def on_mouse(event, x, y, flags, crops):
    if event == cv2.EVENT_LBUTTONDOWN:
        if x < SIDEBAR_W:
            for i in range(len(FOLDERS)):
                y0 = 32 + i * 52
                if y0 <= y <= y0 + 46:
                    if i != state['folder_idx']:
                        state['folder_idx'] = i
                        state['selected_idx'] = None
                        state['scroll_row'] = 0
                        _thumb_cache.clear()
                        _needs_refresh[0] = True
                        threading.Thread(
                            target=lambda: [
                                get_thumb(p)
                                for p in list_crops(labeled_dir / FOLDERS[i])[:60]
                            ],
                            daemon=True,
                        ).start()
                    return
        elif x < WIN_W - 8 and y < GRID_H:
            col = (x - GRID_X0) // (THUMB_SIZE + THUMB_PAD)
            row = y // (THUMB_SIZE + THUMB_PAD)
            if 0 <= col < COLS:
                idx = (state['scroll_row'] + row) * COLS + col
                if 0 <= idx < len(crops):
                    state['selected_idx'] = idx
    elif event == cv2.EVENT_MOUSEWHEEL:
        state['scroll_row'] = max(0, state['scroll_row'] + (-2 if flags > 0 else 2))


# ── Crop action ───────────────────────────────────────────────────────────

def send_crop(src: Path, target_label: str, base_dir: Path):
    """
    CORRECT mode (dest_dir is None):
        Move crop to base_dir/{target_label}/ within the labeled folder.
    REVIEW mode (dest_dir is set):
        Copy crop to dest_dir/{target_label}/ and record in reviewed.txt.
    """
    if dest_dir is not None:
        # ── Review mode ──────────────────────────────────────────────────
        dst_class_dir = dest_dir / target_label
        dst_class_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_class_dir / src.name
        # Avoid name collisions
        counter = 1
        while dst.exists():
            dst = dst_class_dir / f'{src.stem}_{counter}{src.suffix}'
            counter += 1
        shutil.copy2(str(src), str(dst))
        mark_reviewed(base_dir, src.name)
        _thumb_cache.pop(str(src), None)
        print(f'Reviewed: {src.name}  →  {target_label}/')
    else:
        # ── Correct mode ─────────────────────────────────────────────────
        dst_class_dir = base_dir / target_label
        dst_class_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_class_dir / src.name
        counter = 1
        while dst.exists():
            dst = dst_class_dir / f'{src.stem}_{counter}{src.suffix}'
            counter += 1
        shutil.move(str(src), str(dst))
        _thumb_cache.pop(str(src), None)
        print(f'Moved: {src.name}  →  {target_label}/')


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global labeled_dir, dest_dir, reviewed_file, reviewed_set

    parser = argparse.ArgumentParser(
        description='Review and relabel crop images.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--labeled', type=Path,
        default=Path('data/training/annotated_crops/labeled'),
        help='Folder with class subfolders to browse.',
    )
    parser.add_argument(
        '--dest', type=Path, default=None,
        help=(
            'Review mode: copy reviewed crops to this folder (e.g. annotated_crops/). '
            'Already-reviewed crops are tracked in --labeled/reviewed.txt and skipped '
            'on the next run.'
        ),
    )
    args = parser.parse_args()

    labeled_dir = args.labeled.resolve()
    dest_dir = args.dest.resolve() if args.dest else None

    if not labeled_dir.exists():
        print(f'ERROR: --labeled folder not found: {labeled_dir}', file=sys.stderr)
        return 1

    print()
    print('═' * 60)
    print('  Relabel')
    print('═' * 60)
    if dest_dir is not None:
        print('  Mode: REVIEW — copy confirmed crops to annotated_crops/')
        print()
        print(f'  Source (--labeled): {labeled_dir}')
        print(f'  Dest   (--dest)   : {dest_dir}')
        print()
        print('  Press a label key to copy the selected crop to dest/')
        print('  and mark it as reviewed. Progress is saved in')
        print('  reviewed.txt — quit and resume any time.')
    else:
        print('  Mode: CORRECT — fix labels already in annotated_crops/')
        print()
        print(f'  Folder (--labeled): {labeled_dir}')
        print()
        print('  Press a label key to move the selected crop to a')
        print('  different class subfolder.')
    print()
    print('  Controls:')
    print('    b         background')
    print('    1         bumblebee')
    print('    2         fly')
    print('    3         butterfly')
    print('    4         other')
    print('    u         unsure')
    print('    a / ←    previous crop')
    print('    d / →    next crop')
    print('    w / s     previous / next folder')
    print('    q / Esc   quit')
    print('═' * 60)
    print()

    if dest_dir is not None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        reviewed_set = load_reviewed(labeled_dir)
        if reviewed_set:
            print(f'Skipping {len(reviewed_set)} already-reviewed crops.')
    else:
        print(f'Correct mode: {labeled_dir}')

    for f in FOLDERS:
        (labeled_dir / f).mkdir(parents=True, exist_ok=True)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, WIN_W, WIN_H)

    crops = []
    last_state = [None]

    def state_key():
        return (state['folder_idx'], state['selected_idx'], state['scroll_row'])

    def preload_thumbs(crop_list):
        for p in crop_list[:60]:
            get_thumb(p)

    def refresh():
        nonlocal crops
        invalidate_counts()
        crops = list_crops(labeled_dir / FOLDERS[state['folder_idx']])
        sel = state['selected_idx']
        if sel is not None:
            state['selected_idx'] = min(sel, len(crops) - 1) if crops else None
        cv2.setMouseCallback(WINDOW, on_mouse, crops)
        threading.Thread(target=preload_thumbs, args=(crops,), daemon=True).start()

    refresh()

    while True:
        sk = state_key()
        if sk != last_state[0] or _needs_refresh[0]:
            cv2.imshow(WINDOW, render(labeled_dir, crops))
            last_state[0] = sk
        key = cv2.waitKeyEx(16)
        if _needs_refresh[0]:
            refresh()
            _needs_refresh[0] = False
        if key == -1:
            continue

        key_low = key & 0xFF
        ch = chr(key_low).lower() if 0 <= key_low <= 255 else ''

        if key == 27 or ch == 'q':
            break

        if ch == 'a' or key in LEFT_KEYS:
            if crops:
                sel = state['selected_idx']
                state['selected_idx'] = max(
                    0, (sel - 1) if sel is not None else len(crops) - 1
                )

        elif ch == 'd' or key in RIGHT_KEYS:
            if crops:
                sel = state['selected_idx']
                state['selected_idx'] = min(
                    len(crops) - 1, (sel + 1) if sel is not None else 0
                )

        elif ch == 'w':
            state['folder_idx'] = max(0, state['folder_idx'] - 1)
            state['selected_idx'] = None
            state['scroll_row'] = 0
            _thumb_cache.clear()
            refresh()

        elif ch == 's':
            state['folder_idx'] = min(len(FOLDERS) - 1, state['folder_idx'] + 1)
            state['selected_idx'] = None
            state['scroll_row'] = 0
            _thumb_cache.clear()
            refresh()

        elif key_low in KEY_LABELS:
            sel = state['selected_idx']
            if sel is not None and crops and sel < len(crops):
                target = KEY_LABELS[key_low]
                src = crops[sel]
                # In correct mode, skip if crop is already in the target folder
                if dest_dir is None and target == FOLDERS[state['folder_idx']]:
                    pass  # already here, nothing to do
                else:
                    send_crop(src, target, labeled_dir)
                    refresh()

    cv2.destroyAllWindows()
    if dest_dir is not None:
        print(f'\nSession done.  {len(reviewed_set)} crops reviewed total.')
        print(f'Reviewed crops are in: {dest_dir}')
        print(f'Progress saved in: {labeled_dir}/reviewed.txt')
    print('Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

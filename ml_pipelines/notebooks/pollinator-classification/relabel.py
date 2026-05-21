#!/usr/bin/env python3
"""
relabel.py — Browse and relabel crops in labeled/ subfolders.

Usage:
    python relabel.py --labeled /full/path/to/labeled

Layout:
    Left sidebar  — folder list with crop counts, click to switch folder
    Main area     — grid of all crops in current folder, click to select
    Bottom bar    — move selected crop: b/1/2/3/4/u keys

Controls:
    Click folder  select folder
    Click crop    select crop (cyan border)
    b             move to background
    1             move to bumblebee
    2             move to fly
    3             move to butterfly
    4             move to other
    u             move to unsure
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


def list_crops(folder):
    return (
        sorted(
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
        if folder.exists()
        else []
    )


def folder_counts(labeled_dir):
    if not _counts_cache:
        _counts_cache.update({f: len(list_crops(labeled_dir / f)) for f in FOLDERS})
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
            thumb,
            '?',
            (THUMB_SIZE // 2 - 8, THUMB_SIZE // 2 + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (80, 80, 200),
            2,
        )
    else:
        h, w = img.shape[:2]
        scale = THUMB_SIZE / max(w, h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        thumb = np.zeros((THUMB_SIZE, THUMB_SIZE, 3), dtype=np.uint8)
        yo = (THUMB_SIZE - nh) // 2
        xo = (THUMB_SIZE - nw) // 2
        thumb[yo : yo + nh, xo : xo + nw] = resized
    _thumb_cache[key] = thumb
    return thumb


def put(canvas, text, org, scale=0.48, color=(220, 220, 220), thickness=1):
    cv2.putText(
        canvas,
        text,
        org,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def render(labeled_dir, crops):
    canvas = np.full((WIN_H, WIN_W, 3), 22, dtype=np.uint8)
    counts = folder_counts(labeled_dir)
    folder_name = FOLDERS[state['folder_idx']]
    sel = state['selected_idx']

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
        put(canvas, 'Empty folder', (GRID_X0 + 20, WIN_H // 2), 0.8, (120, 120, 120))
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
            canvas[y : y + THUMB_SIZE, x : x + THUMB_SIZE] = thumb
            if idx == sel:
                cv2.rectangle(
                    canvas,
                    (x - 2, y - 2),
                    (x + THUMB_SIZE + 2, y + THUMB_SIZE + 2),
                    (0, 220, 220),
                    3,
                )
            else:
                cv2.rectangle(
                    canvas,
                    (x - 1, y - 1),
                    (x + THUMB_SIZE + 1, y + THUMB_SIZE + 1),
                    (60, 60, 60),
                    1,
                )

        if n_rows > visible_rows:
            bar_h = max(20, int(visible_rows / n_rows * GRID_H))
            bar_y = int(
                state['scroll_row'] / max(1, n_rows - visible_rows) * (GRID_H - bar_h)
            )
            cv2.rectangle(
                canvas,
                (WIN_W - 8, bar_y),
                (WIN_W - 2, bar_y + bar_h),
                (100, 100, 100),
                -1,
            )

    # Bottom bar
    cv2.rectangle(canvas, (0, WIN_H - BOTTOM_H), (WIN_W, WIN_H), (28, 28, 28), -1)
    cv2.line(canvas, (0, WIN_H - BOTTOM_H), (WIN_W, WIN_H - BOTTOM_H), (50, 50, 50), 1)
    if sel is not None and sel < len(crops):
        put(
            canvas,
            f'Selected: {crops[sel].name}',
            (GRID_X0, WIN_H - BOTTOM_H + 18),
            0.42,
            (180, 180, 180),
        )
    btn_labels = [
        ('b', 'background'),
        ('1', 'bumblebee'),
        ('2', 'fly'),
        ('3', 'butterfly'),
        ('4', 'other'),
        ('u', 'unsure'),
    ]
    bx = GRID_X0
    for key_ch, label in btn_labels:
        active = label == folder_name
        bg = (60, 120, 60) if active else (50, 50, 50)
        by = WIN_H - BOTTOM_H + 24
        cv2.rectangle(canvas, (bx, by), (bx + 110, by + 24), bg, -1)
        cv2.rectangle(canvas, (bx, by), (bx + 110, by + 24), (80, 80, 80), 1)
        put(
            canvas,
            f'{key_ch}={label[:8]}',
            (bx + 4, by + 17),
            0.40,
            (200, 220, 200) if active else (190, 190, 190),
        )
        bx += 114
    put(
        canvas,
        'a/d=prev/next  w/s=folder  scroll=wheel  q=quit',
        (WIN_W - 420, WIN_H - 10),
        0.40,
        (130, 130, 130),
    )

    return canvas


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


def move_crop(src, target_label, labeled_dir):
    dst_dir = labeled_dir / target_label
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    counter = 1
    while dst.exists():
        dst = dst_dir / f'{src.stem}_{counter}{src.suffix}'
        counter += 1
    shutil.move(str(src), str(dst))
    _thumb_cache.pop(str(src), None)
    print(f'Moved: {src.name}  →  {target_label}/')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--labeled', type=Path, default=Path('Insects_images/annotated_crops/labeled')
    )
    args = parser.parse_args()
    labeled_dir = args.labeled.resolve()

    if not labeled_dir.exists():
        print(f'ERROR: not found: {labeled_dir}', file=sys.stderr)
        print(
            f'Usage: python relabel.py --labeled /full/path/to/labeled', file=sys.stderr
        )
        return 1

    for f in FOLDERS:
        (labeled_dir / f).mkdir(parents=True, exist_ok=True)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, WIN_W, WIN_H)

    crops = []
    last_state = [None]

    def state_key():
        return (state['folder_idx'], state['selected_idx'], state['scroll_row'])

    def preload_thumbs(crop_list):
        """Pre-load thumbnails in background thread."""
        for p in crop_list[:60]:  # preload first 60
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
                if target != FOLDERS[state['folder_idx']]:
                    move_crop(crops[sel], target, labeled_dir)
                    refresh()

    cv2.destroyAllWindows()
    print('Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

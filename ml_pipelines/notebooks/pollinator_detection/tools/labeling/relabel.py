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
import queue
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

LEFT_KEYS  = {81, 2424832, 65361}
RIGHT_KEYS = {83, 2555904, 65363}

WIN_W     = 1500
WIN_H     = 920
SIDEBAR_W = 180
BOTTOM_H  = 56
GRID_X0   = SIDEBAR_W + 4
GRID_W    = WIN_W - GRID_X0
GRID_H    = WIN_H - BOTTOM_H
THUMB_SIZE = 120
THUMB_PAD  = 6
COLS = max(1, GRID_W // (THUMB_SIZE + THUMB_PAD))

state = {'folder_idx': 0, 'selected_idx': None, 'scroll_row': 0}

# ── Thumb cache — persists across folder switches ─────────────────────────
# Keys are str(path).  Reads/writes on both main thread and loader thread;
# protected by _cache_lock.
_thumb_cache: dict = {}
_cache_lock = threading.Lock()

# Placeholder shown immediately while the real thumb loads in background.
_PLACEHOLDER: np.ndarray  # set in main()

# Signal for main loop: background loader added new thumbs → re-render.
_needs_render = [False]

# ── Background loader ─────────────────────────────────────────────────────
# Single worker thread drains _load_q; each item is a Path to load.
_load_q: queue.Queue = queue.Queue()


def _loader_worker():
    while True:
        try:
            p = _load_q.get(timeout=0.5)
        except queue.Empty:
            continue
        key = str(p)
        with _cache_lock:
            if key in _thumb_cache:
                continue          # already done
        thumb = _build_thumb(p)
        with _cache_lock:
            _thumb_cache[key] = thumb
        _needs_render[0] = True   # wake main loop


def _build_thumb(path: Path) -> np.ndarray:
    """Load and resize one image into a THUMB_SIZE square. Thread-safe."""
    img = cv2.imread(str(path))
    if img is None:
        t = np.full((THUMB_SIZE, THUMB_SIZE, 3), 30, dtype=np.uint8)
        cv2.putText(t, '?', (THUMB_SIZE // 2 - 8, THUMB_SIZE // 2 + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 200), 2)
        return t
    h, w = img.shape[:2]
    scale = THUMB_SIZE / max(w, h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    t = np.zeros((THUMB_SIZE, THUMB_SIZE, 3), dtype=np.uint8)
    yo = (THUMB_SIZE - nh) // 2
    xo = (THUMB_SIZE - nw) // 2
    t[yo: yo + nh, xo: xo + nw] = resized
    return t


def get_thumb(path: Path) -> np.ndarray:
    """Return cached thumb immediately, or placeholder + schedule async load."""
    key = str(path)
    with _cache_lock:
        t = _thumb_cache.get(key)
    if t is not None:
        return t
    _load_q.put(path)   # schedule; worker sets _needs_render when done
    return _PLACEHOLDER


def queue_folder_thumbs(folder_name: str):
    """Queue all crops in a folder for background preloading."""
    for p in _folder_crops.get(folder_name, []):
        with _cache_lock:
            if str(p) not in _thumb_cache:
                _load_q.put(p)


# ── Per-folder crop lists (lazily scanned, incrementally maintained) ───────
_folder_crops: dict = {}   # folder_name → [Path, ...]
_folder_counts: dict = {}  # folder_name → int  (updated in-place on move)

# Globals set in main()
labeled_dir: Path
dest_dir: Path | None = None
reviewed_set: set = set()


def _scan_folder(folder_name: str):
    """Scan disk for one folder and update _folder_crops / _folder_counts."""
    folder = labeled_dir / folder_name
    if not folder.exists():
        _folder_crops[folder_name] = []
        _folder_counts[folder_name] = 0
        return
    all_crops = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if dest_dir is not None:
        all_crops = [p for p in all_crops if p.name not in reviewed_set]
    _folder_crops[folder_name] = all_crops
    _folder_counts[folder_name] = len(all_crops)


def init_folders():
    """Scan all folders once at startup."""
    for f in FOLDERS:
        _scan_folder(f)


def get_counts() -> dict:
    return _folder_counts


# ── Reviewed tracking ─────────────────────────────────────────────────────

def load_reviewed(labeled_path: Path) -> set:
    rfile = labeled_path / 'reviewed.txt'
    if not rfile.exists():
        return set()
    return set(rfile.read_text().splitlines())


def mark_reviewed(labeled_path: Path, filename: str):
    rfile = labeled_path / 'reviewed.txt'
    with open(rfile, 'a') as fh:
        fh.write(filename + '\n')
    reviewed_set.add(filename)


# ── Rendering ─────────────────────────────────────────────────────────────

def put(canvas, text, org, scale=0.48, color=(220, 220, 220), thickness=1):
    cv2.putText(canvas, text, org, cv2.FONT_HERSHEY_SIMPLEX,
                scale, color, thickness, cv2.LINE_AA)


def render(crops: list) -> np.ndarray:
    canvas = np.full((WIN_H, WIN_W, 3), 22, dtype=np.uint8)
    counts = get_counts()
    folder_name = FOLDERS[state['folder_idx']]
    sel = state['selected_idx']

    # Header strip
    mode_label = (
        f'REVIEW MODE  →  {dest_dir}' if dest_dir else 'CORRECT MODE'
    )
    put(canvas, mode_label, (SIDEBAR_W + 8, 16), 0.40,
        (160, 200, 160) if dest_dir else (160, 160, 200))

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
        put(canvas, f'{counts.get(f, 0)} crops', (10, y0 + 36), 0.40, (140, 140, 140))

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
                cv2.rectangle(canvas,
                               (x - 2, y - 2),
                               (x + THUMB_SIZE + 2, y + THUMB_SIZE + 2),
                               (0, 220, 220), 3)
            else:
                cv2.rectangle(canvas,
                               (x - 1, y - 1),
                               (x + THUMB_SIZE + 1, y + THUMB_SIZE + 1),
                               (60, 60, 60), 1)

        if n_rows > visible_rows:
            bar_h = max(20, int(visible_rows / n_rows * GRID_H))
            bar_y = int(
                state['scroll_row'] / max(1, n_rows - visible_rows) * (GRID_H - bar_h)
            )
            cv2.rectangle(canvas,
                           (WIN_W - 8, bar_y), (WIN_W - 2, bar_y + bar_h),
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
                        # Do NOT clear _thumb_cache — keep everything loaded
                        # The main loop will call refresh_crops() via _needs_refresh
                        _needs_render[0] = True
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

def send_crop(src: Path, target_label: str, source_label: str):
    """
    CORRECT mode (dest_dir is None):
        Move crop to labeled_dir/{target_label}/.
        Updates in-memory crop lists and counts without rescanning disk.
    REVIEW mode (dest_dir is set):
        Copy crop to dest_dir/{target_label}/ and record in reviewed.txt.
        Removes crop from in-memory source list.
    """
    if dest_dir is not None:
        # ── Review mode: copy to dest, mark reviewed ──────────────────────
        dst_class_dir = dest_dir / target_label
        dst_class_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_class_dir / src.name
        counter = 1
        while dst.exists():
            dst = dst_class_dir / f'{src.stem}_{counter}{src.suffix}'
            counter += 1
        shutil.copy2(str(src), str(dst))
        mark_reviewed(labeled_dir, src.name)
        # Remove from in-memory source list (reviewed crops are hidden)
        crops_list = _folder_crops.get(source_label, [])
        try:
            crops_list.remove(src)
        except ValueError:
            pass
        _folder_counts[source_label] = len(crops_list)
        print(f'Reviewed: {src.name}  →  {target_label}/')
    else:
        # ── Correct mode: move between class subfolders ───────────────────
        dst_class_dir = labeled_dir / target_label
        dst_class_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_class_dir / src.name
        counter = 1
        while dst.exists():
            dst = dst_class_dir / f'{src.stem}_{counter}{src.suffix}'
            counter += 1
        shutil.move(str(src), str(dst))

        # Update in-memory lists without touching disk
        crops_list = _folder_crops.get(source_label, [])
        try:
            crops_list.remove(src)
        except ValueError:
            pass
        _folder_counts[source_label] = len(crops_list)

        # Add to destination list (keep sorted by name)
        dest_list = _folder_crops.setdefault(target_label, [])
        import bisect
        bisect.insort(dest_list, dst, key=lambda p: str(p))
        _folder_counts[target_label] = len(dest_list)

        # Relocate thumb cache entry to new path
        with _cache_lock:
            thumb = _thumb_cache.pop(str(src), None)
            if thumb is not None:
                _thumb_cache[str(dst)] = thumb

        print(f'Moved: {src.name}  →  {target_label}/')


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global labeled_dir, dest_dir, reviewed_set, _PLACEHOLDER

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

    # Build placeholder thumbnail (shown while real thumb loads in background)
    _PLACEHOLDER = np.full((THUMB_SIZE, THUMB_SIZE, 3), 45, dtype=np.uint8)
    cv2.putText(_PLACEHOLDER, '...', (THUMB_SIZE // 2 - 18, THUMB_SIZE // 2 + 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)

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

    # Start background loader thread
    threading.Thread(target=_loader_worker, daemon=True).start()

    # Scan all folders once (fast — just iterdir, no image loading)
    print('Scanning folders...')
    init_folders()
    total = sum(_folder_counts.values())
    print(f'Found {total} crops across {len(FOLDERS)} folders.')

    # Queue first folder's thumbs for immediate background loading
    queue_folder_thumbs(FOLDERS[0])

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, WIN_W, WIN_H)

    def current_crops() -> list:
        return _folder_crops.get(FOLDERS[state['folder_idx']], [])

    crops = current_crops()
    cv2.setMouseCallback(WINDOW, on_mouse, crops)

    last_state_key = [None]

    def state_key():
        return (state['folder_idx'], state['selected_idx'], state['scroll_row'])

    last_folder_idx = [state['folder_idx']]

    # Initial render
    cv2.imshow(WINDOW, render(crops))
    last_state_key[0] = state_key()

    while True:
        key = cv2.waitKeyEx(16)

        # Check if folder changed (via mouse click in sidebar)
        if state['folder_idx'] != last_folder_idx[0]:
            last_folder_idx[0] = state['folder_idx']
            crops = current_crops()
            cv2.setMouseCallback(WINDOW, on_mouse, crops)
            # Prioritise loading visible thumbs for the new folder
            queue_folder_thumbs(FOLDERS[state['folder_idx']])

        # Re-render if state changed or background loader delivered new thumbs
        sk = state_key()
        if sk != last_state_key[0] or _needs_render[0]:
            crops = current_crops()
            cv2.imshow(WINDOW, render(crops))
            last_state_key[0] = sk
            _needs_render[0] = False

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
            # No cache clear — thumbs from previous visits are reused

        elif ch == 's':
            state['folder_idx'] = min(len(FOLDERS) - 1, state['folder_idx'] + 1)
            state['selected_idx'] = None
            state['scroll_row'] = 0

        elif key_low in KEY_LABELS:
            sel = state['selected_idx']
            crops = current_crops()
            if sel is not None and crops and sel < len(crops):
                target = KEY_LABELS[key_low]
                src = crops[sel]
                source = FOLDERS[state['folder_idx']]
                if dest_dir is None and target == source:
                    pass  # already in the right folder
                else:
                    send_crop(src, target, source)
                    crops = current_crops()
                    cv2.setMouseCallback(WINDOW, on_mouse, crops)
                    # Clamp selection
                    if crops:
                        state['selected_idx'] = min(sel, len(crops) - 1)
                    else:
                        state['selected_idx'] = None

    cv2.destroyAllWindows()
    if dest_dir is not None:
        print(f'\nSession done.  {len(reviewed_set)} crops reviewed total.')
        print(f'Reviewed crops are in: {dest_dir}')
        print(f'Progress saved in: {labeled_dir}/reviewed.txt')
    print('Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

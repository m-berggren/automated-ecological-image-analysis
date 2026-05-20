"""
Pollinator Crop Labeling Tool  (full-width layout)
=======================================================
Top: full-width debug image with numbered bounding boxes
Bottom: horizontal strip of 6 crops  (scroll row by row)

Controls:
  R  → toggle nav mode

  IMAGE_NAV (default — no header badge)
    Left / Right / A / D  → previous / next image
    Up / Down             → scroll the crop strip
    b 1 2 3 4 u           → batch-label all unlabeled in this image
                            (same key twice = undo)
    click crop            → select it; label keys then apply to that crop only

  CROP_NAV  (header shows "CROP NAV" badge)
    Left / Right          → move crop selection left / right
    Up / Down             → move selection up / down by row
    b 1 2 3 4 u           → label the SELECTED crop, then advance

  Labels: bg / bumblebee / fly / butterfly / other / unsure
  Tab / E  → Label-all mode toggle (extra fine-grained control)
  C        → clear all labels in current image
  P        → preview selected crop
  Q        → quit and save

Usage:
  python3 crop_labeler_v2.py --results path/to/results --output path/to/annotated_crops
"""

import os
import argparse
import csv
import json
import re as _re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

UI_FONT_SCALE = 1.20
UI_TEXT_LINE_TYPE = cv2.LINE_8
_cv2_put_text = cv2.putText
_cv2_get_text_size = cv2.getTextSize


def _ui_text_thickness(thickness):
    return max(1, int(round(thickness)))


def _ui_put_text(
    img,
    text,
    org,
    fontFace,
    fontScale,
    color,
    thickness=1,
    lineType=None,
    bottomLeftOrigin=False,
):
    lineType = UI_TEXT_LINE_TYPE if lineType is None else lineType
    return _cv2_put_text(
        img,
        text,
        org,
        fontFace,
        fontScale * UI_FONT_SCALE,
        color,
        _ui_text_thickness(thickness),
        lineType,
        bottomLeftOrigin,
    )


def _ui_get_text_size(text, fontFace, fontScale, thickness):
    return _cv2_get_text_size(
        text, fontFace, fontScale * UI_FONT_SCALE, _ui_text_thickness(thickness)
    )


cv2.putText = _ui_put_text
cv2.getTextSize = _ui_get_text_size

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_json_path(input_folder, output_dir):
    cam_name = os.path.basename(os.fspath(input_folder))
    return Path(output_dir) / 'progress' / f'{cam_name}_result.json'


# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--results', type=Path, default=Path('results'))
parser.add_argument('--output', type=Path, default=Path('labeled_crops'))
args = parser.parse_args()

RESULTS_DIR = args.results
OUTPUT_DIR = (
    args.output.with_name('labeled_crops')
    if args.output.name == 'labeled'
    else args.output
)
ANNOTATION_DIR = OUTPUT_DIR / 'progress'
LABELED_DIR = OUTPUT_DIR / 'labeled'
ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)

for sub in ('bumblebee', 'fly', 'butterfly', 'other', 'background', 'unsure'):
    (LABELED_DIR / sub).mkdir(parents=True, exist_ok=True)

# ── Progress ──────────────────────────────────────────────────────────────────
progress: dict = {}
current_progress_file = None
_save_counter = 0


def save_progress(force=False):
    global _save_counter
    if current_progress_file is None:
        return
    _save_counter += 1
    if force or _save_counter >= 5:
        current_progress_file.write_text(
            json.dumps(progress, indent=2), encoding='utf-8'
        )
        _save_counter = 0


def load_progress_for_task(task_idx):
    global progress, current_progress_file, _save_counter
    if not tasks:
        return
    task_idx = max(0, min(int(task_idx), len(tasks) - 1))
    _, _, _, cam_name, _ = tasks[task_idx]
    progress_file = Path(get_json_path(cam_name, OUTPUT_DIR))
    if current_progress_file == progress_file:
        return
    if current_progress_file is not None:
        save_progress(force=True)
    current_progress_file = progress_file
    if current_progress_file.exists():
        progress = json.loads(current_progress_file.read_text(encoding='utf-8'))
        print(f'Resuming -- {len(progress)} crops already labeled')
    else:
        progress = {}
    _save_counter = 0


# ── Collect tasks ─────────────────────────────────────────────────────────────
tasks = []
for cam_dir in sorted(RESULTS_DIR.iterdir()):
    if not cam_dir.is_dir():
        continue
    debug_dir = cam_dir / 'debug'
    crop_dir = cam_dir / 'crops'
    csv_path = cam_dir / 'results.csv'
    if not (debug_dir.exists() and crop_dir.exists() and csv_path.exists()):
        continue

    image_crops: dict = defaultdict(list)
    seen_crops: dict = defaultdict(set)
    bbox_map: dict = {}

    with open(csv_path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            img_name = row.get('image_name', '')
            crop_fn = row.get('crop_filename', '')
            if not crop_fn or not (crop_dir / crop_fn).exists():
                continue
            if crop_fn in seen_crops[img_name]:
                continue
            seen_crops[img_name].add(crop_fn)
            image_crops[img_name].append((crop_dir / crop_fn, crop_fn))
            try:
                bx = int(float(row.get('bbox_x', 0)))
                by = int(float(row.get('bbox_y', 0)))
                bw = int(float(row.get('bbox_w', 0)))
                bh = int(float(row.get('bbox_h', 0)))
                if bw > 0 and bh > 0:
                    bbox_map[crop_fn] = (bx, by, bw, bh)
            except (ValueError, TypeError):
                pass

    # Index debug_dir once: bucket files by the "{cam_prefix}__{img_stem}"
    # prefix so each image becomes one dict lookup instead of up to 5 globs.
    cam_prefix = cam_dir.name
    debug_by_stem = defaultdict(list)
    for entry in os.scandir(debug_dir):
        if not entry.is_file():
            continue
        name = entry.name
        suffix_at = name.find('_', len(cam_prefix) + 2)
        stem = name[:suffix_at] if suffix_at != -1 else Path(name).stem
        debug_by_stem[stem].append(Path(entry.path))

    def pick_debug(candidates):
        if not candidates:
            return None
        for tag in ('_4_final_saved_crops', '_3_contours', '_1_original'):
            for p in candidates:
                if tag in p.name:
                    return p
        for p in sorted(candidates):
            if '_2_diff' not in p.name:
                return p
        return candidates[0]

    for img_name, crops in sorted(image_crops.items()):
        img_stem = Path(img_name).stem
        stem = f'{cam_prefix}__{img_stem}'
        debug_img = pick_debug(debug_by_stem.get(stem, []))
        if crops:
            tasks.append((debug_img, img_name, crops, cam_dir.name, bbox_map))

total_images = len(tasks)
total_crops = sum(len(c) for _, _, c, _, _ in tasks)
all_crop_fns = {cf for _, _, crops, _, _ in tasks for _, cf in crops}


def clamp_task_idx(idx):
    return max(0, min(int(idx), total_images - 1))


# ── Session: remember where the user left off and resume there ────────────────
SESSION_FILE = OUTPUT_DIR / 'session.json'


def read_session_data():
    if not SESSION_FILE.exists():
        return {}
    try:
        data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def coerce_bool(raw, default=False):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in ('1', 'true', 'yes', 'on'):
            return True
        if val in ('0', 'false', 'no', 'off'):
            return False
    return default


DEFAULT_LABEL_TINT_PERCENT = 4
MAX_LABEL_TINT_PERCENT = 50
LABEL_TINT_STEP_PERCENT = 2
LABEL_TINT_PRESETS = (0, 4, 10, 20, 30, 50)
DEFAULT_AFTER_LABEL_ACTION = 'unselect'
AFTER_LABEL_ACTIONS = ('unselect', 'stay', 'next')
AFTER_LABEL_BUTTON_TEXT = {'unselect': 'none', 'stay': 'same', 'next': 'next'}
LABEL_TEXT_FS = 0.58
LABEL_TEXT_MIN_FS = 0.32

SESSION_BOOL_SETTINGS = {
    'batch_mode': False,
    'show_bbox_labels': True,
    'show_main_bbox_numbers': False,
    'show_labeled_boxes': True,
    'show_background_boxes': False,
    'click_bbox_preview': True,
    'second_click_preview': True,
    'skip_labeled_crops': False,
    'show_only_unlabeled': False,
    'help_open': False,
}

CONTROL_HELP = {
    'batch_mode': 'OFF: label keys change the selected crop. ON: with no crop selected, a label key labels every unlabeled crop in this image.',
    'arrow_mode': 'Choose what Left/Right keys do: change images, or move between crop thumbnails.',
    'after_label_action': 'After labeling one crop: select nothing, keep the same crop selected, or select the next crop.',
    'label_tint_down': 'Make the color wash on already-labeled crop thumbnails weaker.',
    'label_tint_cycle': 'Cycle through common color-wash strengths for already-labeled crop thumbnails.',
    'label_tint_up': 'Make the color wash on already-labeled crop thumbnails stronger.',
    'show_only_unlabeled': 'Show only crops without a saved label in the crop strip.',
    'skip_labeled_crops': 'When navigating crops, jump over crops that already have labels.',
    'show_bbox_labels': 'Left image: show or hide class-name text on detected boxes.',
    'show_main_bbox_numbers': 'Left image: show or hide crop index numbers on detected boxes.',
    'show_labeled_boxes': 'Left image: show or hide colored boxes for already-labeled crops.',
    'show_background_boxes': 'Left image: include or hide boxes for crops labeled background.',
    'click_bbox_preview': 'Debug image click: ON opens the crop preview; OFF only selects the matching crop.',
    'second_click_preview': 'Crop strip: ON opens preview when you click the selected crop again.',
    'help_open': 'Show or hide this full explanation panel for the bottom buttons.',
}


def normalized_settings(source):
    data = source if isinstance(source, dict) else {}
    nav_mode = data.get('nav_mode', 'image')
    if nav_mode not in ('image', 'crop'):
        nav_mode = 'image'
    arrow_mode = data.get('arrow_mode', nav_mode)
    if arrow_mode not in ('crop', 'image'):
        arrow_mode = nav_mode
    try:
        tint = int(data.get('label_tint_percent', DEFAULT_LABEL_TINT_PERCENT))
    except (TypeError, ValueError):
        tint = DEFAULT_LABEL_TINT_PERCENT
    tint = max(0, min(MAX_LABEL_TINT_PERCENT, tint))
    after_label = data.get('after_label_action', DEFAULT_AFTER_LABEL_ACTION)
    if after_label == 'none':
        after_label = 'unselect'
    if after_label not in AFTER_LABEL_ACTIONS:
        after_label = DEFAULT_AFTER_LABEL_ACTION
    settings = {
        'nav_mode': nav_mode,
        'arrow_mode': arrow_mode,
        'label_tint_percent': tint,
        'after_label_action': after_label,
    }
    for key, default in SESSION_BOOL_SETTINGS.items():
        settings[key] = coerce_bool(data.get(key, default), default)
    return settings


def save_session(task_idx):
    if not tasks:
        return
    try:
        idx = clamp_task_idx(task_idx)
        _, img_name, _, cam_name, _ = tasks[idx]
        current_settings = normalized_settings(state if 'state' in globals() else {})
        data = {
            'results_dir': str(RESULTS_DIR),
            'cam_name': cam_name,
            'image_name': img_name,
            'task_idx': idx,
        }
        data.update(current_settings)
        SESSION_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except Exception:
        pass


def load_initial_task_idx():
    if not tasks:
        return 0
    data = read_session_data()
    if not data:
        return 0
    cam_name = data.get('cam_name')
    image_name = data.get('image_name')
    for i, (_, im, _, cam, _) in enumerate(tasks):
        if cam == cam_name and im == image_name:
            return i
    saved = data.get('task_idx', 0)
    return clamp_task_idx(saved) if isinstance(saved, int) else 0


initial_task_idx = load_initial_task_idx()
if initial_task_idx > 0:
    print(f'Resuming session at task {initial_task_idx + 1}/{len(tasks)}')

if tasks:
    load_progress_for_task(initial_task_idx)
done_crops = sum(1 for fn in progress if fn in all_crop_fns)

print(
    f'Images: {total_images} | Total crops: {total_crops} | '
    f'Labeled: {done_crops} | Remaining: {total_crops - done_crops}'
)

if not tasks:
    print('No tasks found. Check --results path.')
    sys.exit(0)

bbox_total = sum(len(bm) for _, _, _, _, bm in tasks)
print(
    f'bbox entries: {bbox_total}/{total_crops}'
    + (' -- WARNING: no bbox data, debug sync disabled' if bbox_total == 0 else '')
)

# ── UI constants ──────────────────────────────────────────────────────────────
# Layout (top → bottom):
#   HEADER_H px  — title + key hints
#   DEBUG panel  — full-width debug image, centred horizontally
#   CROP strip   — CROP_COLS thumbnails, one row at a time
#   FOOTER_H px  — toggle buttons + status
WIN_W, WIN_H = 1800, 1100
PAD = 8
CROP_COLS = 6
CROP_SIZE = 220
CROP_META_H = 60
HEADER_H = 86
FOOTER_H = 155
CROP_STRIP_H = CROP_SIZE + CROP_META_H + PAD
DEBUG_TOP = HEADER_H
DEBUG_BOTTOM = WIN_H - FOOTER_H - CROP_STRIP_H
ROWS_VISIBLE = 1
# Equal horizontal gap left / between / right of the 6 crops
CROP_PAD_X = max(PAD, (WIN_W - CROP_SIZE * CROP_COLS) // (CROP_COLS + 1))

# ── Colours & badges ──────────────────────────────────────────────────────────
COLORS = {
    'bumblebee': (0, 200, 255),
    'fly': (0, 255, 0),
    'butterfly': (255, 0, 200),
    'other': (200, 200, 0),
    'insect': (0, 200, 150),
    'background': (50, 50, 210),
    'unsure': (100, 100, 100),
    None: (60, 60, 60),
}
BADGES = {
    'bumblebee': 'bumblebee',
    'fly': 'fly',
    'butterfly': 'butterfly',
    'other': 'other',
    'insect': 'insect',
    'background': 'BG',
    'unsure': 'unsure',
    None: '',
}


def get_color(label):
    return COLORS.get(label, COLORS[None])


def get_badge(label):
    return BADGES.get(label, (label[:3].upper() if label else ''))


# ── Keybindings ───────────────────────────────────────────────────────────────
KEYS = {
    'prev_image': ('a', 'A'),
    'next_image': ('d', 'D'),
    'preview': ('p', 'P'),
    'clear_image': ('c', 'C'),
    'quit': ('q', 'Q'),
    # R: combined nav-mode toggle (image ↔ crop)
    'nav_mode_toggle': ('r', 'R'),
    'label_background': ('b',),
    'label_bumblebee': ('1',),
    'label_fly': ('2',),
    'label_butterfly': ('3',),
    'label_other': ('4',),
    'label_unsure': ('u',),
    'batch_mode_toggle': ('\t', 'e', 'E'),
    'batch_background': (),
    'batch_bumblebee': (),
    'batch_fly': (),
    'batch_butterfly': (),
    'batch_other': (),
    'batch_unsure': (),
}

KEY_ORDS = {action: tuple(ord(c) for c in chars) for action, chars in KEYS.items()}
LABEL_KEY_ORDS = {
    ord(c): action[len('label_') :]
    for action, chars in KEYS.items()
    if action.startswith('label_')
    for c in chars
}
BATCH_KEY_ORDS = {
    ord(c): action[len('batch_') :]
    for action, chars in KEYS.items()
    if action.startswith('batch_') and action != 'batch_mode_toggle'
    for c in chars
}


def _key_label(action):
    return KEYS.get(action, ('?',))[0].upper()


# ── Caches ────────────────────────────────────────────────────────────────────
thumb_cache: dict = {}  # str(path) -> (thumb_bgr, orig_w, orig_h, display_h)
row_heights_cache: dict = {}  # task_idx -> list[int] (only for unfiltered views)
debug_cache: dict = {}  # str(path) -> (canvas, coord_scale, ox, oy, draw_x)


def get_row_heights(task_idx: int, visible_indices=None) -> list:
    task_idx = clamp_task_idx(task_idx)
    cache_key = task_idx if visible_indices is None else None
    if cache_key is not None and cache_key in row_heights_cache:
        return row_heights_cache[task_idx]
    _, _, crops, _, _ = tasks[task_idx]
    if visible_indices is None:
        visible_indices = list(range(len(crops)))
    n_rows = max(1, (len(visible_indices) - 1) // CROP_COLS + 1)
    heights = []
    for r in range(n_rows):
        row_start = r * CROP_COLS
        rh = CROP_SIZE
        for crop_idx in visible_indices[row_start : row_start + CROP_COLS]:
            cp, _ = crops[crop_idx]
            entry = thumb_cache.get(str(cp))
            if entry:
                rh = max(rh, entry[3])
        heights.append(rh)
    if cache_key is not None:
        row_heights_cache[task_idx] = heights
    return heights


# ── ROI offset helper ─────────────────────────────────────────────────────────
def read_debug_transform(debug_path) -> tuple:
    if debug_path is None:
        return 0, 0, 1.0
    stem = Path(str(debug_path)).stem
    if '_4_final_saved_crops' not in stem:
        return 0, 0, 1.0
    offset_path = Path(str(debug_path)).parent / (
        stem.replace('_4_final_saved_crops', '_4_offset') + '.json'
    )
    if not offset_path.exists():
        return 0, 0, 1.0
    try:
        d = json.loads(offset_path.read_text(encoding='utf-8'))
        return int(d.get('ox', 0)), int(d.get('oy', 0)), float(d.get('scale', 1.0))
    except Exception:
        return 0, 0, 1.0


# ── Debug-image cache — full-width, horizontally centred ─────────────────────
def load_debug_base(path):
    """Return (canvas_copy, coord_scale, ox, oy, draw_x).
    The debug image is scaled to fit the full-width panel and centred;
    draw_x is the left pixel of the image within the canvas."""
    tw = WIN_W
    th = DEBUG_BOTTOM - DEBUG_TOP
    if path is None or not Path(path).exists():
        blank = np.zeros((th, tw, 3), dtype=np.uint8)
        cv2.putText(
            blank,
            'No debug image',
            (20, th // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (160, 160, 160),
            2,
        )
        return blank, 1.0, 0, 0, 0
    key = str(path)
    if key not in debug_cache:
        img = cv2.imread(key)
        if img is None:
            debug_cache[key] = (np.zeros((th, tw, 3), dtype=np.uint8), 1.0, 0, 0, 0)
        else:
            h, w = img.shape[:2]
            view_scale = min(tw / w, th / h)
            nw, nh = int(w * view_scale), int(h * view_scale)
            scaled = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((th, tw, 3), dtype=np.uint8)
            draw_x = (tw - nw) // 2  # centre horizontally
            canvas[:nh, draw_x : draw_x + nw] = scaled
            ox, oy, storage_scale = read_debug_transform(path)
            coord_scale = view_scale * storage_scale
            debug_cache[key] = (canvas, coord_scale, ox, oy, draw_x)
    base, coord_scale, ox, oy, draw_x = debug_cache[key]
    return base.copy(), coord_scale, ox, oy, draw_x


# ── Bbox overlay helper ───────────────────────────────────────────────────────
def draw_bbox_overlay(
    img,
    crops,
    bbox_map,
    crops_labels,
    sel,
    scale,
    ox,
    oy,
    num_fs=0.22,
    show_all_numbers=False,
    show_label_badges=True,
    show_labeled_boxes=True,
    show_background_boxes=False,
    draw_x=0,
):
    """draw_x: horizontal offset where the scaled image starts in the canvas."""
    SEL_COLOR = (180, 0, 255)

    for i, (_, crop_fn) in enumerate(crops):
        label = crops_labels.get(crop_fn)
        if label is None or crop_fn not in bbox_map:
            continue
        bx, by, bw, bh = bbox_map[crop_fn]
        dx = int((bx - ox) * scale) + draw_x
        dy = int((by - oy) * scale)
        dw = int(bw * scale)
        dh = int(bh * scale)
        color = get_color(label)
        if show_labeled_boxes and (label != 'background' or show_background_boxes):
            cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), color, 2)
        if not show_label_badges:
            continue
        badge = get_badge(label)
        fs = (
            max(0.18, num_fs - 0.02)
            if label == 'background'
            else max(0.24, num_fs + 0.05)
        )
        (tw_b, th_b), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        tx = max(1, dx)
        ty = max(th_b + 4, dy - 4 if label != 'background' else dy + th_b + 3)
        cv2.rectangle(img, (tx - 2, ty - th_b - 3), (tx + tw_b + 4, ty + 3), color, -1)
        cv2.putText(img, badge, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 1)

    if show_all_numbers:
        for i, (_, crop_fn) in enumerate(crops):
            if crop_fn not in bbox_map:
                continue
            bx, by, bw, bh = bbox_map[crop_fn]
            dx = int((bx - ox) * scale) + draw_x
            dy = int((by - oy) * scale)
            num_txt = str(i)
            (tw_n, th_n), _ = cv2.getTextSize(
                num_txt, cv2.FONT_HERSHEY_SIMPLEX, num_fs, 1
            )
            nx = max(1, dx)
            ny = max(th_n + 2, dy - 3)
            color = SEL_COLOR if i == sel else (245, 245, 245)
            cv2.rectangle(
                img, (nx - 1, ny - th_n - 2), (nx + tw_n + 2, ny + 2), (35, 35, 35), -1
            )
            cv2.putText(
                img, num_txt, (nx, ny), cv2.FONT_HERSHEY_SIMPLEX, num_fs, color, 1
            )

    if sel is None or sel >= len(crops):
        return
    crop_fn = crops[sel][1]
    if crop_fn not in bbox_map:
        return
    bx, by, bw, bh = bbox_map[crop_fn]
    dx = int((bx - ox) * scale) + draw_x
    dy = int((by - oy) * scale)
    dw = int(bw * scale)
    dh = int(bh * scale)
    cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), SEL_COLOR, 2)
    if not show_all_numbers:
        num_txt = str(sel)
        (tw_n, th_n), _ = cv2.getTextSize(num_txt, cv2.FONT_HERSHEY_SIMPLEX, num_fs, 1)
        nx, ny = dx + 1, dy + th_n + 1
        cv2.rectangle(
            img, (nx - 1, ny - th_n - 1), (nx + tw_n + 1, ny + 1), SEL_COLOR, -1
        )
        cv2.putText(
            img, num_txt, (nx, ny), cv2.FONT_HERSHEY_SIMPLEX, num_fs, (255, 255, 255), 1
        )


# ── State ─────────────────────────────────────────────────────────────────────
_sess = read_session_data()
_s = normalized_settings(_sess)

state = {
    'task_idx': initial_task_idx,
    'selected_idx': None,
    'scroll_row': 0,
    'overlay': None,
    'overlay_kind': None,
    'last_batch': None,
    'last_single_label': None,
    # nav_mode: "image" = arrows nav images, label keys batch
    #           "crop"  = arrows nav crops,  label keys label selected
    'nav_mode': _s['nav_mode'],
    'arrow_mode': _s['arrow_mode'],
    'label_tint_percent': _s['label_tint_percent'],
    'after_label_action': _s['after_label_action'],
    'hover_x': -1,
    'hover_y': -1,
    'filter_label': None,
}
for _k in SESSION_BOOL_SETTINGS:
    state[_k] = _s[_k]

click_buf = [None]
trackbar_buf = [None]
ui_controls = []


def on_trackbar(val):
    trackbar_buf[0] = clamp_task_idx(val)


# ── Filter / visibility helpers ───────────────────────────────────────────────
def get_visible_crop_indices(task_idx=None):
    task_idx = state['task_idx'] if task_idx is None else clamp_task_idx(task_idx)
    _, _, crops, _, _ = tasks[task_idx]
    filter_label = state.get('filter_label')
    show_only_unlabeled = state.get('show_only_unlabeled', False)
    indices = []
    for i, (_, crop_fn) in enumerate(crops):
        label = progress.get(crop_fn)
        if filter_label is not None and label != filter_label:
            continue
        if show_only_unlabeled and crop_fn in progress:
            continue
        indices.append(i)
    return indices


def get_selectable_crop_indices(task_idx=None):
    indices = get_visible_crop_indices(task_idx)
    if state.get('skip_labeled_crops', False):
        _, _, crops, _, _ = tasks[
            state['task_idx'] if task_idx is None else clamp_task_idx(task_idx)
        ]
        indices = [i for i in indices if crops[i][1] not in progress]
    return indices


def get_display_position(crop_idx, task_idx=None):
    try:
        return get_visible_crop_indices(task_idx).index(crop_idx)
    except ValueError:
        return None


def scroll_crop_into_view(crop_idx):
    pos = get_display_position(crop_idx)
    if pos is None:
        return
    max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
    row = pos // CROP_COLS
    if row >= state['scroll_row'] + ROWS_VISIBLE:
        state['scroll_row'] = min(row - ROWS_VISIBLE + 1, max_scroll)
    elif row < state['scroll_row']:
        state['scroll_row'] = row


def pick_adjacent_crop_index(current, direction, stay_at_edge=True):
    indices = get_selectable_crop_indices()
    if not indices:
        return None
    if current is None:
        return indices[0] if direction > 0 else indices[-1]
    if direction > 0:
        for idx in indices:
            if idx > current:
                return idx
        return indices[-1] if stay_at_edge else None
    for idx in reversed(indices):
        if idx < current:
            return idx
    return indices[0] if stay_at_edge else None


_visible_tasks_cache: list = []
_visible_tasks_filter: object = None


def get_visible_task_indices():
    global _visible_tasks_cache, _visible_tasks_filter
    filter_label = state.get('filter_label')
    if filter_label == _visible_tasks_filter and _visible_tasks_cache:
        return _visible_tasks_cache
    if filter_label is None:
        _visible_tasks_cache = list(range(total_images))
    else:
        _visible_tasks_cache = []
        for i, (_, _, crops, _, _) in enumerate(tasks):
            for _, crop_fn in crops:
                if progress.get(crop_fn) == filter_label:
                    _visible_tasks_cache.append(i)
                    break
    _visible_tasks_filter = filter_label
    return _visible_tasks_cache


def invalidate_visible_tasks_cache():
    global _visible_tasks_filter
    _visible_tasks_filter = None


def navigate_task(direction):
    visible = get_visible_task_indices()
    if not visible:
        return
    cur = state['task_idx']
    try:
        pos = visible.index(cur)
    except ValueError:
        pos = 0
        for k, v in enumerate(visible):
            if v > cur:
                pos = k if direction > 0 else max(0, k - 1)
                break
        else:
            pos = len(visible) - 1
    new_pos = pos + direction
    if new_pos < 0 or new_pos >= len(visible):
        return
    new = visible[new_pos]
    load_progress_for_task(new)
    save_session(new)
    state.update(
        {
            'task_idx': new,
            'selected_idx': None,
            'scroll_row': 0,
            'last_batch': None,
            'last_single_label': None,
        }
    )
    cv2.setTrackbarPos('Image', WINDOW, new)


def clamp_scroll_to_visible_rows():
    max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
    state['scroll_row'] = max(0, min(state['scroll_row'], max_scroll))


def get_total_rows():
    return len(get_row_heights(state['task_idx'], get_visible_crop_indices()))


# ── Footer rendering ──────────────────────────────────────────────────────────
def put_fitted_text(
    img, text, x, y, max_w, fs=0.34, color=(220, 220, 220), thickness=1
):
    while (
        fs > 0.20
        and cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, thickness)[0][0] > max_w
    ):
        fs -= 0.02
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, color, thickness)


def footer_control_at(x, y):
    for ctrl in reversed(ui_controls):
        x1, y1, x2, y2 = ctrl['rect']
        if x1 <= x <= x2 and y1 <= y <= y2:
            return ctrl
    return None


def add_footer_button(canvas, x, y, w, h, key, text, active=False):
    fill = (70, 115, 80) if active else (45, 45, 45)
    border = (130, 190, 140) if active else (95, 95, 95)
    text_color = (245, 245, 245) if active else (180, 180, 180)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), fill, -1)
    cv2.rectangle(canvas, (x, y), (x + w, y + h), border, 1)
    put_fitted_text(canvas, text, x + 6, y + h - 8, w - 12, 0.32, text_color, 1)
    ui_controls.append({'type': 'button', 'key': key, 'rect': (x, y, x + w, y + h)})


def draw_footer_tip(canvas, text):
    x0, y0 = 10, WIN_H - FOOTER_H - 38
    w, h = WIN_W - 20, 30
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (22, 32, 26), -1)
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (105, 150, 110), 1)
    put_fitted_text(canvas, text, x0 + 10, y0 + 20, w - 20, 0.36, (220, 235, 220), 1)


def draw_footer_help_panel(canvas):
    x0, y0 = 10, WIN_H - FOOTER_H - 290
    w, h = WIN_W - 20, 282
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (18, 18, 18), -1)
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (120, 120, 120), 1)
    lines = [
        'Bottom controls',
        'Nav mode (R): IMAGE_NAV = arrows move between images, label keys batch-label; CROP_NAV = arrows move between crops, label keys label selected crop.',
        'Label all OFF: normal mode. Label keys change the selected crop only.',
        'Label all ON: if no crop is selected, one label key labels all unlabeled crops.',
        'After none/same/next: after one label, select nothing, same crop, or next crop.',
        'Tint - / Tint % / Tint +: change the color wash on labeled crop thumbnails.',
        'Unlabeled only: hide crops that already have a saved label.',
        'Skip labeled: crop-arrow navigation jumps over crops that already have labels.',
        'Left labels / nums / boxes / BG boxes: control overlays on the debug image.',
        'Debug click opens: clicking a debug box opens preview; OFF only selects it.',
        '2nd crop opens: clicking the selected crop again opens preview.',
        'Filter row (bottom): show only crops / images that have a specific label.',
    ]
    y = y0 + 24
    for i, line in enumerate(lines):
        color = (235, 235, 235) if i == 0 else (185, 185, 185)
        fs = 0.42 if i == 0 else 0.33
        put_fitted_text(canvas, line, x0 + 12, y, w - 24, fs, color, 1)
        y += 24 if i == 0 else 22


def render_footer(canvas, g_done, total_rows):
    """Full-width footer with page bar + toggle buttons + filter buttons."""
    ui_controls.clear()
    x0, y0 = 0, WIN_H - FOOTER_H
    cv2.rectangle(canvas, (x0, y0), (WIN_W, WIN_H), (20, 20, 20), -1)
    cv2.line(canvas, (x0, y0), (WIN_W, y0), (55, 55, 55), 1)

    # ── Page progress bar ─────────────────────────────────────────────────────
    if total_rows > 0:
        bar_y1 = y0 + 4
        bar_y2 = bar_y1 + 10
        cv2.rectangle(canvas, (x0 + 8, bar_y1), (WIN_W - 8, bar_y2), (45, 45, 55), -1)
        seg_w = max(8, (WIN_W - 16) // max(1, total_rows))
        seg_x1 = x0 + 8 + state['scroll_row'] * seg_w
        seg_x2 = min(seg_x1 + seg_w, WIN_W - 8)
        on_last = state['scroll_row'] >= total_rows - 1
        seg_color = (0, 215, 255) if not on_last else (180, 220, 90)
        cv2.rectangle(canvas, (seg_x1, bar_y1), (seg_x2, bar_y2), seg_color, -1)
        cv2.rectangle(canvas, (x0 + 8, bar_y1), (WIN_W - 8, bar_y2), (0, 0, 0), 1)

    gap = 6
    row1 = y0 + 20
    row2 = y0 + 54
    row3 = y0 + 88
    btn_h = 28

    # ── Row 1 ─────────────────────────────────────────────────────────────────
    x = x0 + 10
    nav = state.get('nav_mode', 'image')
    add_footer_button(
        canvas,
        x,
        row1,
        140,
        btn_h,
        'nav_mode_toggle',
        f'Nav: {"CROP" if nav == "crop" else "IMAGE"}',
        nav == 'crop',
    )
    x += 140 + gap
    label_all_on = state.get('batch_mode', False)
    add_footer_button(
        canvas,
        x,
        row1,
        126,
        btn_h,
        'batch_mode',
        'Label all: ON' if label_all_on else 'Label all: OFF',
        label_all_on,
    )
    x += 126 + gap
    after_key = state.get('after_label_action', DEFAULT_AFTER_LABEL_ACTION)
    after_text = AFTER_LABEL_BUTTON_TEXT.get(after_key, after_key)
    add_footer_button(
        canvas,
        x,
        row1,
        112,
        btn_h,
        'after_label_action',
        f'After: {after_text}',
        after_key != 'unselect',
    )
    x += 112 + gap
    add_footer_button(canvas, x, row1, 54, btn_h, 'label_tint_down', 'Tint -')
    x += 54 + gap
    add_footer_button(
        canvas,
        x,
        row1,
        72,
        btn_h,
        'label_tint_cycle',
        f'Tint {int(state.get("label_tint_percent", DEFAULT_LABEL_TINT_PERCENT))}%',
    )
    x += 72 + gap
    add_footer_button(canvas, x, row1, 54, btn_h, 'label_tint_up', 'Tint +')
    x += 54 + gap
    add_footer_button(
        canvas,
        x,
        row1,
        126,
        btn_h,
        'show_only_unlabeled',
        'Unlabeled only',
        state.get('show_only_unlabeled', False),
    )
    x += 126 + gap
    add_footer_button(
        canvas,
        x,
        row1,
        112,
        btn_h,
        'skip_labeled_crops',
        'Skip labeled',
        state.get('skip_labeled_crops', False),
    )
    x += 112 + gap

    # Status text (right side of row 1)
    page_txt = f'Page {state["scroll_row"] + 1}/{max(1, total_rows)}'
    status = f'Total: {g_done}/{total_crops}  |  {page_txt}'
    put_fitted_text(
        canvas,
        status,
        x + 10,
        row1 + btn_h - 8,
        WIN_W - x - 20,
        0.38,
        (160, 160, 160),
        1,
    )

    # ── Row 2 ─────────────────────────────────────────────────────────────────
    x = x0 + 10
    add_footer_button(
        canvas,
        x,
        row2,
        102,
        btn_h,
        'show_bbox_labels',
        'Debug labels',
        state.get('show_bbox_labels', True),
    )
    x += 102 + gap
    add_footer_button(
        canvas,
        x,
        row2,
        92,
        btn_h,
        'show_main_bbox_numbers',
        'Debug nums',
        state.get('show_main_bbox_numbers', False),
    )
    x += 92 + gap
    add_footer_button(
        canvas,
        x,
        row2,
        102,
        btn_h,
        'show_labeled_boxes',
        'Debug boxes',
        state.get('show_labeled_boxes', True),
    )
    x += 102 + gap
    add_footer_button(
        canvas,
        x,
        row2,
        88,
        btn_h,
        'show_background_boxes',
        'BG boxes',
        state.get('show_background_boxes', False),
    )
    x += 88 + gap
    add_footer_button(
        canvas,
        x,
        row2,
        144,
        btn_h,
        'click_bbox_preview',
        'Debug click opens',
        state.get('click_bbox_preview', True),
    )
    x += 144 + gap
    add_footer_button(
        canvas,
        x,
        row2,
        126,
        btn_h,
        'second_click_preview',
        '2nd crop opens',
        state.get('second_click_preview', True),
    )
    x += 126 + gap
    add_footer_button(
        canvas, x, row2, 32, btn_h, 'help_open', '?', state.get('help_open', False)
    )

    # ── Row 3: label filter buttons ───────────────────────────────────────────
    x = x0 + 10
    active_filter = state.get('filter_label')
    add_footer_button(
        canvas,
        x,
        row3,
        78,
        btn_h,
        'filter_label_clear',
        'Show all',
        active_filter is None,
    )
    x += 78 + gap
    for lbl, txt, w in [
        ('bumblebee', 'BB', 90),
        ('fly', 'Fly', 60),
        ('butterfly', 'Butterfly', 90),
        ('other', 'Other', 70),
        ('background', 'BG', 60),
        ('unsure', 'Unsure', 72),
    ]:
        add_footer_button(
            canvas, x, row3, w, btn_h, f'filter_label_{lbl}', txt, active_filter == lbl
        )
        x += w + gap

    hint = 'Hover a button for help  |  ? = full explanation  |  R = toggle IMAGE/CROP nav  |  up/down = scroll pages'
    put_fitted_text(
        canvas, hint, x0 + 10, WIN_H - 10, WIN_W - 20, 0.38, (145, 145, 145), 1
    )

    hover = footer_control_at(state.get('hover_x', -1), state.get('hover_y', -1))
    if state.get('help_open', False):
        draw_footer_help_panel(canvas)
    elif hover is not None:
        tip = CONTROL_HELP.get(hover['key'])
        if tip:
            draw_footer_tip(canvas, tip)


def apply_bool_setting_side_effects(key):
    if key == 'show_only_unlabeled':
        row_heights_cache.clear()
        clamp_scroll_to_visible_rows()
        sel = state.get('selected_idx')
        if sel is not None and get_display_position(sel) is None:
            state['selected_idx'] = None
        if state['selected_idx'] is None:
            clear_last_single_label()


def toggle_footer_control(key):
    if key == 'nav_mode_toggle':
        new_nav = 'crop' if state.get('nav_mode') == 'image' else 'image'
        state['nav_mode'] = new_nav
        state['arrow_mode'] = new_nav
        if new_nav == 'crop' and state['selected_idx'] is None:
            indices = get_selectable_crop_indices()
            if indices:
                state['selected_idx'] = indices[0]
                scroll_crop_into_view(indices[0])
        elif new_nav == 'image':
            state['selected_idx'] = None
            clear_last_single_label()
        save_session(state['task_idx'])
        return
    if key == 'batch_mode':
        state['batch_mode'] = not state.get('batch_mode', False)
        save_session(state['task_idx'])
        return
    if key == 'help_open':
        state['help_open'] = not state.get('help_open', False)
        save_session(state['task_idx'])
        return
    if key == 'filter_label_clear':
        state['filter_label'] = None
        invalidate_visible_tasks_cache()
        row_heights_cache.clear()
        clamp_scroll_to_visible_rows()
        state['selected_idx'] = None
        clear_last_single_label()
        return
    if key.startswith('filter_label_'):
        lbl = key[len('filter_label_') :]
        state['filter_label'] = None if state.get('filter_label') == lbl else lbl
        invalidate_visible_tasks_cache()
        row_heights_cache.clear()
        if state['filter_label'] is not None:
            visible_tasks = get_visible_task_indices()
            if visible_tasks and state['task_idx'] not in visible_tasks:
                new = visible_tasks[0]
                load_progress_for_task(new)
                save_session(new)
                state.update(
                    {
                        'task_idx': new,
                        'scroll_row': 0,
                        'last_batch': None,
                        'last_single_label': None,
                    }
                )
                cv2.setTrackbarPos('Image', WINDOW, new)
        clamp_scroll_to_visible_rows()
        state['selected_idx'] = None
        clear_last_single_label()
        return
    if key == 'after_label_action':
        current = state.get('after_label_action', DEFAULT_AFTER_LABEL_ACTION)
        try:
            idx = AFTER_LABEL_ACTIONS.index(current)
        except ValueError:
            idx = 0
        state['after_label_action'] = AFTER_LABEL_ACTIONS[
            (idx + 1) % len(AFTER_LABEL_ACTIONS)
        ]
        save_session(state['task_idx'])
        return
    if key == 'label_tint_down':
        state['label_tint_percent'] = max(
            0,
            int(state.get('label_tint_percent', DEFAULT_LABEL_TINT_PERCENT))
            - LABEL_TINT_STEP_PERCENT,
        )
        save_session(state['task_idx'])
        return
    if key == 'label_tint_up':
        state['label_tint_percent'] = min(
            MAX_LABEL_TINT_PERCENT,
            int(state.get('label_tint_percent', DEFAULT_LABEL_TINT_PERCENT))
            + LABEL_TINT_STEP_PERCENT,
        )
        save_session(state['task_idx'])
        return
    if key == 'label_tint_cycle':
        cur = int(state.get('label_tint_percent', DEFAULT_LABEL_TINT_PERCENT))
        next_vals = [v for v in LABEL_TINT_PRESETS if v > cur]
        state['label_tint_percent'] = (
            next_vals[0] if next_vals else LABEL_TINT_PRESETS[0]
        )
        save_session(state['task_idx'])
        return
    if key in SESSION_BOOL_SETTINGS:
        state[key] = not state.get(key, SESSION_BOOL_SETTINGS[key])
        apply_bool_setting_side_effects(key)
        save_session(state['task_idx'])


def handle_footer_control_click(x, y):
    ctrl = footer_control_at(x, y)
    if ctrl is not None:
        toggle_footer_control(ctrl['key'])
        return True
    return False


# ── Label I/O helpers ─────────────────────────────────────────────────────────
def remember_single_label(idx, crop_fn):
    state['last_single_label'] = {
        'task_idx': state['task_idx'],
        'idx': idx,
        'crop_fn': crop_fn,
    }


def clear_last_single_label():
    state['last_single_label'] = None


def get_recent_single_label_crop(crops):
    last = state.get('last_single_label')
    if not last or last.get('task_idx') != state['task_idx']:
        return None
    idx = last.get('idx')
    if not isinstance(idx, int) or idx < 0 or idx >= len(crops):
        return None
    if crops[idx][1] != last.get('crop_fn'):
        return None
    return idx


# ── Overlay builders ──────────────────────────────────────────────────────────
def build_debug_overlay(task_idx: int):
    task_idx = clamp_task_idx(task_idx)
    debug_path, _, crops, _, bbox_map = tasks[task_idx]
    if debug_path is None or not Path(debug_path).exists():
        return None
    img = cv2.imread(str(debug_path))
    if img is None:
        return None
    oh, ow = img.shape[:2]
    scale = min(WIN_W / ow, WIN_H / oh, 2.0)
    shown = cv2.resize(
        img, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA
    )
    ox, oy, storage_scale = read_debug_transform(debug_path)
    coord_scale = scale * storage_scale
    crops_labels = {cf: progress.get(cf) for _, cf in crops}
    draw_bbox_overlay(
        shown,
        crops,
        bbox_map,
        crops_labels,
        state['selected_idx'],
        coord_scale,
        ox,
        oy,
        num_fs=0.28,
        show_all_numbers=True,
        show_label_badges=state.get('show_bbox_labels', True),
        show_labeled_boxes=state.get('show_labeled_boxes', True),
        show_background_boxes=state.get('show_background_boxes', False),
        draw_x=0,
    )
    sh, sw = shown.shape[:2]
    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
    cy = (WIN_H - sh) // 2
    cx = (WIN_W - sw) // 2
    canvas[cy : cy + sh, cx : cx + sw] = shown
    cv2.putText(
        canvas,
        'click bbox = select  |  A/D or arrows = prev/next  |  other click/key = close',
        (WIN_W // 2 - 330, WIN_H - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (160, 160, 160),
        1,
    )
    return canvas


def hit_debug_overlay_bbox(task_idx: int, x: int, y: int):
    task_idx = clamp_task_idx(task_idx)
    debug_path, _, crops, _, bbox_map = tasks[task_idx]
    if debug_path is None or not Path(debug_path).exists():
        return None
    img = cv2.imread(str(debug_path))
    if img is None:
        return None
    oh, ow = img.shape[:2]
    scale = min(WIN_W / ow, WIN_H / oh, 2.0)
    sw, sh = int(ow * scale), int(oh * scale)
    cx = (WIN_W - sw) // 2
    cy = (WIN_H - sh) // 2
    if not (cx <= x <= cx + sw and cy <= y <= cy + sh):
        return None
    ox, oy, storage_scale = read_debug_transform(debug_path)
    coord_scale = scale * storage_scale
    best_i = best_area = None
    for i, (_, crop_fn) in enumerate(crops):
        if crop_fn not in bbox_map:
            continue
        bx, by, bw, bh = bbox_map[crop_fn]
        dx = cx + int((bx - ox) * coord_scale)
        dy = cy + int((by - oy) * coord_scale)
        dw = int(bw * coord_scale)
        dh = int(bh * coord_scale)
        if dx - 8 <= x <= dx + dw + 8 and dy - 8 <= y <= dy + dh + 8:
            area = max(1, dw * dh)
            if best_area is None or area < best_area:
                best_i = i
                best_area = area
    return best_i


def build_preview_overlay(crop_path, crop_fn):
    img = cv2.imread(str(crop_path))
    if img is None:
        return None
    orig_h, orig_w = img.shape[:2]
    scale = min((WIN_W - 40) / orig_w, (WIN_H - 60) / orig_h, 4.0)
    img = cv2.resize(
        img,
        (int(orig_w * scale), int(orig_h * scale)),
        interpolation=cv2.INTER_NEAREST if scale > 1 else cv2.INTER_AREA,
    )
    ih, iw = img.shape[:2]
    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
    cy = (WIN_H - ih) // 2
    cx = (WIN_W - iw) // 2
    canvas[cy : cy + ih, cx : cx + iw] = img
    info = f'{crop_fn}  |  {orig_w}x{orig_h}px  |  click or any key to close'
    cv2.putText(
        canvas,
        info,
        (10, WIN_H - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.4,
        (160, 160, 160),
        1,
    )
    return canvas


# ── Mouse ─────────────────────────────────────────────────────────────────────
def on_mouse(event, x, y, flags, param):
    state['hover_x'] = x
    state['hover_y'] = y

    if state['overlay'] is not None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if state['overlay_kind'] == 'debug':
                hit_i = hit_debug_overlay_bbox(state['task_idx'], x, y)
                if hit_i is not None:
                    state['selected_idx'] = hit_i
                    clear_last_single_label()
                    scroll_crop_into_view(hit_i)
            state['overlay'] = None
            state['overlay_kind'] = None
        return

    _, _, crops, _, _ = tasks[state['task_idx']]
    max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)

    if event == cv2.EVENT_MOUSEWHEEL:
        signed = flags if flags < 2**31 else flags - 2**32
        state['scroll_row'] = max(
            0, min(state['scroll_row'] + (-1 if signed > 0 else 1), max_scroll)
        )
        return

    if event == cv2.EVENT_MOUSEMOVE:
        return

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    # Footer (full width)
    if y >= WIN_H - FOOTER_H:
        handle_footer_control_click(x, y)
        return

    # Debug panel (full width, between header and crop strip)
    if DEBUG_TOP <= y < DEBUG_BOTTOM:
        debug_path = tasks[state['task_idx']][0]
        key_dp = str(debug_path) if debug_path else ''
        if key_dp in debug_cache:
            _, dbg_scale, dbg_ox, dbg_oy, dbg_draw_x = debug_cache[key_dp]
            _, _, crops_cur, _, bbox_map = tasks[state['task_idx']]
            local_y = y - DEBUG_TOP
            for i, (_, crop_fn) in enumerate(crops_cur):
                if crop_fn not in bbox_map:
                    continue
                bx, by, bw, bh = bbox_map[crop_fn]
                dx = int((bx - dbg_ox) * dbg_scale) + dbg_draw_x
                dy = int((by - dbg_oy) * dbg_scale)
                dw = int(bw * dbg_scale)
                dh = int(bh * dbg_scale)
                if dx - 4 <= x <= dx + dw + 4 and dy - 4 <= local_y <= dy + dh + 4:
                    click_buf[0] = ('bbox', i)
                    return
        click_buf[0] = -2
        return

    # Crop strip
    if DEBUG_BOTTOM <= y < WIN_H - FOOTER_H:
        visible_indices = get_visible_crop_indices()
        for display_pos, i in enumerate(visible_indices):
            x1, y1, x2, y2 = crop_rect(display_pos, visible_indices)
            if y1 < 0:
                continue
            if x1 <= x <= x2 and y1 <= y <= y2:
                click_buf[0] = -3 if state['selected_idx'] == i else i
                return
    click_buf[0] = -1


# ── Layout helper ─────────────────────────────────────────────────────────────
def crop_rect(display_pos: int, visible_indices=None):
    """(x1, y1, x2, y2). Crops are in the bottom strip; only the row
    matching state["scroll_row"] is visible — others get a sentinel."""
    if visible_indices is None:
        visible_indices = get_visible_crop_indices()
    col = display_pos % CROP_COLS
    row_of_idx = display_pos // CROP_COLS

    if row_of_idx != state['scroll_row']:
        return 0, -9999, CROP_SIZE, -9999 + CROP_SIZE

    y = DEBUG_BOTTOM + PAD
    x1 = CROP_PAD_X + col * (CROP_SIZE + CROP_PAD_X)

    _, _, crops, _, _ = tasks[state['task_idx']]
    if display_pos < len(visible_indices):
        crop_idx = visible_indices[display_pos]
        entry = thumb_cache.get(str(crops[crop_idx][0]))
        crop_h = entry[3] if entry else CROP_SIZE
    else:
        crop_h = CROP_SIZE

    return x1, y, x1 + CROP_SIZE, y + crop_h


# ── Label I/O ─────────────────────────────────────────────────────────────────
def apply_label(crop_fn, crop_path, label):
    if crop_fn in progress:
        old_label = progress[crop_fn]
        for old_dest in (
            LABELED_DIR / old_label / crop_fn,
            LABELED_DIR / old_label / f'{state["task_idx"]}_{crop_fn}',
        ):
            if old_dest.exists():
                old_dest.unlink()
    dest = LABELED_DIR / label / crop_fn
    if dest.exists():
        dest = LABELED_DIR / label / f'{state["task_idx"]}_{crop_fn}'
    shutil.copy2(crop_path, dest)
    progress[crop_fn] = label
    invalidate_visible_tasks_cache()
    save_progress()


def batch_label_or_undo(
    state, label, tasks, progress, labeled_dir, save_progress, apply_label
):
    _, _, crops, _, _ = tasks[state['task_idx']]
    last = state.get('last_batch')
    if last and last['task_idx'] == state['task_idx'] and last['label'] == label:
        undone = 0
        for crop_fn in last['crops']:
            if progress.get(crop_fn) == label:
                old_label = progress[crop_fn]
                for old in (
                    labeled_dir / old_label / crop_fn,
                    labeled_dir / old_label / f'{state["task_idx"]}_{crop_fn}',
                ):
                    if old.exists():
                        old.unlink()
                del progress[crop_fn]
                undone += 1
        if undone:
            save_progress(force=True)
            print(f'Reverted {undone} batch labels in current image')
        state['last_batch'] = None
        return
    just_labeled = []
    for crop_path, crop_fn in crops:
        if crop_fn not in progress:
            apply_label(crop_fn, crop_path, label)
            just_labeled.append(crop_fn)
    state['last_batch'] = (
        {'task_idx': state['task_idx'], 'label': label, 'crops': just_labeled}
        if just_labeled
        else None
    )


# ── Render ────────────────────────────────────────────────────────────────────
def render():
    if state['overlay'] is not None:
        return state['overlay']

    idx = clamp_task_idx(state['task_idx'])
    state['task_idx'] = idx
    sel = state['selected_idx']
    debug_path, img_name, crops, cam_name, bbox_map = tasks[idx]
    crops_labels = {cf: progress.get(cf) for _, cf in crops}
    visible_indices = get_visible_crop_indices(idx)
    heights = get_row_heights(idx, visible_indices)
    total_rows = len(heights)
    clamp_scroll_to_visible_rows()

    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)

    # ── Debug panel (full width) ──────────────────────────────────────────────
    debug_panel, dbg_scale, dbg_ox, dbg_oy, dbg_draw_x = load_debug_base(debug_path)
    draw_bbox_overlay(
        debug_panel,
        crops,
        bbox_map,
        crops_labels,
        sel,
        dbg_scale,
        dbg_ox,
        dbg_oy,
        num_fs=0.20,
        show_all_numbers=state.get('show_main_bbox_numbers', False),
        show_label_badges=state.get('show_bbox_labels', True),
        show_labeled_boxes=state.get('show_labeled_boxes', True),
        show_background_boxes=state.get('show_background_boxes', False),
        draw_x=dbg_draw_x,
    )
    dh, dw = debug_panel.shape[:2]
    canvas[DEBUG_TOP : DEBUG_TOP + dh, :dw] = debug_panel

    # ── Header ────────────────────────────────────────────────────────────────
    cv2.rectangle(canvas, (0, 0), (WIN_W, HEADER_H - 2), (25, 25, 25), -1)
    done_this = sum(1 for _, cf in crops if cf in progress)
    g_done = sum(1 for fn in progress if fn in all_crop_fns)
    more_txt = (
        '  [MORE CROPS]' if total_rows > state['scroll_row'] + ROWS_VISIBLE else ''
    )
    title = (
        f'[{idx + 1}/{total_images}]  {cam_name} / {Path(img_name).name}'
        f'  ({done_this}/{len(crops)} labeled){more_txt}'
    )
    cv2.putText(
        canvas, title, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1
    )

    # nav_mode badge (top-right)
    nav = state.get('nav_mode', 'image')
    if nav == 'crop':
        badge_txt = 'CROP NAV'
        (tw_b, th_b), _ = cv2.getTextSize(badge_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        bx1 = WIN_W - tw_b - 24
        cv2.rectangle(canvas, (bx1, 4), (WIN_W - 8, th_b + 14), (40, 200, 255), -1)
        cv2.putText(
            canvas,
            badge_txt,
            (bx1 + 8, th_b + 9),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            2,
        )
    elif state.get('batch_mode'):
        badge_txt = 'LABEL ALL'
        (tw_b, th_b), _ = cv2.getTextSize(badge_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        bx1 = WIN_W - tw_b - 24
        cv2.rectangle(canvas, (bx1, 4), (WIN_W - 8, th_b + 14), (40, 200, 255), -1)
        cv2.putText(
            canvas,
            badge_txt,
            (bx1 + 8, th_b + 9),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            2,
        )

    bg_k = _key_label('label_background')
    bb_k = _key_label('label_bumblebee')
    fly_k = _key_label('label_fly')
    but_k = _key_label('label_butterfly')
    oth_k = _key_label('label_other')
    un_k = _key_label('label_unsure')
    if nav == 'crop':
        arrow_help = '<-/-> = prev/next crop | up/down = up/down row'
        label_help = 'label = label selected + advance'
    else:
        arrow_help = '<-/-> or A/D = prev/next image | up/down = scroll'
        label_help = 'label = batch all unlabeled (twice = undo)'
    instruction = (
        f'{bg_k}=bg {bb_k}=BB {fly_k}=fly {but_k}=but {oth_k}=other {un_k}=unsure'
        f' | R=nav mode  Tab/E=label-all  {_key_label("clear_image")}=clear'
        f' {_key_label("preview")}=preview  {_key_label("quit")}=quit'
        f' | {arrow_help} | {label_help}'
    )
    instr_fs = 0.44
    while (
        cv2.getTextSize(instruction, cv2.FONT_HERSHEY_SIMPLEX, instr_fs, 1)[0][0]
        > WIN_W - 20
    ):
        instr_fs -= 0.02
        if instr_fs <= 0.34:
            break
    cv2.putText(
        canvas,
        instruction,
        (10, 62),
        cv2.FONT_HERSHEY_SIMPLEX,
        instr_fs,
        (180, 180, 180),
        1,
    )

    # ── Footer ────────────────────────────────────────────────────────────────
    render_footer(canvas, g_done, total_rows)

    # ── Crop strip ────────────────────────────────────────────────────────────
    grid_bottom = WIN_H - FOOTER_H
    for display_pos, i in enumerate(visible_indices):
        crop_path, crop_fn = crops[i]
        x1, y1, x2, y2 = crop_rect(display_pos, visible_indices)
        if y1 < 0:
            continue

        entry = thumb_cache.get(str(crop_path))
        if entry is None:
            raw = cv2.imread(str(crop_path))
            if raw is None:
                entry = (
                    np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8),
                    0,
                    0,
                    CROP_SIZE,
                )
            else:
                oh, ow = raw.shape[:2]
                sc = CROP_SIZE / max(ow, oh)
                t = cv2.resize(
                    raw,
                    (max(1, int(ow * sc)), max(1, int(oh * sc))),
                    interpolation=cv2.INTER_AREA,
                )
                entry = (t, ow, oh, t.shape[0])
            thumb_cache[str(crop_path)] = entry

        thumb, orig_w, orig_h, _ = entry
        th_h, th_w = thumb.shape[:2]
        tx, ty = x1, y1

        clip = min(th_h, grid_bottom - CROP_META_H - ty)
        if clip > 0 and ty >= 0 and tx + th_w <= WIN_W:
            canvas[ty : ty + clip, tx : tx + th_w] = thumb[:clip]

        label = crops_labels.get(crop_fn)
        color = get_color(label)
        border = 6 if i == sel else 2
        border_color = (180, 0, 255) if i == sel else color
        cv2.rectangle(
            canvas,
            (tx - 2, ty - 2),
            (tx + th_w + 2, ty + th_h + 2),
            border_color,
            border,
        )

        if label is not None and clip > 0:
            tint_alpha = (
                max(
                    0,
                    min(
                        MAX_LABEL_TINT_PERCENT,
                        int(
                            state.get('label_tint_percent', DEFAULT_LABEL_TINT_PERCENT)
                        ),
                    ),
                )
                / 100.0
            )
            if tint_alpha > 0:
                roi = canvas[ty : ty + clip, tx : tx + th_w]
                tint = np.full_like(roi, color)
                canvas[ty : ty + clip, tx : tx + th_w] = cv2.addWeighted(
                    tint, tint_alpha, roi, 1.0 - tint_alpha, 0
                )
            ovr_text = get_badge(label)
            if ovr_text:
                ovr_fs = LABEL_TEXT_FS
                (otw, oth), _ = cv2.getTextSize(
                    ovr_text, cv2.FONT_HERSHEY_SIMPLEX, ovr_fs, 2
                )
                while otw > th_w - 10 and ovr_fs > LABEL_TEXT_MIN_FS:
                    ovr_fs = max(LABEL_TEXT_MIN_FS, ovr_fs - 0.05)
                    (otw, oth), _ = cv2.getTextSize(
                        ovr_text, cv2.FONT_HERSHEY_SIMPLEX, ovr_fs, 2
                    )
                ox = tx + max(4, (th_w - otw) // 2)
                oy = ty + oth + 8
                cv2.putText(
                    canvas,
                    ovr_text,
                    (ox + 1, oy + 1),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    ovr_fs,
                    (0, 0, 0),
                    3,
                )
                cv2.putText(
                    canvas,
                    ovr_text,
                    (ox, oy),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    ovr_fs,
                    (255, 255, 255),
                    2,
                )

        # Label badge strip below thumbnail
        badge = get_badge(label)
        badge_fs = 0.48
        (bw_t, bh_t), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, badge_fs, 1)
        badge_h = bh_t + 8
        bw_px = max(28, bw_t + 10)
        cv2.rectangle(
            canvas, (tx, ty + th_h), (tx + bw_px, ty + th_h + badge_h), color, -1
        )
        cv2.putText(
            canvas,
            badge,
            (tx + 5, ty + th_h + bh_t + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            badge_fs,
            (0, 0, 0),
            1,
        )

        # Index badge (top-left corner)
        num_txt = str(i)
        fs_n = 0.50
        (nw_t, nh_t), _ = cv2.getTextSize(num_txt, cv2.FONT_HERSHEY_SIMPLEX, fs_n, 1)
        nbg = (255, 255, 255) if i == sel else (20, 20, 20)
        nfg = (0, 0, 0) if i == sel else (210, 210, 210)
        cv2.rectangle(canvas, (tx, ty), (tx + nw_t + 6, ty + nh_t + 6), nbg, -1)
        cv2.putText(
            canvas,
            num_txt,
            (tx + 3, ty + nh_t + 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            fs_n,
            nfg,
            1,
        )

        # Size + filename meta
        meta_y = ty + th_h + badge_h
        if orig_w > 0:
            size_text = f'{orig_w}x{orig_h}'
            size_fs = 0.30
            (_, size_h), _ = cv2.getTextSize(
                size_text, cv2.FONT_HERSHEY_SIMPLEX, size_fs, 1
            )
            size_y = meta_y + size_h + 7
            cv2.putText(
                canvas,
                size_text,
                (tx, size_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                size_fs,
                (140, 180, 140),
                1,
            )
        else:
            size_y = meta_y + 18
        m = _re.search(r'_crop_(\d+)', crop_fn)
        prefix = f'#{m.group(1)} ' if m else ''
        short = ('..' + crop_fn[-12:]) if len(crop_fn) > 14 else crop_fn
        file_fs = 0.28
        (_, file_h), _ = cv2.getTextSize(
            prefix + short, cv2.FONT_HERSHEY_SIMPLEX, file_fs, 1
        )
        cv2.putText(
            canvas,
            prefix + short,
            (tx, size_y + file_h + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            file_fs,
            (110, 110, 110),
            1,
        )

        # Selection glow
        if i == sel:
            ry1 = max(0, ty - 2)
            ry2 = min(canvas.shape[0], ty + th_h + 3)
            rx1 = max(0, tx - 2)
            rx2 = min(canvas.shape[1], tx + th_w + 3)
            roi = canvas[ry1:ry2, rx1:rx2]
            white = np.full_like(roi, 255)
            cv2.addWeighted(white, 0.15, roi, 0.85, 0, roi)
            canvas[ry1:ry2, rx1:rx2] = roi

    return canvas


# ── Window & main loop ────────────────────────────────────────────────────────
WINDOW = 'Pollinator Crop Labeler'
cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW, WIN_W, WIN_H)
cv2.moveWindow(WINDOW, 0, 0)
cv2.createTrackbar('Image', WINDOW, 0, max(1, total_images - 1), on_trackbar)
if initial_task_idx > 0:
    cv2.setTrackbarPos('Image', WINDOW, initial_task_idx)
cv2.setMouseCallback(WINDOW, on_mouse)

prev_keys = (65361, 2424832, 63234)
next_keys = (65363, 2555904, 63235)
up_keys = (65362, 2490368, 63232)
down_keys = (65364, 2621440, 63233)
_arrow_codes = set(prev_keys + next_keys + up_keys + down_keys)


def go_to_image(new_idx, overlay=None, overlay_kind=None):
    load_progress_for_task(new_idx)
    save_session(new_idx)
    state.update(
        {
            'task_idx': new_idx,
            'selected_idx': None,
            'scroll_row': 0,
            'last_batch': None,
            'last_single_label': None,
            'overlay': overlay,
            'overlay_kind': overlay_kind,
        }
    )
    cv2.setTrackbarPos('Image', WINDOW, new_idx)


while True:
    tb_val = clamp_task_idx(cv2.getTrackbarPos('Image', WINDOW))
    if trackbar_buf[0] is not None:
        tb_val = clamp_task_idx(trackbar_buf[0])
        trackbar_buf[0] = None
    if tb_val != state['task_idx'] and click_buf[0] is None:
        load_progress_for_task(tb_val)
        save_session(tb_val)
        state.update(
            {
                'task_idx': tb_val,
                'selected_idx': None,
                'scroll_row': 0,
                'last_batch': None,
                'last_single_label': None,
                'overlay': None,
                'overlay_kind': None,
            }
        )

    if click_buf[0] is not None:
        val = click_buf[0]
        click_buf[0] = None
        if isinstance(val, tuple) and val[0] == 'bbox':
            i = val[1]
            state['selected_idx'] = i
            clear_last_single_label()
            scroll_crop_into_view(i)
            _, _, crops, _, _ = tasks[state['task_idx']]
            if state.get('click_bbox_preview', True) and i < len(crops):
                state['overlay'] = build_preview_overlay(*crops[i])
                state['overlay_kind'] = 'preview'
        elif val == -2:
            state['overlay'] = build_debug_overlay(state['task_idx'])
            state['overlay_kind'] = 'debug'
        elif val == -3:
            sel = state['selected_idx']
            if state.get('second_click_preview', True) and sel is not None:
                _, _, crops, _, _ = tasks[state['task_idx']]
                if sel < len(crops):
                    state['overlay'] = build_preview_overlay(*crops[sel])
                    state['overlay_kind'] = 'preview'
        elif val == -1:
            state['selected_idx'] = None
            clear_last_single_label()
        else:
            state['selected_idx'] = val
            clear_last_single_label()

    cv2.imshow(WINDOW, render())
    key_raw = cv2.waitKeyEx(30)

    if key_raw == -1:
        ascii_key = None
    elif 0 <= key_raw <= 255:
        ascii_key = key_raw
    elif key_raw not in _arrow_codes and 32 <= (key_raw & 0xFF) <= 126:
        ascii_key = key_raw & 0xFF
    else:
        ascii_key = None

    # ── Overlay key handling ──────────────────────────────────────────────────
    if state['overlay'] is not None:
        if key_raw != -1:
            if state['overlay_kind'] == 'debug':
                if ascii_key in KEY_ORDS['next_image'] or key_raw in next_keys:
                    new = min(state['task_idx'] + 1, total_images - 1)
                    go_to_image(new, build_debug_overlay(new), 'debug')
                elif ascii_key in KEY_ORDS['prev_image'] or key_raw in prev_keys:
                    new = max(state['task_idx'] - 1, 0)
                    go_to_image(new, build_debug_overlay(new), 'debug')
                else:
                    state['overlay'] = None
                    state['overlay_kind'] = None
            else:
                state['overlay'] = None
                state['overlay_kind'] = None
        continue

    _, _, crops, _, _ = tasks[state['task_idx']]
    nav = state.get('nav_mode', 'image')

    # ── Preview ───────────────────────────────────────────────────────────────
    if ascii_key in KEY_ORDS['preview']:
        sel = state['selected_idx']
        if sel is not None and sel < len(crops):
            state['overlay'] = build_preview_overlay(*crops[sel])
            state['overlay_kind'] = 'preview'

    # ── Clear ─────────────────────────────────────────────────────────────────
    elif ascii_key in KEY_ORDS['clear_image']:
        removed = 0
        for _, crop_fn in crops:
            if crop_fn in progress:
                old_label = progress[crop_fn]
                for old in (
                    LABELED_DIR / old_label / crop_fn,
                    LABELED_DIR / old_label / f'{state["task_idx"]}_{crop_fn}',
                ):
                    if old.exists():
                        old.unlink()
                del progress[crop_fn]
                removed += 1
        if removed:
            save_progress(force=True)
            print(f'Cleared {removed} crops in current image')
        state['selected_idx'] = None
        clear_last_single_label()

    # ── Quit ──────────────────────────────────────────────────────────────────
    elif ascii_key in KEY_ORDS['quit']:
        save_progress(force=True)
        save_session(state['task_idx'])
        break

    # ── Nav mode toggle (R) ───────────────────────────────────────────────────
    elif ascii_key in KEY_ORDS['nav_mode_toggle']:
        toggle_footer_control('nav_mode_toggle')

    # ── Batch mode toggle (Tab/E) ─────────────────────────────────────────────
    elif ascii_key in KEY_ORDS['batch_mode_toggle']:
        state['batch_mode'] = not state.get('batch_mode', False)
        save_session(state['task_idx'])

    # ── Batch chord shortcuts ─────────────────────────────────────────────────
    elif ascii_key in BATCH_KEY_ORDS:
        label = BATCH_KEY_ORDS[ascii_key]
        batch_label_or_undo(
            state, label, tasks, progress, LABELED_DIR, save_progress, apply_label
        )
        state['selected_idx'] = None
        clear_last_single_label()

    # ── Label keys ────────────────────────────────────────────────────────────
    elif ascii_key in LABEL_KEY_ORDS:
        label = LABEL_KEY_ORDS[ascii_key]
        sel = state['selected_idx']

        if nav == 'crop':
            # CROP_NAV: always label selected crop + advance
            if sel is not None and sel < len(crops):
                apply_label(crops[sel][1], crops[sel][0], label)
                after_label = state.get(
                    'after_label_action', DEFAULT_AFTER_LABEL_ACTION
                )
                if after_label == 'next':
                    new_sel = pick_adjacent_crop_index(sel, 1, stay_at_edge=False)
                elif after_label == 'stay':
                    new_sel = sel
                else:
                    new_sel = None
                if new_sel is not None:
                    state['selected_idx'] = new_sel
                    scroll_crop_into_view(new_sel)
                else:
                    state['selected_idx'] = None
                remember_single_label(sel, crops[sel][1])
                state['last_batch'] = None
            else:
                # No crop selected in CROP_NAV → select first
                indices = get_selectable_crop_indices()
                if indices:
                    state['selected_idx'] = indices[0]
                    scroll_crop_into_view(indices[0])
        else:
            # IMAGE_NAV: crop selected → label it; else → batch
            if sel is not None and sel < len(crops):
                apply_label(crops[sel][1], crops[sel][0], label)
                remember_single_label(sel, crops[sel][1])
                state['last_batch'] = None
                # after label: unselect (keep image browsing feel)
                after_label = state.get(
                    'after_label_action', DEFAULT_AFTER_LABEL_ACTION
                )
                if after_label == 'next':
                    new_sel = pick_adjacent_crop_index(sel, 1, stay_at_edge=False)
                    if new_sel is not None:
                        state['selected_idx'] = new_sel
                        scroll_crop_into_view(new_sel)
                    else:
                        state['selected_idx'] = None
                elif after_label != 'stay':
                    state['selected_idx'] = None
            elif state.get('batch_mode'):
                batch_label_or_undo(
                    state,
                    label,
                    tasks,
                    progress,
                    LABELED_DIR,
                    save_progress,
                    apply_label,
                )
                state['selected_idx'] = None
                clear_last_single_label()
            else:
                # No crop selected, batch_mode off → try recent single, then batch
                recent_sel = get_recent_single_label_crop(crops)
                if recent_sel is not None:
                    apply_label(crops[recent_sel][1], crops[recent_sel][0], label)
                    remember_single_label(recent_sel, crops[recent_sel][1])
                    state['last_batch'] = None
                else:
                    last = state.get('last_batch')
                    if (
                        last
                        and last['task_idx'] == state['task_idx']
                        and last['label'] == label
                    ):
                        batch_label_or_undo(
                            state,
                            label,
                            tasks,
                            progress,
                            LABELED_DIR,
                            save_progress,
                            apply_label,
                        )
                    else:
                        batch_label_or_undo(
                            state,
                            label,
                            tasks,
                            progress,
                            LABELED_DIR,
                            save_progress,
                            apply_label,
                        )

    # ── Arrow keys ────────────────────────────────────────────────────────────
    elif key_raw in next_keys:
        if nav == 'crop':
            new_sel = pick_adjacent_crop_index(state['selected_idx'], 1)
            if new_sel is not None:
                state['selected_idx'] = new_sel
                scroll_crop_into_view(new_sel)
        else:
            if state.get('filter_label') is not None:
                navigate_task(+1)
            else:
                go_to_image(min(state['task_idx'] + 1, total_images - 1))

    elif key_raw in prev_keys:
        if nav == 'crop':
            new_sel = pick_adjacent_crop_index(state['selected_idx'], -1)
            if new_sel is not None:
                state['selected_idx'] = new_sel
                scroll_crop_into_view(new_sel)
        else:
            if state.get('filter_label') is not None:
                navigate_task(-1)
            else:
                go_to_image(max(state['task_idx'] - 1, 0))

    elif key_raw in down_keys:
        if nav == 'crop':
            new_sel = pick_adjacent_crop_index(
                (state['scroll_row'] * CROP_COLS)
                if state['selected_idx'] is None
                else min(
                    state['selected_idx'] + CROP_COLS,
                    len(get_visible_crop_indices()) - 1,
                ),
                1,
                stay_at_edge=True,
            )
            if new_sel is not None:
                state['selected_idx'] = new_sel
                scroll_crop_into_view(new_sel)
        else:
            max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
            state['scroll_row'] = min(state['scroll_row'] + 1, max_scroll)

    elif key_raw in up_keys:
        if nav == 'crop':
            sel = state['selected_idx']
            vis = get_visible_crop_indices()
            if sel is None:
                new_sel = vis[0] if vis else None
            else:
                pos = get_display_position(sel)
                new_pos = max(0, pos - CROP_COLS) if pos is not None else 0
                new_sel = vis[new_pos] if new_pos < len(vis) else None
            if new_sel is not None:
                state['selected_idx'] = new_sel
                scroll_crop_into_view(new_sel)
        else:
            state['scroll_row'] = max(0, state['scroll_row'] - 1)

    # ── A / D image navigation ────────────────────────────────────────────────
    elif ascii_key in KEY_ORDS['next_image']:
        if state.get('filter_label') is not None:
            navigate_task(+1)
        else:
            go_to_image(min(state['task_idx'] + 1, total_images - 1))

    elif ascii_key in KEY_ORDS['prev_image']:
        if state.get('filter_label') is not None:
            navigate_task(-1)
        else:
            go_to_image(max(state['task_idx'] - 1, 0))

cv2.destroyAllWindows()
save_progress(force=True)
save_session(state['task_idx'])

bb_n = len(list((LABELED_DIR / 'bumblebee').glob('*.jpg')))
fly_n = len(list((LABELED_DIR / 'fly').glob('*.jpg')))
but_n = len(list((LABELED_DIR / 'butterfly').glob('*.jpg')))
oth_n = len(list((LABELED_DIR / 'other').glob('*.jpg')))
bg_n = len(list((LABELED_DIR / 'background').glob('*.jpg')))
un_n = len(list((LABELED_DIR / 'unsure').glob('*.jpg')))
total_insect = bb_n + fly_n + but_n + oth_n
print(f'\nDone!')
print(
    f'  insects: {total_insect}  (BB={bb_n}  fly={fly_n}  but={but_n}  other={oth_n})'
)
print(f'  background: {bg_n}   unsure: {un_n}')
print(f'Saved to: {OUTPUT_DIR}')

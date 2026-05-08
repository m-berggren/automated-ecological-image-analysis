"""
Pollinator Crop Annotation Tool
=====================================
Left: debug image with numbered bounding boxes  |  Right: crops with index badges

Controls:
  Two navigation modes, toggle with R.

  IMAGE_NAV (default — header has no badge)
    Left / Right    -> previous / next image
    Up   / Down     -> scroll the crop grid up / down
    b 1 2 3 4 u     -> label every unlabeled crop in the current image,
                       or clear every crop already carrying that label
    Click a crop    -> select it (also flips behavior to selected-crop labels)

  CROP_NAV (header shows "CROP NAV" badge)
    Left / Right    -> move crop selection left / right
    Up   / Down     -> move crop selection up / down (by row)
    b 1 2 3 4 u     -> label the SELECTED crop, advance to next

  Labels: bg / bumblebee / fly / butterfly / other / unsure
  C   -> clear all annotations in current image
  P   -> preview selected crop (large popup)
  Q   -> quit and save

Usage:
  python3 annotate.py --results path/to/results --output path/to/annotated_crops
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

def _ui_put_text(img, text, org, fontFace, fontScale, color,
                 thickness=1, lineType=None, bottomLeftOrigin=False):
    lineType = UI_TEXT_LINE_TYPE if lineType is None else lineType
    return _cv2_put_text(
        img, text, org, fontFace, fontScale * UI_FONT_SCALE, color,
        _ui_text_thickness(thickness), lineType, bottomLeftOrigin
    )

def _ui_get_text_size(text, fontFace, fontScale, thickness):
    return _cv2_get_text_size(
        text, fontFace, fontScale * UI_FONT_SCALE,
        _ui_text_thickness(thickness)
    )

cv2.putText = _ui_put_text
cv2.getTextSize = _ui_get_text_size

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


# ── Helper to get JSON path for saving progress, based on input folder name
def get_json_path(input_folder, output_dir):
    cam_name = os.path.basename(os.fspath(input_folder))
    return Path(output_dir) / "progress" / f"{cam_name}_result.json"

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--results", type=Path, default=Path("results"))
parser.add_argument("--output",  type=Path, default=Path("annotated_crops"))
args = parser.parse_args()

RESULTS_DIR   = args.results
OUTPUT_DIR    = args.output.with_name("annotated_crops") if args.output.name == "labeled" else args.output
ANNOTATION_DIR = OUTPUT_DIR / "progress"
LABELED_DIR = OUTPUT_DIR / "labeled"
ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)

for sub in ("bumblebee", "fly", "butterfly", "other", "background", "unsure"):
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
        current_progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
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
        progress = json.loads(current_progress_file.read_text(encoding="utf-8"))
        print(f"Resuming -- {len(progress)} crops already labeled")
    else:
        progress = {}
    _save_counter = 0

# ── Collect tasks ─────────────────────────────────────────────────────────────
tasks = []
for cam_dir in sorted(RESULTS_DIR.iterdir()):
    if not cam_dir.is_dir():
        continue
    debug_dir = cam_dir / "debug"
    crop_dir  = cam_dir / "crops"
    csv_path  = cam_dir / "results.csv"
    if not (debug_dir.exists() and crop_dir.exists() and csv_path.exists()):
        continue

    image_crops: dict = defaultdict(list)
    seen_crops:  dict = defaultdict(set)   # img_name -> set of crop_fn already added
    bbox_map:    dict = {}                 # crop_fn -> (x, y, w, h) in original-image px

    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            img_name = row.get("image_name", "")
            crop_fn  = row.get("crop_filename", "")
            if not crop_fn or not (crop_dir / crop_fn).exists():
                continue
            if crop_fn in seen_crops[img_name]:   # skip duplicate CSV rows
                continue
            seen_crops[img_name].add(crop_fn)
            image_crops[img_name].append((crop_dir / crop_fn, crop_fn))
            try:
                bx = int(float(row.get("bbox_x", 0)))
                by = int(float(row.get("bbox_y", 0)))
                bw = int(float(row.get("bbox_w", 0)))
                bh = int(float(row.get("bbox_h", 0)))
                if bw > 0 and bh > 0:
                    bbox_map[crop_fn] = (bx, by, bw, bh)
            except (ValueError, TypeError):
                pass

    # Index debug_dir once: bucket files by the "{cam_prefix}__{img_stem}"
    # prefix so each image becomes one dict lookup instead of up to 5 globs.
    cam_prefix    = cam_dir.name
    debug_by_stem = defaultdict(list)
    for entry in os.scandir(debug_dir):
        if not entry.is_file():
            continue
        name = entry.name
        suffix_at = name.find("_", len(cam_prefix) + 2)  # past "{cam_prefix}__"
        stem = name[:suffix_at] if suffix_at != -1 else Path(name).stem
        debug_by_stem[stem].append(Path(entry.path))

    def pick_debug(candidates):
        if not candidates:
            return None
        for tag in ("_4_final_saved_crops", "_3_contours", "_1_original"):
            for p in candidates:
                if tag in p.name:
                    return p
        for p in sorted(candidates):
            if "_2_diff" not in p.name:
                return p
        return candidates[0]

    for img_name, crops in sorted(image_crops.items()):
        img_stem  = Path(img_name).stem
        stem      = f"{cam_prefix}__{img_stem}"
        debug_img = pick_debug(debug_by_stem.get(stem, []))
        if crops:
            tasks.append((debug_img, img_name, crops, cam_dir.name, bbox_map))

total_images = len(tasks)
total_crops  = sum(len(c) for _, _, c, _, _ in tasks)
all_crop_fns = {cf for _, _, crops, _, _ in tasks for _, cf in crops}

def clamp_task_idx(idx):
    return max(0, min(int(idx), total_images - 1))

# ── Session: remember where the user left off and resume there ────────────────
SESSION_FILE = OUTPUT_DIR / "session.json"

def save_session(task_idx):
    if not tasks:
        return
    try:
        idx = clamp_task_idx(task_idx)
        _, img_name, _, cam_name, _ = tasks[idx]
        SESSION_FILE.write_text(
            json.dumps({
                "results_dir": str(RESULTS_DIR),
                "cam_name":    cam_name,
                "image_name":  img_name,
                "task_idx":    idx,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Best-effort — never crash the UI over a session-write failure.
        pass

def load_initial_task_idx():
    """Pick up where the previous run ended. Match (cam, image) first; fall
    back to the saved index; final fallback is 0."""
    if not tasks or not SESSION_FILE.exists():
        return 0
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    cam_name   = data.get("cam_name")
    image_name = data.get("image_name")
    for i, (_, im, _, cam, _) in enumerate(tasks):
        if cam == cam_name and im == image_name:
            return i
    saved = data.get("task_idx", 0)
    return clamp_task_idx(saved) if isinstance(saved, int) else 0

initial_task_idx = load_initial_task_idx()
if initial_task_idx > 0:
    print(f"Resuming session at task {initial_task_idx + 1}/{len(tasks)}")

if tasks:
    load_progress_for_task(initial_task_idx)
done_crops   = sum(1 for fn in progress if fn in all_crop_fns)

print(f"Images: {total_images} | Total crops: {total_crops} | "
      f"Labeled: {done_crops} | Remaining: {total_crops - done_crops}")

if not tasks:
    print("No tasks found. Check --results path.")
    sys.exit(0)

bbox_total = sum(len(bm) for _, _, _, _, bm in tasks)
print(f"bbox entries: {bbox_total}/{total_crops}"
      + (" -- WARNING: no bbox data, left-right sync disabled" if bbox_total == 0 else ""))

# ── UI constants ──────────────────────────────────────────────────────────────
# Layout: header on top, full-width debug image below, then a horizontal strip
# of CROP_COLS crops at the bottom, then a status footer. Scroll moves the
# strip one row at a time (= CROP_COLS crops per page).
WIN_W, WIN_H = 1800, 1100
PAD          = 8
CROP_COLS    = 6
CROP_SIZE    = 220                         # smaller than width-fill so the
                                           # debug image up top gets more height
CROP_META_H  = 60
HEADER_H     = 86
FOOTER_H     = 58
CROP_STRIP_H = CROP_SIZE + CROP_META_H + PAD
DEBUG_TOP    = HEADER_H
DEBUG_BOTTOM = WIN_H - FOOTER_H - CROP_STRIP_H
DEBUG_W      = WIN_W                       # debug spans full width now
ROWS_VISIBLE = 1                           # one row of CROP_COLS crops at a time
# Distribute the extra horizontal space evenly: equal gap on left, between,
# and right of the crops, so the strip looks centered.
CROP_PAD_X   = max(PAD, (WIN_W - CROP_SIZE * CROP_COLS) // (CROP_COLS + 1))

# ── Colours & badges ──────────────────────────────────────────────────────────
COLORS = {
    "bumblebee":  (0,   200, 255),
    "fly":        (0,   255,   0),
    "butterfly":  (255,   0, 200),
    "other":      (200, 200,   0),
    "insect":     (0,   200, 150),   # legacy
    "background": (40,   40, 240),    # bright red (BGR)
    "unsure":     (100, 100, 100),
    None:         (60,   60,  60),
}
BADGES = {
    "bumblebee":  "bumblebee",
    "fly":        "fly",
    "butterfly":  "butterfly",
    "other":      "other",
    "insect":     "insect",
    "background": "BG",
    "unsure":     "unsure",
    None:         "",
}

def get_color(label):
    return COLORS.get(label, COLORS[None])

def get_badge(label):
    return BADGES.get(label, (label[:3].upper() if label else ""))

# ── Keybindings ───────────────────────────────────────────────────────────────
# Edit to remap. Each action maps to a tuple of single-character strings;
# all listed characters trigger that action. Arrow keys are detected from
# raw key codes elsewhere and are not configurable here.
KEYS = {
    # Mode toggle: switch between IMAGE_NAV (default — arrows nav images +
    # scroll grid; label keys batch all unlabeled) and CROP_NAV (arrows move
    # crop selection; label keys label only the selected crop).
    "nav_mode_toggle":   ("r", "R"),
    "preview":           ("p", "P"),
    "clear_image":       ("c", "C"),
    "quit":              ("q", "Q"),
    # Label keys. Behaviour depends on nav mode:
    #   IMAGE_NAV → label all unlabeled in current image (same key twice = undo)
    #   CROP_NAV  → label only the selected crop, then advance to next
    "label_background":  ("b", "B"),
    "label_bumblebee":   ("1",),
    "label_fly":         ("2",),
    "label_butterfly":   ("3",),
    "label_other":       ("4",),
    "label_unsure":      ("u", "U"),
}

KEY_ORDS = {action: tuple(ord(c) for c in chars) for action, chars in KEYS.items()}
LABEL_KEY_ORDS = {
    ord(c): action[len("label_"):]
    for action, chars in KEYS.items() if action.startswith("label_")
    for c in chars
}

def _key_label(action):
    """First character bound to `action`, uppercased — for help-text display."""
    return KEYS.get(action, ("?",))[0].upper()

# ── Thumbnail cache ───────────────────────────────────────────────────────────
# Filled lazily by render() on first access — preloading every crop at startup
# blocks the UI for minutes on large runs.
# str(path) -> (thumb_bgr, orig_w, orig_h, display_h)
thumb_cache: dict = {}

# ── Row-height cache ──────────────────────────────────────────────────────────
row_heights_cache: dict = {}

def get_row_heights(task_idx: int) -> list:
    task_idx = clamp_task_idx(task_idx)
    if task_idx in row_heights_cache:
        return row_heights_cache[task_idx]
    _, _, crops, _, _ = tasks[task_idx]
    n_rows = max(1, (len(crops) - 1) // CROP_COLS + 1)
    heights = []
    for r in range(n_rows):
        row_start = r * CROP_COLS
        rh = CROP_SIZE
        for cp, _ in crops[row_start : row_start + CROP_COLS]:
            entry = thumb_cache.get(str(cp))
            if entry:
                rh = max(rh, entry[3])
        heights.append(rh)
    row_heights_cache[task_idx] = heights
    return heights

# ── ROI offset helper ─────────────────────────────────────────────────────────
def read_debug_transform(debug_path) -> tuple:
    """Return (ox, oy, storage_scale) saved alongside the debug image."""
    if debug_path is None:
        return 0, 0, 1.0
    stem = Path(str(debug_path)).stem
    if "_4_final_saved_crops" not in stem:
        return 0, 0, 1.0
    offset_path = Path(str(debug_path)).parent / (
        stem.replace("_4_final_saved_crops", "_4_offset") + ".json"
    )
    if not offset_path.exists():
        return 0, 0, 1.0
    try:
        d = json.loads(offset_path.read_text(encoding="utf-8"))
        return int(d.get("ox", 0)), int(d.get("oy", 0)), float(d.get("scale", 1.0))
    except Exception:
        return 0, 0, 1.0

# ── Debug-image cache ─────────────────────────────────────────────────────────
# str(path) -> (base_bgr_canvas, coord_scale, ox, oy)
debug_cache: dict = {}

def load_debug_base(path):
    """Return (canvas_copy, coord_scale, ox, oy, draw_x). Debug area spans
    the full window width between the header and the crop strip; the image
    is centred horizontally so the empty right-side strip you'd otherwise
    see disappears. `draw_x` is added to bbox positions when drawing /
    hit-testing so they line up with the centred image."""
    tw = DEBUG_W
    th = DEBUG_BOTTOM - DEBUG_TOP
    if path is None or not Path(path).exists():
        blank = np.zeros((th, tw, 3), dtype=np.uint8)
        cv2.putText(blank, "No debug image", (20, th // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (160, 160, 160), 2)
        return blank, 1.0, 0, 0, 0
    key = str(path)
    if key not in debug_cache:
        img = cv2.imread(key)
        if img is None:
            debug_cache[key] = (np.zeros((th, tw, 3), dtype=np.uint8), 1.0, 0, 0, 0)
        else:
            h, w   = img.shape[:2]
            view_scale = min(tw / w, th / h)
            nw, nh = int(w * view_scale), int(h * view_scale)
            scaled = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((th, tw, 3), dtype=np.uint8)
            draw_x = (tw - nw) // 2
            canvas[:nh, draw_x:draw_x + nw] = scaled
            ox, oy, storage_scale = read_debug_transform(path)
            coord_scale = view_scale * storage_scale
            debug_cache[key] = (canvas, coord_scale, ox, oy, draw_x)
    base, coord_scale, ox, oy, draw_x = debug_cache[key]
    return base.copy(), coord_scale, ox, oy, draw_x

# ── Bbox overlay helper ───────────────────────────────────────────────────────
def draw_bbox_overlay(img, crops, bbox_map, crops_labels, sel, scale, ox, oy,
                      num_fs=0.22, show_all_numbers=False, draw_x=0):
    """Draw selected bbox plus colored borders for already-labelled crops.
    No label-name text is drawn — colour alone signals the label.
    `draw_x` is the horizontal offset where the underlying image starts in
    the canvas (for centred layouts)."""
    SEL_COLOR = (180, 0, 255)   # bright magenta

    for i, (_, crop_fn) in enumerate(crops):
        label = crops_labels.get(crop_fn)
        if label is None or crop_fn not in bbox_map:
            continue
        bx, by, bw, bh = bbox_map[crop_fn]
        dx = int((bx - ox) * scale) + draw_x
        dy = int((by - oy) * scale)
        dw = int(bw * scale)
        dh = int(bh * scale)
        cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), get_color(label), 2)

    if show_all_numbers:
        for i, (_, crop_fn) in enumerate(crops):
            if crop_fn not in bbox_map:
                continue
            bx, by, bw, bh = bbox_map[crop_fn]
            dx = int((bx - ox) * scale) + draw_x
            dy = int((by - oy) * scale)
            num_txt = str(i)
            (tw_n, th_n), _ = cv2.getTextSize(num_txt, cv2.FONT_HERSHEY_SIMPLEX, num_fs, 1)
            nx = max(1, dx)
            ny = max(th_n + 2, dy - 3)
            color = SEL_COLOR if i == sel else (245, 245, 245)
            bg = (35, 35, 35)
            cv2.rectangle(img, (nx - 1, ny - th_n - 2), (nx + tw_n + 2, ny + 2), bg, -1)
            cv2.putText(img, num_txt, (nx, ny), cv2.FONT_HERSHEY_SIMPLEX, num_fs, color, 1)

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
        cv2.rectangle(img, (nx - 1, ny - th_n - 1), (nx + tw_n + 1, ny + 1), SEL_COLOR, -1)
        cv2.putText(img, num_txt, (nx, ny), cv2.FONT_HERSHEY_SIMPLEX, num_fs, (255, 255, 255), 1)

# ── State ─────────────────────────────────────────────────────────────────────
state = {
    "task_idx":    initial_task_idx,
    "selected_idx": None,
    "scroll_row":  0,
    "overlay":     None,   # None  or  numpy array to draw fullscreen over canvas
    "overlay_kind": None,
    # Navigation mode. "image" (default): arrows nav images + scroll grid;
    # label keys batch every unlabeled crop or clear ones already labeled
    # with that label. "crop": arrows move crop selection; label keys label
    # only the selected crop. Toggle with R.
    "nav_mode":    "image",
}
click_buf = [None]
trackbar_buf = [None]

def on_trackbar(val):
    trackbar_buf[0] = clamp_task_idx(val)

def get_total_rows():
    return len(get_row_heights(state["task_idx"]))

# ── Overlay builders (called from main loop, not callbacks) ───────────────────
def build_debug_overlay(task_idx: int):
    """Build a full-window image of the debug photo with bbox overlay."""
    task_idx = clamp_task_idx(task_idx)
    debug_path, _, crops, _, bbox_map = tasks[task_idx]
    if debug_path is None or not Path(debug_path).exists():
        return None
    img = cv2.imread(str(debug_path))
    if img is None:
        return None
    oh, ow = img.shape[:2]
    scale  = min(WIN_W / ow, WIN_H / oh, 2.0)
    shown  = cv2.resize(img, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
    ox, oy, storage_scale = read_debug_transform(debug_path)
    coord_scale = scale * storage_scale
    crops_labels = {cf: progress.get(cf) for _, cf in crops}
    draw_bbox_overlay(shown, crops, bbox_map, crops_labels,
                      state["selected_idx"], coord_scale, ox, oy,
                      num_fs=0.28, show_all_numbers=True)
    sh, sw = shown.shape[:2]
    # Pad to full window size
    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
    cy = (WIN_H - sh) // 2
    cx = (WIN_W - sw) // 2
    canvas[cy:cy+sh, cx:cx+sw] = shown
    cv2.putText(canvas, "click bbox = select  |  A/D or arrows = prev/next  |  other click/key = close",
                (WIN_W // 2 - 330, WIN_H - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
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
    PAD_HIT = 8
    best_i = None
    best_area = None
    for i, (_, crop_fn) in enumerate(crops):
        if crop_fn not in bbox_map:
            continue
        bx, by, bw, bh = bbox_map[crop_fn]
        dx = cx + int((bx - ox) * coord_scale)
        dy = cy + int((by - oy) * coord_scale)
        dw = int(bw * coord_scale)
        dh = int(bh * coord_scale)
        if (dx - PAD_HIT <= x <= dx + dw + PAD_HIT and
                dy - PAD_HIT <= y <= dy + dh + PAD_HIT):
            area = max(1, dw * dh)
            if best_area is None or area < best_area:
                best_i = i
                best_area = area
    return best_i

def build_preview_overlay(crop_path, crop_fn):
    """Build a full-window preview of a single crop."""
    img = cv2.imread(str(crop_path))
    if img is None:
        return None
    orig_h, orig_w = img.shape[:2]
    scale = min((WIN_W - 40) / orig_w, (WIN_H - 60) / orig_h, 4.0)
    img   = cv2.resize(img, (int(orig_w * scale), int(orig_h * scale)),
                       interpolation=cv2.INTER_NEAREST if scale > 1 else cv2.INTER_AREA)
    ih, iw = img.shape[:2]
    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
    cy = (WIN_H - ih) // 2
    cx = (WIN_W - iw) // 2
    canvas[cy:cy+ih, cx:cx+iw] = img
    info = f"{crop_fn}  |  {orig_w}x{orig_h}px  |  click or any key to close"
    cv2.putText(canvas, info, (10, WIN_H - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1)
    return canvas

# ── Mouse ─────────────────────────────────────────────────────────────────────
def on_mouse(event, x, y, flags, param):
    # Any click dismisses overlay
    if state["overlay"] is not None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if state["overlay_kind"] == "debug":
                hit_i = hit_debug_overlay_bbox(state["task_idx"], x, y)
                if hit_i is not None:
                    state["selected_idx"] = hit_i
                    max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
                    state["scroll_row"] = max(0, min(hit_i // CROP_COLS, max_scroll))
            state["overlay"] = None
            state["overlay_kind"] = None
        return

    _, _, crops, _, _ = tasks[state["task_idx"]]
    total_rows = get_total_rows()
    max_scroll = max(0, total_rows - ROWS_VISIBLE)

    if event == cv2.EVENT_MOUSEWHEEL:
        signed = flags if flags < 2**31 else flags - 2**32
        state["scroll_row"] = max(0, min(state["scroll_row"] + (-1 if signed > 0 else 1),
                                         max_scroll))
        return

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    # Click in the top half: debug panel — hit-test bboxes first, fall back
    # to opening the large debug overlay.
    if DEBUG_TOP <= y < DEBUG_BOTTOM:
        debug_path = tasks[state["task_idx"]][0]
        key_dp = str(debug_path) if debug_path else ""
        if key_dp in debug_cache:
            _, dbg_scale, dbg_ox, dbg_oy, dbg_draw_x = debug_cache[key_dp]
            _, _, crops, _, bbox_map = tasks[state["task_idx"]]
            PAD_HIT = 4
            local_y = y - DEBUG_TOP    # bboxes are drawn relative to canvas top
            for i, (_, crop_fn) in enumerate(crops):
                if crop_fn not in bbox_map:
                    continue
                bx, by, bw, bh = bbox_map[crop_fn]
                dx = int((bx - dbg_ox) * dbg_scale) + dbg_draw_x
                dy = int((by - dbg_oy) * dbg_scale)
                dw = int(bw * dbg_scale)
                dh = int(bh * dbg_scale)
                if (dx - PAD_HIT <= x <= dx + dw + PAD_HIT and
                        dy - PAD_HIT <= local_y <= dy + dh + PAD_HIT):
                    click_buf[0] = ("bbox", i)
                    return
        click_buf[0] = -2
        return

    # Click in the bottom strip: crop grid
    if y >= DEBUG_BOTTOM:
        for i in range(len(crops)):
            x1, y1, x2, y2 = crop_rect(i)
            if y1 < 0:    # off-screen sentinel from crop_rect
                continue
            if x1 <= x <= x2 and y1 <= y <= y2:
                click_buf[0] = -3 if state["selected_idx"] == i else i
                return
    click_buf[0] = -1

# ── Layout helper ─────────────────────────────────────────────────────────────
def crop_rect(idx: int):
    """(x1, y1, x2, y2) for a crop in the bottom strip. Returns an off-screen
    sentinel if the crop's row is not the currently visible one."""
    col        = idx % CROP_COLS
    row_of_idx = idx // CROP_COLS

    # Only the row at scroll_row is visible — anything else is off-screen.
    if row_of_idx != state["scroll_row"]:
        return 0, -9999, CROP_SIZE, -9999 + CROP_SIZE

    # Strip starts right below the debug area, ends above the footer.
    y = DEBUG_BOTTOM + PAD
    x1 = CROP_PAD_X + col * (CROP_SIZE + CROP_PAD_X)

    _, _, crops, _, _ = tasks[state["task_idx"]]
    if idx < len(crops):
        entry  = thumb_cache.get(str(crops[idx][0]))
        crop_h = entry[3] if entry else CROP_SIZE
    else:
        crop_h = CROP_SIZE

    return x1, y, x1 + CROP_SIZE, y + crop_h

# ── Label I/O ─────────────────────────────────────────────────────────────────
def apply_label(crop_fn, crop_path, label):
    if crop_fn in progress:
        old_dest = LABELED_DIR / progress[crop_fn] / crop_fn
        if old_dest.exists():
            old_dest.unlink()
    dest = LABELED_DIR / label / crop_fn
    if dest.exists():
        dest = LABELED_DIR / label / f"{state['task_idx']}_{crop_fn}"
    shutil.copy2(crop_path, dest)
    progress[crop_fn] = label
    save_progress()

def batch_label_or_undo(state, label, tasks, progress, labeled_dir,
                        save_progress, apply_label):
    """In IMAGE_NAV mode, label every unlabeled crop with `label`. If any
    crops in this image already carry `label`, clear those instead — works
    regardless of which images you switched between (no batch history)."""
    _, _, crops, _, _ = tasks[state["task_idx"]]

    matching = [crop_fn for _, crop_fn in crops
                if progress.get(crop_fn) == label]
    if matching:
        for crop_fn in matching:
            old = labeled_dir / progress[crop_fn] / crop_fn
            if old.exists():
                old.unlink()
            del progress[crop_fn]
        save_progress(force=True)
        print(f"Cleared {len(matching)} '{label}' labels in current image")
        return

    just_labeled = []
    for crop_path, crop_fn in crops:
        if crop_fn not in progress:
            apply_label(crop_fn, crop_path, label)
            just_labeled.append(crop_fn)
    if just_labeled:
        print(f"Labeled {len(just_labeled)} crops as '{label}' in current image")

# ── Render ────────────────────────────────────────────────────────────────────
def render():
    # ── Overlay mode (large debug view or crop preview) ────────────────────────
    if state["overlay"] is not None:
        return state["overlay"]

    idx   = clamp_task_idx(state["task_idx"])
    state["task_idx"] = idx
    sel   = state["selected_idx"]
    debug_path, img_name, crops, cam_name, bbox_map = tasks[idx]
    crops_labels = {cf: progress.get(cf) for _, cf in crops}
    heights      = get_row_heights(idx)
    total_rows   = len(heights)

    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)

    # ── Top: debug image + bbox overlay (full width) ───────────────────────────
    debug_panel, dbg_scale, dbg_ox, dbg_oy, dbg_draw_x = load_debug_base(debug_path)
    draw_bbox_overlay(debug_panel, crops, bbox_map, crops_labels,
                      sel, dbg_scale, dbg_ox, dbg_oy, num_fs=0.20,
                      draw_x=dbg_draw_x)
    dh, dw = debug_panel.shape[:2]
    canvas[DEBUG_TOP:DEBUG_TOP + dh, :dw] = debug_panel

    # ── Header ─────────────────────────────────────────────────────────────────
    cv2.rectangle(canvas, (0, 0), (WIN_W, HEADER_H - 2), (25, 25, 25), -1)
    done_this = sum(1 for _, cf in crops if cf in progress)
    g_done    = sum(1 for fn in progress if fn in all_crop_fns)
    more_txt  = "  [MORE CROPS BELOW]" if total_rows > state["scroll_row"] + ROWS_VISIBLE else ""
    title = (f"[{idx+1}/{total_images}]  {cam_name} / {Path(img_name).name}"
             f"  ({done_this}/{len(crops)} labeled){more_txt}")
    cv2.putText(canvas, title, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    nav = state.get("nav_mode", "image")
    badge = "CROP NAV" if nav == "crop" else None
    if badge:
        (tw_b, th_b), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        bx1 = WIN_W - tw_b - 24
        bx2 = WIN_W - 8
        by1 = 4
        by2 = by1 + th_b + 10
        cv2.rectangle(canvas, (bx1, by1), (bx2, by2), (40, 200, 255), -1)
        cv2.putText(canvas, badge, (bx1 + 8, by2 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    bg_k  = _key_label('label_background')
    bb_k  = _key_label('label_bumblebee')
    fly_k = _key_label('label_fly')
    but_k = _key_label('label_butterfly')
    oth_k = _key_label('label_other')
    un_k  = _key_label('label_unsure')
    if nav == "crop":
        arrows_help = "<-/-> = prev/next crop | up/down = up/down row"
        label_help  = "label = label selected crop"
    else:
        arrows_help = "<-/-> = prev/next image | up/down = scroll grid"
        label_help  = "label = batch all unlabeled (twice = undo)"
    instruction = (
        f"{bg_k}=bg {bb_k}=BB {fly_k}=fly {but_k}=but {oth_k}=other {un_k}=unsure"
        f" | R = toggle CROP NAV"
        f" | {arrows_help}"
        f" | {label_help}"
        f" | {_key_label('clear_image')}=clear {_key_label('preview')}=preview {_key_label('quit')}=quit"
    )
    instr_fs = 0.44
    while cv2.getTextSize(instruction, cv2.FONT_HERSHEY_SIMPLEX, instr_fs, 1)[0][0] > WIN_W - 20:
        instr_fs -= 0.02
        if instr_fs <= 0.36:
            break
    cv2.putText(canvas, instruction, (10, 62),
                cv2.FONT_HERSHEY_SIMPLEX, instr_fs, (180, 180, 180), 1)

    # ── Footer ─────────────────────────────────────────────────────────────────
    cv2.rectangle(canvas, (0, WIN_H - FOOTER_H), (WIN_W, WIN_H), (20, 20, 20), -1)
    # Page indicator bar — bright segment shows current page position; spans
    # the full width so a glance tells you whether there are pages left.
    if total_rows > 0:
        bar_y1 = WIN_H - FOOTER_H + 4
        bar_y2 = bar_y1 + 10
        bar_x1 = 8
        bar_x2 = WIN_W - 8
        cv2.rectangle(canvas, (bar_x1, bar_y1), (bar_x2, bar_y2), (45, 45, 55), -1)
        seg_w  = max(8, (bar_x2 - bar_x1) // max(1, total_rows))
        seg_x1 = bar_x1 + state["scroll_row"] * seg_w
        seg_x2 = min(seg_x1 + seg_w, bar_x2)
        # Yellow when there's still more after the current page; cyan once
        # you're on the last page (signals "you've seen everything").
        on_last = state["scroll_row"] >= total_rows - 1
        seg_color = (0, 215, 255) if not on_last else (180, 220, 90)
        cv2.rectangle(canvas, (seg_x1, bar_y1), (seg_x2, bar_y2), seg_color, -1)
        cv2.rectangle(canvas, (bar_x1, bar_y1), (bar_x2, bar_y2), (0, 0, 0), 1)
    page_txt = (f"Page {state['scroll_row']+1}/{max(1, total_rows)}"
                if total_rows else "Page 0/0")
    cv2.putText(canvas,
                f"Total: {g_done}/{total_crops}  |  {page_txt}"
                "  |  up/down = scroll page  |  double-click crop = large preview",
                (10, WIN_H - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (130, 130, 130), 1)

    # ── Bottom strip: crop thumbnails (one row) ───────────────────────────────
    grid_bottom = WIN_H - FOOTER_H
    for i, (crop_path, crop_fn) in enumerate(crops):
        x1, y1, x2, y2 = crop_rect(i)
        if y1 < 0:    # off-screen sentinel
            continue
        if x2 > WIN_W:
            continue

        entry = thumb_cache.get(str(crop_path))
        if entry is None:
            raw = cv2.imread(str(crop_path))
            if raw is None:
                entry = (np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8), 0, 0, CROP_SIZE)
            else:
                oh, ow = raw.shape[:2]
                sc = CROP_SIZE / max(ow, oh)
                t  = cv2.resize(raw, (max(1, int(ow * sc)), max(1, int(oh * sc))),
                                interpolation=cv2.INTER_AREA)
                entry = (t, ow, oh, t.shape[0])
            thumb_cache[str(crop_path)] = entry

        thumb, orig_w, orig_h, _ = entry
        th_h, th_w = thumb.shape[:2]
        tx, ty     = x1, y1
        if ty < DEBUG_BOTTOM or ty + th_h + CROP_META_H > grid_bottom:
            continue

        clip = min(th_h, grid_bottom - CROP_META_H - ty)
        if ty >= 0 and clip > 0 and tx + th_w <= WIN_W:
            canvas[ty : ty + clip, tx : tx + th_w] = thumb[:clip]

        label  = crops_labels.get(crop_fn)
        color  = get_color(label)
        border = 6 if i == sel else 2
        border_color = (180, 0, 255) if i == sel else color
        cv2.rectangle(canvas, (tx - 2, ty - 2), (tx + th_w + 2, ty + th_h + 2), border_color, border)

        # Bold label text near the top of the crop when labelled. The
        # coloured border (drawn just above) is the main visual signal;
        # we keep the image itself fully visible.
        if label is not None and clip > 0:
            ovr_text = get_badge(label)
            if ovr_text:
                ovr_fs = 0.75
                (otw, oth), _ = cv2.getTextSize(ovr_text, cv2.FONT_HERSHEY_SIMPLEX, ovr_fs, 2)
                ox = tx + (th_w - otw) // 2
                oy = ty + oth + 8
                cv2.putText(canvas, ovr_text, (ox, oy),  # black outline
                            cv2.FONT_HERSHEY_SIMPLEX, ovr_fs, (0, 0, 0), 5)
                cv2.putText(canvas, ovr_text, (ox, oy),  # label colour on top
                            cv2.FONT_HERSHEY_SIMPLEX, ovr_fs, color, 2)

        # Label badge
        badge = get_badge(label)
        badge_fs = 0.48
        (bw_t, bh_t), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, badge_fs, 1)
        badge_h = bh_t + 8
        bw_px = max(28, bw_t + 10)
        cv2.rectangle(canvas, (tx, ty + th_h), (tx + bw_px, ty + th_h + badge_h), color, -1)
        cv2.putText(canvas, badge, (tx + 5, ty + th_h + bh_t + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, badge_fs, (0, 0, 0), 1)

        # Index number badge (top-left)
        num_txt = str(i)
        fs_n    = 0.50
        (nw_t, nh_t), _ = cv2.getTextSize(num_txt, cv2.FONT_HERSHEY_SIMPLEX, fs_n, 1)
        nbg = (255, 255, 255) if i == sel else (20, 20, 20)
        nfg = (0, 0, 0)       if i == sel else (210, 210, 210)
        cv2.rectangle(canvas, (tx, ty), (tx + nw_t + 6, ty + nh_t + 6), nbg, -1)
        cv2.putText(canvas, num_txt, (tx + 3, ty + nh_t + 3),
                    cv2.FONT_HERSHEY_SIMPLEX, fs_n, nfg, 1)

        # Size text
        meta_y = ty + th_h + badge_h
        if orig_w > 0:
            size_text = f"{orig_w}x{orig_h}"
            size_fs = 0.30
            (_, size_h), _ = cv2.getTextSize(size_text, cv2.FONT_HERSHEY_SIMPLEX, size_fs, 1)
            size_y = meta_y + size_h + 7
            cv2.putText(canvas, size_text, (tx, size_y),
                        cv2.FONT_HERSHEY_SIMPLEX, size_fs, (140, 180, 140), 1)
        else:
            size_y = meta_y + 18

        # Filename
        m      = _re.search(r"_crop_(\d+)", crop_fn)
        prefix = f"#{m.group(1)} " if m else ""
        short  = (".." + crop_fn[-12:]) if len(crop_fn) > 14 else crop_fn
        file_fs = 0.28
        (_, file_h), _ = cv2.getTextSize(prefix + short, cv2.FONT_HERSHEY_SIMPLEX, file_fs, 1)
        cv2.putText(canvas, prefix + short, (tx, size_y + file_h + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, file_fs, (110, 110, 110), 1)

        # Selection glow
        if i == sel:
            ry1 = max(0, ty - 2)
            ry2 = min(canvas.shape[0], ty + th_h + 3)
            rx1 = max(0, tx - 2)
            rx2 = min(canvas.shape[1], tx + th_w + 3)
            roi   = canvas[ry1:ry2, rx1:rx2]
            white = np.full_like(roi, 255)
            cv2.addWeighted(white, 0.15, roi, 0.85, 0, roi)
            canvas[ry1:ry2, rx1:rx2] = roi

    return canvas

# ── Window & main loop ────────────────────────────────────────────────────────
WINDOW = "Pollinator Annotator"
cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW, WIN_W, WIN_H)
cv2.moveWindow(WINDOW, 0, 0)
cv2.createTrackbar("Image", WINDOW, 0, max(1, total_images - 1), on_trackbar)
if initial_task_idx > 0:
    cv2.setTrackbarPos("Image", WINDOW, initial_task_idx)

cv2.setMouseCallback(WINDOW, on_mouse)

while True:
    tb_val = cv2.getTrackbarPos("Image", WINDOW)
    tb_val = clamp_task_idx(tb_val)
    if trackbar_buf[0] is not None:
        tb_val = clamp_task_idx(trackbar_buf[0])
        trackbar_buf[0] = None
    if tb_val != state["task_idx"] and click_buf[0] is None:
        load_progress_for_task(tb_val); save_session(tb_val)
        state.update({"task_idx": tb_val, "selected_idx": None, "scroll_row": 0,
                      "overlay": None, "overlay_kind": None})

    if click_buf[0] is not None:
        val        = click_buf[0]
        click_buf[0] = None
        if isinstance(val, tuple) and val[0] == "bbox":
            i = val[1]
            state["selected_idx"] = i
            _, _, crops, _, _ = tasks[state["task_idx"]]
            if i < len(crops):
                state["overlay"] = build_preview_overlay(*crops[i])
                state["overlay_kind"] = "preview"
        elif val == -2:
            state["overlay"] = build_debug_overlay(state["task_idx"])
            state["overlay_kind"] = "debug"
        elif val == -3:
            sel = state["selected_idx"]
            if sel is not None:
                _, _, crops, _, _ = tasks[state["task_idx"]]
                if sel < len(crops):
                    state["overlay"] = build_preview_overlay(*crops[sel])
                    state["overlay_kind"] = "preview"
        elif val == -1:
            state["selected_idx"] = None
        else:
            state["selected_idx"] = val

    cv2.imshow(WINDOW, render())
    key_raw = cv2.waitKeyEx(30)

    prev_keys = (65361, 2424832, 63234)
    next_keys = (65363, 2555904, 63235)
    up_keys   = (65362, 2490368, 63232)
    down_keys = (65364, 2621440, 63233)
    _arrow_codes = set(prev_keys + next_keys + up_keys + down_keys)

    # Extract a printable ASCII char from key_raw, tolerating Shift/Alt/Ctrl
    # high-bit masks that some OpenCV builds put on top of the base char.
    # Skip arrow-key keysyms: their low bytes (Q/R/S/T) collide with letters.
    if key_raw == -1:
        ascii_key = None
    elif 0 <= key_raw <= 255:
        ascii_key = key_raw
    elif key_raw not in _arrow_codes and 32 <= (key_raw & 0xFF) <= 126:
        ascii_key = key_raw & 0xFF
    else:
        ascii_key = None

    if os.environ.get("DEBUG_KEYS") and key_raw != -1:
        print(f"[DEBUG_KEYS] key_raw={key_raw} ascii_key={ascii_key}")

    # Helper: switch image, reset per-image state. Used in both nav mode
    # arrow handlers and the debug-overlay navigation.
    def go_to_image(new_idx, overlay=None, overlay_kind=None):
        load_progress_for_task(new_idx); save_session(new_idx)
        state.update({
            "task_idx":     new_idx,
            "selected_idx": None,
            "scroll_row":   0,
            
            "overlay":      overlay,
            "overlay_kind": overlay_kind,
        })
        cv2.setTrackbarPos("Image", WINDOW, new_idx)

    # Any key press dismisses overlay, except debug overlay navigation
    if state["overlay"] is not None:
        if key_raw != -1:
            if state["overlay_kind"] == "debug" and key_raw in next_keys:
                new = min(state["task_idx"] + 1, total_images - 1)
                go_to_image(new, build_debug_overlay(new), "debug")
            elif state["overlay_kind"] == "debug" and key_raw in prev_keys:
                new = max(state["task_idx"] - 1, 0)
                go_to_image(new, build_debug_overlay(new), "debug")
            else:
                state["overlay"] = None
                state["overlay_kind"] = None
        continue

    _, _, crops, _, _ = tasks[state["task_idx"]]

    if ascii_key in KEY_ORDS["preview"]:
        sel = state["selected_idx"]
        if sel is not None and sel < len(crops):
            state["overlay"] = build_preview_overlay(*crops[sel])
            state["overlay_kind"] = "preview"

    elif ascii_key in KEY_ORDS["clear_image"]:
        removed = 0
        for _, crop_fn in crops:
            if crop_fn in progress:
                old = LABELED_DIR / progress[crop_fn] / crop_fn
                if old.exists():
                    old.unlink()
                del progress[crop_fn]
                removed += 1
        if removed:
            save_progress(force=True)
            print(f"Cleared {removed} crops in current image")
        state["selected_idx"] = None

    elif ascii_key in KEY_ORDS["quit"]:
        save_progress(force=True)
        save_session(state["task_idx"])
        break

    elif ascii_key in KEY_ORDS["nav_mode_toggle"]:
        if state["nav_mode"] == "image":
            state["nav_mode"] = "crop"
            # Initialize selection so arrow keys have somewhere to start.
            if state["selected_idx"] is None and crops:
                state["selected_idx"] = state["scroll_row"] * CROP_COLS
        else:
            state["nav_mode"] = "image"
            state["selected_idx"] = None

    elif ascii_key in LABEL_KEY_ORDS:
        label = LABEL_KEY_ORDS[ascii_key]
        if state["nav_mode"] == "crop":
            sel = state["selected_idx"]
            if sel is not None and sel < len(crops):
                crop_path, crop_fn = crops[sel]
                if progress.get(crop_fn) == label:
                    # Same label pressed twice on this crop → toggle off,
                    # stay on it so the user can apply a different label.
                    old = LABELED_DIR / progress[crop_fn] / crop_fn
                    if old.exists():
                        old.unlink()
                    del progress[crop_fn]
                    save_progress()
                    print(f"Unlabeled {crop_fn}")
                else:
                    apply_label(crop_fn, crop_path, label)
                    # Advance selection to the next crop.
                    new_sel = min(sel + 1, len(crops) - 1)
                    state["selected_idx"] = new_sel
                    sel_row = new_sel // CROP_COLS
                    max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
                    if sel_row >= state["scroll_row"] + ROWS_VISIBLE:
                        state["scroll_row"] = min(sel_row - ROWS_VISIBLE + 1, max_scroll)
                    elif sel_row < state["scroll_row"]:
                        state["scroll_row"] = sel_row
        else:
            # IMAGE_NAV: label every unlabeled crop, or clear all crops
            # already carrying this label.
            batch_label_or_undo(state, label, tasks, progress, LABELED_DIR, save_progress, apply_label)

    elif key_raw in next_keys:
        if state["nav_mode"] == "crop":
            if crops:
                sel = state["selected_idx"]
                new_sel = 0 if sel is None else min(sel + 1, len(crops) - 1)
                state["selected_idx"] = new_sel
                sel_row = new_sel // CROP_COLS
                max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
                if sel_row >= state["scroll_row"] + ROWS_VISIBLE:
                    state["scroll_row"] = min(sel_row - ROWS_VISIBLE + 1, max_scroll)
                elif sel_row < state["scroll_row"]:
                    state["scroll_row"] = sel_row
        else:
            go_to_image(min(state["task_idx"] + 1, total_images - 1))

    elif key_raw in prev_keys:
        if state["nav_mode"] == "crop":
            if crops:
                sel = state["selected_idx"]
                new_sel = len(crops) - 1 if sel is None else max(sel - 1, 0)
                state["selected_idx"] = new_sel
                sel_row = new_sel // CROP_COLS
                if sel_row < state["scroll_row"]:
                    state["scroll_row"] = sel_row
                elif sel_row >= state["scroll_row"] + ROWS_VISIBLE:
                    state["scroll_row"] = sel_row
        else:
            go_to_image(max(state["task_idx"] - 1, 0))

    elif key_raw in down_keys:
        if state["nav_mode"] == "crop":
            if crops:
                sel = state["selected_idx"]
                new_sel = (state["scroll_row"] * CROP_COLS) if sel is None \
                          else min(sel + CROP_COLS, len(crops) - 1)
                state["selected_idx"] = new_sel
                sel_row = new_sel // CROP_COLS
                max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
                if sel_row >= state["scroll_row"] + ROWS_VISIBLE:
                    state["scroll_row"] = min(sel_row - ROWS_VISIBLE + 1, max_scroll)
        else:
            max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
            state["scroll_row"] = min(state["scroll_row"] + 1, max_scroll)

    elif key_raw in up_keys:
        if state["nav_mode"] == "crop":
            if crops:
                sel = state["selected_idx"]
                new_sel = 0 if sel is None else max(sel - CROP_COLS, 0)
                state["selected_idx"] = new_sel
                sel_row = new_sel // CROP_COLS
                if sel_row < state["scroll_row"]:
                    state["scroll_row"] = sel_row
        else:
            state["scroll_row"] = max(0, state["scroll_row"] - 1)

cv2.destroyAllWindows()
save_progress()
save_session(state["task_idx"])

bb_n  = len(list((LABELED_DIR / "bumblebee").glob("*.jpg")))
fly_n = len(list((LABELED_DIR / "fly").glob("*.jpg")))
but_n = len(list((LABELED_DIR / "butterfly").glob("*.jpg")))
oth_n = len(list((LABELED_DIR / "other").glob("*.jpg")))
bg_n  = len(list((LABELED_DIR / "background").glob("*.jpg")))
un_n  = len(list((LABELED_DIR / "unsure").glob("*.jpg")))
total_insect = bb_n + fly_n + but_n + oth_n
print(f"\nDone!")
print(f"  insects: {total_insect}  (BB={bb_n}  fly={fly_n}  but={but_n}  other={oth_n})")
print(f"  background: {bg_n}   unsure: {un_n}")
print(f"Saved to: {OUTPUT_DIR}")

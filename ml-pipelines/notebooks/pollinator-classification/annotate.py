"""
Pollinator Crop Annotation Tool
=====================================
Left: debug image with numbered bounding boxes  |  Right: crops with index badges

Controls:
  Click a crop (right)   -> select it; its bbox on the left is highlighted
  B / 1 / 2 / 3 / 4 / U -> label selected crop (or ALL unlabeled if none selected)
  B=background  1=bumblebee  2=fly  3=butterfly  4=other  U=unsure
  C       -> clear all annotations in current image
  P       -> preview selected crop (large popup)
  A / D   -> previous / next image
  W / X   -> scroll crops up / down  (mouse wheel also works)
  Q       -> quit and save

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

    for img_name, crops in sorted(image_crops.items()):
        img_stem   = Path(img_name).stem
        cam_prefix = cam_dir.name
        stem       = f"{cam_prefix}__{img_stem}"
        debug_img = (
            next(debug_dir.glob(f"{stem}*_4_final_saved_crops*"), None)
            or next(debug_dir.glob(f"{stem}*_3_contours*"), None)
            or next(debug_dir.glob(f"{stem}*_1_original*"), None)
            or next(
                (p for p in sorted(debug_dir.glob(f"{stem}*")) if "_2_diff" not in p.name),
                None,
            )
            or next(debug_dir.glob(f"{stem}*"), None)
        )
        if crops:
            tasks.append((debug_img, img_name, crops, cam_dir.name, bbox_map))

total_images = len(tasks)
total_crops  = sum(len(c) for _, _, c, _, _ in tasks)
all_crop_fns = {cf for _, _, crops, _, _ in tasks for _, cf in crops}

def clamp_task_idx(idx):
    return max(0, min(int(idx), total_images - 1))

if tasks:
    load_progress_for_task(0)
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
WIN_W, WIN_H = 1800, 1100
DEBUG_W      = 920
PANEL_W      = WIN_W - DEBUG_W
PAD          = 8
CROP_COLS    = 3
CROP_SIZE    = max(1, (PANEL_W - PAD * CROP_COLS - 15) // CROP_COLS)
CROP_META_H  = 66
HEADER_H     = 86
FOOTER_H     = 58
ROWS_VISIBLE = max(1, (WIN_H - HEADER_H - FOOTER_H - PAD) // (CROP_SIZE + PAD + CROP_META_H))

# ── Colours & badges ──────────────────────────────────────────────────────────
COLORS = {
    "bumblebee":  (0,   200, 255),
    "fly":        (0,   255,   0),
    "butterfly":  (255,   0, 200),
    "other":      (200, 200,   0),
    "insect":     (0,   200, 150),   # legacy
    "background": (50,   50, 210),
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
    """Return (canvas_copy, coord_scale, ox, oy)."""
    tw, th = DEBUG_W, WIN_H
    if path is None or not Path(path).exists():
        blank = np.zeros((th, tw, 3), dtype=np.uint8)
        cv2.putText(blank, "No debug image", (20, th // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (160, 160, 160), 2)
        return blank, 1.0, 0, 0
    key = str(path)
    if key not in debug_cache:
        img = cv2.imread(key)
        if img is None:
            debug_cache[key] = (np.zeros((th, tw, 3), dtype=np.uint8), 1.0, 0, 0)
        else:
            h, w   = img.shape[:2]
            view_scale = min(tw / w, th / h)
            nw, nh = int(w * view_scale), int(h * view_scale)
            scaled = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            canvas = np.zeros((th, tw, 3), dtype=np.uint8)
            canvas[:nh, :nw] = scaled
            ox, oy, storage_scale = read_debug_transform(path)
            coord_scale = view_scale * storage_scale
            debug_cache[key] = (canvas, coord_scale, ox, oy)
    base, coord_scale, ox, oy = debug_cache[key]
    return base.copy(), coord_scale, ox, oy

# ── Bbox overlay helper ───────────────────────────────────────────────────────
def draw_bbox_overlay(img, crops, bbox_map, crops_labels, sel, scale, ox, oy,
                      num_fs=0.22, show_all_numbers=False):
    """Draw selected bbox plus labels already assigned."""
    SEL_COLOR = (180, 0, 255)   # bright magenta

    for i, (_, crop_fn) in enumerate(crops):
        label = crops_labels.get(crop_fn)
        if label is None or crop_fn not in bbox_map:
            continue
        bx, by, bw, bh = bbox_map[crop_fn]
        dx = int((bx - ox) * scale)
        dy = int((by - oy) * scale)
        dw = int(bw * scale)
        dh = int(bh * scale)
        color = get_color(label)
        if label != "background":
            cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), color, 2)

        badge = get_badge(label)
        fs = max(0.18, num_fs - 0.02) if label == "background" else max(0.24, num_fs + 0.05)
        (tw_b, th_b), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        tx = max(1, dx)
        ty = max(th_b + 4, dy - 4 if label != "background" else dy + th_b + 3)
        cv2.rectangle(img, (tx - 2, ty - th_b - 3), (tx + tw_b + 4, ty + 3), color, -1)
        cv2.putText(img, badge, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 1)

    if show_all_numbers:
        for i, (_, crop_fn) in enumerate(crops):
            if crop_fn not in bbox_map:
                continue
            bx, by, bw, bh = bbox_map[crop_fn]
            dx = int((bx - ox) * scale)
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
    dx = int((bx - ox) * scale)
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
    "task_idx":    0,
    "selected_idx": None,
    "scroll_row":  0,
    "overlay":     None,   # None  or  numpy array to draw fullscreen over canvas
    "overlay_kind": None,
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

    # Scrollbar
    if x >= WIN_W - 14 and total_rows > ROWS_VISIBLE:
        ratio = (y - HEADER_H) / max(1, WIN_H - FOOTER_H - HEADER_H)
        state["scroll_row"] = max(0, min(int(ratio * total_rows), max_scroll))
        return

    # Debug panel — hit-test bboxes first, fall back to large view
    if x < DEBUG_W:
        debug_path = tasks[state["task_idx"]][0]
        key_dp = str(debug_path) if debug_path else ""
        if key_dp in debug_cache:
            _, dbg_scale, dbg_ox, dbg_oy = debug_cache[key_dp]
            _, _, crops, _, bbox_map = tasks[state["task_idx"]]
            PAD_HIT = 4   # extra px tolerance around each bbox
            for i, (_, crop_fn) in enumerate(crops):
                if crop_fn not in bbox_map:
                    continue
                bx, by, bw, bh = bbox_map[crop_fn]
                dx = int((bx - dbg_ox) * dbg_scale)
                dy = int((by - dbg_oy) * dbg_scale)
                dw = int(bw * dbg_scale)
                dh = int(bh * dbg_scale)
                if (dx - PAD_HIT <= x <= dx + dw + PAD_HIT and
                        dy - PAD_HIT <= y <= dy + dh + PAD_HIT):
                    click_buf[0] = ("bbox", i)
                    return
        click_buf[0] = -2
        return

    # Crop grid
    for i in range(len(crops)):
        x1, y1, x2, y2 = crop_rect(i)
        if y1 < HEADER_H or y2 + CROP_META_H > WIN_H - FOOTER_H - PAD:
            continue
        if x1 <= x <= x2 and y1 <= y <= y2:
            click_buf[0] = -3 if state["selected_idx"] == i else i
            return
    click_buf[0] = -1

# ── Layout helper ─────────────────────────────────────────────────────────────
def crop_rect(idx: int):
    """(x1, y1, x2, y2). Returns off-screen sentinel if crop is above scroll."""
    col        = idx % CROP_COLS
    row_of_idx = idx // CROP_COLS
    heights    = get_row_heights(state["task_idx"])

    # Crop is scrolled above visible area — return sentinel so it's ignored
    if row_of_idx < state["scroll_row"]:
        return 0, -9999, CROP_SIZE, -9999 + CROP_SIZE

    y = HEADER_H + PAD
    for r in range(row_of_idx - state["scroll_row"]):
        actual_r = r + state["scroll_row"]
        if actual_r < len(heights):
            y += heights[actual_r] + PAD + CROP_META_H

    x1 = DEBUG_W + PAD + col * (CROP_SIZE + PAD)

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

    # ── Left panel: debug image + bbox overlay ─────────────────────────────────
    debug_panel, dbg_scale, dbg_ox, dbg_oy = load_debug_base(debug_path)
    draw_bbox_overlay(debug_panel, crops, bbox_map, crops_labels,
                      sel, dbg_scale, dbg_ox, dbg_oy, num_fs=0.20)
    canvas[:, :DEBUG_W] = debug_panel

    # ── Header ─────────────────────────────────────────────────────────────────
    cv2.rectangle(canvas, (0, 0), (WIN_W, HEADER_H - 2), (25, 25, 25), -1)
    done_this = sum(1 for _, cf in crops if cf in progress)
    g_done    = sum(1 for fn in progress if fn in all_crop_fns)
    more_txt  = "  [MORE CROPS BELOW]" if total_rows > state["scroll_row"] + ROWS_VISIBLE else ""
    cv2.putText(canvas,
                f"[{idx+1}/{total_images}]  {cam_name} / {Path(img_name).name}"
                f"  ({done_this}/{len(crops)} labeled){more_txt}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)
    instruction = (
        "B=background | 1=bumblebee | 2=fly | 3=butterfly | 4=other | U=unsure | "
        "C=clear | P=preview | A/D=previous/next | W/X or mouse wheel=scroll crops | Q=quit"
    )
    instr_fs = 0.44
    while cv2.getTextSize(instruction, cv2.FONT_HERSHEY_SIMPLEX, instr_fs, 1)[0][0] > WIN_W - 20:
        instr_fs -= 0.02
        if instr_fs <= 0.36:
            break
    cv2.putText(canvas, instruction, (10, 62),
                cv2.FONT_HERSHEY_SIMPLEX, instr_fs, (180, 180, 180), 1)

    # ── Footer ─────────────────────────────────────────────────────────────────
    cv2.rectangle(canvas, (DEBUG_W, WIN_H - FOOTER_H), (WIN_W, WIN_H), (20, 20, 20), -1)
    cv2.putText(canvas,
                f"Total: {g_done}/{total_crops}"
                f"  |  Rows {state['scroll_row']+1}-"
                f"{min(state['scroll_row']+ROWS_VISIBLE, total_rows)}/{total_rows}"
                "  |  double-click crop = large preview",
                (DEBUG_W + 10, WIN_H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (130, 130, 130), 1)
    if total_rows > state["scroll_row"] + ROWS_VISIBLE:
        msg = "v v v   MORE CROPS BELOW   v v v"
        fs = 0.75
        (tw_m, th_m), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, fs, 2)
        mx1 = DEBUG_W + 12
        mx2 = WIN_W - 24
        my1 = WIN_H - FOOTER_H + 4
        my2 = WIN_H - 4
        cv2.rectangle(canvas, (mx1, my1), (mx2, my2), (0, 180, 255), -1)
        cv2.rectangle(canvas, (mx1, my1), (mx2, my2), (0, 0, 0), 2)
        tx = mx1 + max(10, (mx2 - mx1 - tw_m) // 2)
        cv2.putText(canvas, msg, (tx, my1 + th_m + 7),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 2)

    # ── Scrollbar ──────────────────────────────────────────────────────────────
    if total_rows > ROWS_VISIBLE:
        sb_x         = WIN_W - 12
        sb_y1, sb_y2 = HEADER_H, WIN_H - FOOTER_H
        sb_h         = sb_y2 - sb_y1
        cv2.rectangle(canvas, (sb_x, sb_y1), (sb_x + 10, sb_y2), (40, 40, 40), -1)
        thumb_h   = max(20, int(sb_h * ROWS_VISIBLE / total_rows))
        thumb_top = sb_y1 + int(
            (sb_h - thumb_h) * state["scroll_row"] / max(1, total_rows - ROWS_VISIBLE)
        )
        cv2.rectangle(canvas, (sb_x, thumb_top), (sb_x + 10, thumb_top + thumb_h),
                      (140, 140, 180), -1)
        cv2.putText(canvas, "^", (sb_x + 1, sb_y1 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
        cv2.putText(canvas, "v", (sb_x + 1, sb_y2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    # ── Right panel: crop thumbnails ──────────────────────────────────────────
    grid_bottom = WIN_H - FOOTER_H - PAD
    for i, (crop_path, crop_fn) in enumerate(crops):
        x1, y1, x2, y2 = crop_rect(i)
        if y2 < HEADER_H or y1 >= grid_bottom:
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
        if ty < HEADER_H or ty + th_h + CROP_META_H > grid_bottom:
            continue

        clip = min(th_h, grid_bottom - CROP_META_H - ty)
        if ty >= 0 and clip > 0 and tx + th_w <= WIN_W - 15:
            canvas[ty : ty + clip, tx : tx + th_w] = thumb[:clip]

        label  = crops_labels.get(crop_fn)
        color  = get_color(label)
        border = 6 if i == sel else 2
        border_color = (180, 0, 255) if i == sel else color
        cv2.rectangle(canvas, (tx - 2, ty - 2), (tx + th_w + 2, ty + th_h + 2), border_color, border)

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
cv2.setMouseCallback(WINDOW, on_mouse)

while True:
    tb_val = cv2.getTrackbarPos("Image", WINDOW)
    tb_val = clamp_task_idx(tb_val)
    if trackbar_buf[0] is not None:
        tb_val = clamp_task_idx(trackbar_buf[0])
        trackbar_buf[0] = None
    if tb_val != state["task_idx"] and click_buf[0] is None:
        load_progress_for_task(tb_val)
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
    ascii_key = key_raw if 0 <= key_raw <= 255 else None

    prev_keys = (65361, 2424832, 63234)
    next_keys = (65363, 2555904, 63235)
    up_keys   = (65362, 2490368, 63232)
    down_keys = (65364, 2621440, 63233)

    # Any key press dismisses overlay, except debug overlay navigation
    if state["overlay"] is not None:
        if key_raw != -1:
            if state["overlay_kind"] == "debug" and (
                ascii_key in (ord("d"), ord("D")) or key_raw in next_keys
            ):
                new = min(state["task_idx"] + 1, total_images - 1)
                load_progress_for_task(new)
                state.update({"task_idx": new, "selected_idx": None, "scroll_row": 0,
                              "overlay": build_debug_overlay(new), "overlay_kind": "debug"})
                cv2.setTrackbarPos("Image", WINDOW, new)
            elif state["overlay_kind"] == "debug" and (
                ascii_key in (ord("a"), ord("A")) or key_raw in prev_keys
            ):
                new = max(state["task_idx"] - 1, 0)
                load_progress_for_task(new)
                state.update({"task_idx": new, "selected_idx": None, "scroll_row": 0,
                              "overlay": build_debug_overlay(new), "overlay_kind": "debug"})
                cv2.setTrackbarPos("Image", WINDOW, new)
            else:
                state["overlay"] = None
                state["overlay_kind"] = None
        continue

    if ascii_key in (ord("p"), ord("P")):
        sel = state["selected_idx"]
        if sel is not None:
            _, _, crops, _, _ = tasks[state["task_idx"]]
            if sel < len(crops):
                state["overlay"] = build_preview_overlay(*crops[sel])
                state["overlay_kind"] = "preview"

    elif ascii_key in (ord("c"), ord("C")):
        _, _, crops, _, _ = tasks[state["task_idx"]]
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

    elif ascii_key in (ord("q"), ord("Q")):
        save_progress(force=True)
        break

    elif ascii_key in (
        ord("b"), ord("B"),
        ord("1"), ord("2"), ord("3"), ord("4"),
        ord("u"), ord("U"),
    ):
        label = {
            ord("b"): "background", ord("B"): "background",
            ord("1"): "bumblebee",
            ord("2"): "fly",
            ord("3"): "butterfly",
            ord("4"): "other",
            ord("u"): "unsure",    ord("U"): "unsure",
        }[ascii_key]
        _, _, crops, _, _ = tasks[state["task_idx"]]
        sel = state["selected_idx"]
        if sel is not None and sel < len(crops):
            apply_label(crops[sel][1], crops[sel][0], label)
            state["selected_idx"] = None
        else:
            for crop_path, crop_fn in crops:
                if crop_fn not in progress:
                    apply_label(crop_fn, crop_path, label)

    elif ascii_key in (ord("d"), ord("D")) or key_raw in next_keys:
        new = min(state["task_idx"] + 1, total_images - 1)
        load_progress_for_task(new)
        state.update({"task_idx": new, "selected_idx": None, "scroll_row": 0})
        cv2.setTrackbarPos("Image", WINDOW, new)

    elif ascii_key in (ord("a"), ord("A")) or key_raw in prev_keys:
        new = max(state["task_idx"] - 1, 0)
        load_progress_for_task(new)
        state.update({"task_idx": new, "selected_idx": None, "scroll_row": 0})
        cv2.setTrackbarPos("Image", WINDOW, new)

    elif ascii_key in (ord("w"), ord("W")) or key_raw in up_keys:
        state["scroll_row"] = max(0, state["scroll_row"] - 1)

    elif ascii_key in (ord("x"), ord("X")) or key_raw in down_keys:
        max_scroll = max(0, get_total_rows() - ROWS_VISIBLE)
        state["scroll_row"] = min(state["scroll_row"] + 1, max_scroll)

cv2.destroyAllWindows()
save_progress()

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

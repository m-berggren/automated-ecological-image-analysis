"""
Pollinator Crop Annotation Tool v2
=====================================
Left: debug image with detection boxes  |  Right: all crops from that image

Controls:
  Click a crop to select it, then press I / B / S to label it
  I / B / S without selection  ->  label ALL unlabeled crops in this image
  A / D            -> previous / next image
  W / X            -> scroll crops up / down
  Q                -> quit and save

Usage:
  python3 annotate.py --results path/to/results --output path/to/labeled
"""

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import sys
import cv2
import numpy as np

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

parser = argparse.ArgumentParser()
parser.add_argument("--results", type=Path, default=Path("results"))
parser.add_argument("--output",  type=Path, default=Path("labeled"))
args = parser.parse_args()

RESULTS_DIR   = args.results
OUTPUT_DIR    = args.output
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

(OUTPUT_DIR / "insect").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "background").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "skip").mkdir(parents=True, exist_ok=True)

progress: dict = {}
if PROGRESS_FILE.exists():
    progress = json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    print(f"Resuming -- {len(progress)} crops already labeled")

_save_counter = 0
def save_progress(force=False):
    global _save_counter
    _save_counter += 1
    if force or _save_counter >= 5:
        PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding='utf-8')
        _save_counter = 0

# ── Collect tasks ─────────────────────────────────────────────────────────────
tasks = []
for cam_dir in sorted(RESULTS_DIR.iterdir()):
    if not cam_dir.is_dir(): continue
    debug_dir = cam_dir / "debug"
    crop_dir  = cam_dir / "crops"
    csv_path  = cam_dir / "results.csv"
    if not (debug_dir.exists() and crop_dir.exists() and csv_path.exists()): continue

    image_crops = defaultdict(list)
    with open(csv_path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            img_name = row.get("image_name", "")
            crop_fn  = row.get("crop_filename", "")
            if crop_fn and (crop_dir / crop_fn).exists():
                image_crops[img_name].append((crop_dir / crop_fn, crop_fn))

    for img_name, crops in sorted(image_crops.items()):
        # Debug images named: {cam_dir.name}__{img_stem}_N_type.jpg
        # cam_dir.name already contains the full camera prefix
        img_stem   = Path(img_name).stem
        cam_prefix = cam_dir.name
        stem       = f"{cam_prefix}__{img_stem}"
        # Priority: _4_final_saved_crops > _3_contours > _1_original
        # Skip _2_diff (black & white diff image, not useful for annotation)
        debug_img = (
            next(debug_dir.glob(f"{stem}*_4_final_saved_crops*"), None)
            or next(debug_dir.glob(f"{stem}*_3_contours*"), None)
            or next(debug_dir.glob(f"{stem}*_1_original*"), None)
            or next((p for p in sorted(debug_dir.glob(f"{stem}*"))
                     if "_2_diff" not in p.name), None)
            or next(debug_dir.glob(f"{stem}*"), None)
        )
        if crops:
            tasks.append((debug_img, img_name, crops, cam_dir.name))

# Pre-load all thumbnails into memory cache to avoid repeated disk reads
# This is the main cause of slow rendering and freezing
thumb_cache = {}  # crop_path -> (thumb_bgr, orig_w, orig_h)

total_images = len(tasks)
total_crops  = sum(len(c) for _, _, c, _ in tasks)
all_crop_fns = {cf for _, _, crops, _ in tasks for _, cf in crops}
done_crops   = sum(1 for fn in progress if fn in all_crop_fns)

print(f"Images: {total_images} | Total crops: {total_crops} | "
      f"Labeled: {done_crops} | Remaining: {total_crops - done_crops}")

if not tasks:
    print("No tasks found. Check --results path.")
    sys.exit(0)


# ── UI ────────────────────────────────────────────────────────────────────────
WIN_W, WIN_H = 1800, 1100
DEBUG_W      = 800
PANEL_W      = WIN_W - DEBUG_W
CROP_SIZE    = 160
PAD          = 8
CROP_COLS    = max(1, PANEL_W // (CROP_SIZE + PAD))
HEADER_H     = 65
FOOTER_H     = 40
CROP_AREA_H  = WIN_H - HEADER_H - FOOTER_H
ROWS_VISIBLE = max(1, CROP_AREA_H // (CROP_SIZE + PAD + 50) - 1)  # extra margin for footer

# ── Pre-cache all thumbnails ───────────────────────────────────────────────────
print(f"Loading thumbnails for {total_crops} crops...")
thumb_cache = {}
cached = 0
for _, _, crops, _ in tasks:
    for crop_path, crop_fn in crops:
        key = str(crop_path)
        if key in thumb_cache:
            continue
        img = cv2.imread(key)
        if img is None:
            thumb_cache[key] = (np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8), 0, 0)
            continue
        orig_h, orig_w = img.shape[:2]
        scale = CROP_SIZE / max(orig_w, orig_h)
        tw    = max(1, int(orig_w * scale))
        th    = max(1, int(orig_h * scale))
        thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
        thumb_cache[key] = (thumb, orig_w, orig_h)
        cached += 1
print(f"Thumbnails cached: {cached}")

COLORS = {
    "insect":     (50,  210,  50),
    "background": (50,   50, 210),
    "skip":       (210, 210,  50),
    None:         (90,  90,  90),
}
BADGES = {"insect": "I", "background": "B", "skip": "S", None: "?"}

state = {"task_idx": 0, "selected_idx": None, "scroll_row": 0}
click_buf = [None]

def on_trackbar(val):
    state["task_idx"]     = val
    state["selected_idx"] = None
    state["scroll_row"]   = 0

def get_total_rows():
    _, _, crops, _ = tasks[state["task_idx"]]
    return max(1, (len(crops) - 1) // CROP_COLS + 1)

def show_debug_large(debug_path, img_name):
    """Show the debug image fullscreen with a visible CLOSE hint."""
    if debug_path is None or not Path(debug_path).exists():
        return
    img = cv2.imread(str(debug_path))
    if img is None:
        return
    oh, ow = img.shape[:2]
    max_w, max_h = 1600, 1000
    scale = min(max_w/ow, max_h/oh, 2.0)
    img_show = cv2.resize(img, (int(ow*scale), int(oh*scale)),
                          interpolation=cv2.INTER_AREA)
    sh, sw = img_show.shape[:2]

    # Draw close button hint in top-right corner
    btn_w, btn_h = 120, 36
    cv2.rectangle(img_show, (sw-btn_w-8, 8), (sw-8, 8+btn_h), (30,30,30), -1)
    cv2.rectangle(img_show, (sw-btn_w-8, 8), (sw-8, 8+btn_h), (80,80,200), 2)
    cv2.putText(img_show, "X  CLOSE", (sw-btn_w+6, 8+btn_h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80,80,200), 1)

    # Info bar at bottom
    bar = np.zeros((32, sw, 3), dtype=np.uint8)
    info = f"{Path(debug_path).name}  |  {ow}x{oh}px  |  click or press any key to close"
    cv2.putText(bar, info, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160,160,160), 1)
    full_img = np.vstack([img_show, bar])

    WIN_DBG = "Debug Image"
    cv2.imshow(WIN_DBG, full_img)

    # Close on any click or any key
    def _close_on_click(event, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            cv2.destroyWindow(WIN_DBG)
    cv2.setMouseCallback(WIN_DBG, _close_on_click)
    cv2.waitKey(0)
    cv2.destroyWindow(WIN_DBG)
    cv2.waitKey(1)  # flush key buffer


def show_preview(crop_path, crop_fn):
    """Show large preview of a crop in a popup window."""
    img = cv2.imread(str(crop_path))
    if img is None:
        return
    orig_h, orig_w = img.shape[:2]
    max_w, max_h = 900, 750
    scale = min(max_w / orig_w, max_h / orig_h, 3.0)  # allow upscale up to 3x
    img = cv2.resize(img, (int(orig_w * scale), int(orig_h * scale)),
                     interpolation=cv2.INTER_NEAREST if scale > 1 else cv2.INTER_AREA)
    ph, pw = img.shape[:2]
    bar = np.zeros((35, pw, 3), dtype=np.uint8)
    info = f"{crop_fn}  |  original: {orig_w}x{orig_h}px  |  press any key to close"
    cv2.putText(bar, info, (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180,180,180), 1)
    preview = np.vstack([img, bar])
    cv2.imshow("Preview", preview)
    cv2.waitKey(0)
    cv2.destroyWindow("Preview")
    cv2.waitKey(1)  # flush key buffer

def on_mouse(event, x, y, flags, param):
    _, _, crops, _ = tasks[state["task_idx"]]
    total_rows = get_total_rows()
    max_scroll = max(0, total_rows - ROWS_VISIBLE)

    # Mouse wheel scroll
    # Windows/Linux: flags > 0 = scroll up
    # macOS: flags > 0 = scroll DOWN (inverted)
    if event == cv2.EVENT_MOUSEWHEEL:
        # flags is a signed 32-bit int; positive = scroll up on all platforms
        # Cast to signed int to handle platform differences
        signed_flags = flags if flags < 2**31 else flags - 2**32
        delta = -1 if signed_flags > 0 else 1
        state["scroll_row"] = max(0, min(state["scroll_row"] + delta, max_scroll))
        return

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    # Click on scrollbar area (right 14px of panel)
    sb_x = WIN_W - 14
    if x >= sb_x and total_rows > ROWS_VISIBLE:
        sb_y1 = HEADER_H
        sb_y2 = WIN_H - FOOTER_H
        ratio  = (y - sb_y1) / max(1, sb_y2 - sb_y1)
        state["scroll_row"] = int(ratio * total_rows)
        state["scroll_row"] = max(0, min(state["scroll_row"], max_scroll))
        return

    # Click on left debug panel → show large image
    if x < DEBUG_W:
        click_buf[0] = -2   # special code for debug panel click
        return

    # Click on crops
    for i in range(len(crops)):
        x1, y1, x2, y2 = crop_rect(i)
        if y1 < HEADER_H or y2 > WIN_H - FOOTER_H: continue
        if x1 <= x <= x2 and y1 <= y <= y2:
            # Second click on already-selected crop → open preview
            if state["selected_idx"] == i:
                click_buf[0] = -3   # preview trigger
            else:
                click_buf[0] = i
            return
    click_buf[0] = -1

debug_cache = {}  # cache full debug images

def load_debug(path):
    tw, th = DEBUG_W, WIN_H
    if path is None or not Path(path).exists():
        blank = np.zeros((th, tw, 3), dtype=np.uint8)
        cv2.putText(blank, "No debug image", (20, th//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (160,160,160), 2)
        return blank
    if path not in debug_cache:
        img = cv2.imread(str(path))
        if img is None:
            debug_cache[path] = np.zeros((th, tw, 3), dtype=np.uint8)
        else:
            h, w = img.shape[:2]
            scale = min(tw/w, th/h)
            img = cv2.resize(img, (int(w*scale), int(h*scale)),
                             interpolation=cv2.INTER_AREA)
            canvas = np.zeros((th, tw, 3), dtype=np.uint8)
            canvas[:img.shape[0], :img.shape[1]] = img
            debug_cache[path] = canvas
    return debug_cache[path].copy()

def load_thumb(path):
    """Return cached thumbnail. Falls back to reading file if not cached."""
    key = str(path)
    if key in thumb_cache:
        return thumb_cache[key]
    # Fallback (should not happen after startup cache)
    img = cv2.imread(key)
    if img is None:
        return np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8), 0, 0
    orig_h, orig_w = img.shape[:2]
    scale = CROP_SIZE / max(orig_w, orig_h)
    thumb = cv2.resize(img, (max(1, int(orig_w*scale)), max(1, int(orig_h*scale))),
                       interpolation=cv2.INTER_AREA)
    return thumb, orig_w, orig_h

def get_crop_display_h(crop_path):
    """Return display height for a crop based on its actual aspect ratio."""
    img = cv2.imread(str(crop_path))
    if img is None:
        return CROP_SIZE
    h, w = img.shape[:2]
    # Scale so width = CROP_SIZE, compute proportional height
    display_h = int(CROP_SIZE * h / max(1, w))
    return max(30, min(display_h, CROP_SIZE * 2))  # min 30px, max 2x CROP_SIZE


def crop_rect(idx):
    """Returns (x1, y1, x2, y2) where height is proportional to actual crop aspect ratio."""
    _, _, crops, _ = tasks[state["task_idx"]]
    col = idx % CROP_COLS

    # Compute cumulative row height up to this row
    # Each row height = max display_h of crops in that row
    row_of_idx = idx // CROP_COLS
    y = HEADER_H + PAD

    for r in range(row_of_idx - state["scroll_row"]):
        row_start = (r + state["scroll_row"]) * CROP_COLS
        row_crops  = crops[row_start:row_start + CROP_COLS]
        row_h = max((get_crop_display_h(cp) for cp, _ in row_crops), default=CROP_SIZE)
        y += row_h + PAD + 45  # 45px for label text below

    x1 = DEBUG_W + PAD + col * (CROP_SIZE + PAD)
    # Height for this cell
    crop_h = get_crop_display_h(crops[idx][0]) if idx < len(crops) else CROP_SIZE
    return x1, y, x1 + CROP_SIZE, y + crop_h

def apply_label(crop_fn, crop_path, label):
    # Remove from old label folder if re-labeling
    if crop_fn in progress:
        old_label = progress[crop_fn]
        old_dest  = OUTPUT_DIR / old_label / crop_fn
        if old_dest.exists():
            old_dest.unlink()

    dest = OUTPUT_DIR / label / crop_fn
    if dest.exists():
        dest = OUTPUT_DIR / label / f"{state['task_idx']}_{crop_fn}"
    shutil.copy2(crop_path, dest)
    progress[crop_fn] = label
    save_progress()

def render():
    idx  = state["task_idx"]
    sel  = state["selected_idx"]
    debug_path, img_name, crops, cam_name = tasks[idx]
    crops_labels = {cf: progress.get(cf) for _, cf in crops}

    canvas = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
    canvas[:, :DEBUG_W] = load_debug(debug_path)

    # Header
    cv2.rectangle(canvas, (0,0), (WIN_W, HEADER_H-2), (25,25,25), -1)
    done_this = sum(1 for _, cf in crops if cf in progress)
    g_done    = sum(1 for fn in progress if fn in all_crop_fns)
    total_rows = (len(crops) - 1) // CROP_COLS + 1

    more_below = total_rows > state["scroll_row"] + ROWS_VISIBLE
    more_indicator = "  [v more crops below]" if more_below else ""
    cv2.putText(canvas,
                f"[{idx+1}/{total_images}]  {cam_name} / {Path(img_name).name}  "
                f"({done_this}/{len(crops)} labeled){more_indicator}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220,220,220), 1)
    cv2.putText(canvas,
                f"Total: {g_done}/{total_crops}  |  "
                "I=insect B=background S=skip U=undo all | click=select re-click=zoom | click debug=zoom  |  "
                "A=prev  D=next  |  W=scroll up  X=scroll down  |  Q=quit",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160,160,160), 1)

    # Footer — scroll info
    cv2.rectangle(canvas, (DEBUG_W, WIN_H-FOOTER_H), (WIN_W, WIN_H), (20,20,20), -1)
    scroll_info = (f"Rows {state['scroll_row']+1}-"
                   f"{min(state['scroll_row']+ROWS_VISIBLE, total_rows)}/{total_rows}  "
                   f"|  W=scroll up  X=scroll down  |  Double-click crop = large preview")
    cv2.putText(canvas, scroll_info,
                (DEBUG_W+10, WIN_H-12), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (130,130,130), 1)

    # Scrollbar on right edge of panel
    if total_rows > ROWS_VISIBLE:
        sb_x  = WIN_W - 12
        sb_y1 = HEADER_H
        sb_y2 = WIN_H - FOOTER_H
        sb_h  = sb_y2 - sb_y1
        # Track background
        cv2.rectangle(canvas, (sb_x, sb_y1), (sb_x+10, sb_y2), (40,40,40), -1)
        # Thumb position and size
        thumb_h   = max(20, int(sb_h * ROWS_VISIBLE / total_rows))
        thumb_top = sb_y1 + int((sb_h - thumb_h) * state["scroll_row"] / max(1, total_rows - ROWS_VISIBLE))
        cv2.rectangle(canvas, (sb_x, thumb_top), (sb_x+10, thumb_top+thumb_h), (140,140,180), -1)
        # Arrows
        cv2.putText(canvas, "^", (sb_x+1, sb_y1+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180,180,180), 1)
        cv2.putText(canvas, "v", (sb_x+1, sb_y2-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180,180,180), 1)

    # Crops
    for i, (crop_path, crop_fn) in enumerate(crops):
        x1, y1, x2, y2 = crop_rect(i)
        if y2 < HEADER_H or y1 >= WIN_H - FOOTER_H - 30: continue
        if x2 > WIN_W: continue

        # Use thumbnail cache — read from disk only once per crop
        if crop_path not in thumb_cache:
            img_raw = cv2.imread(str(crop_path))
            if img_raw is None:
                thumb_cache[crop_path] = (np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8), 0, 0)
            else:
                orig_h, orig_w = img_raw.shape[:2]
                scale = CROP_SIZE / max(1, orig_w)
                tw_d  = CROP_SIZE
                th_d  = max(30, int(orig_h * scale))
                # Cap thumbnail height to avoid huge crops slowing render
                th_d  = min(th_d, CROP_SIZE * 2)
                thumb = cv2.resize(img_raw, (tw_d, th_d),
                                   interpolation=cv2.INTER_AREA)
                thumb_cache[crop_path] = (thumb, orig_w, orig_h)
        thumb, orig_w, orig_h = thumb_cache[crop_path]

        th, tw = thumb.shape[:2]
        tx, ty = x1, y1
        th_clipped = min(th, WIN_H - FOOTER_H - 30 - ty)
        if 0 <= ty and th_clipped > 0 and tx+tw <= WIN_W - 15:
            canvas[ty:ty+th_clipped, tx:tx+tw] = thumb[:th_clipped]

        label  = crops_labels.get(crop_fn)
        color  = COLORS[label]
        border = 4 if i == sel else 2

        # Draw border around actual thumb, not full cell
        cv2.rectangle(canvas, (tx-2, ty-2), (tx+tw+2, ty+th+2), color, border)

        # Badge
        cv2.rectangle(canvas, (tx, ty+th), (tx+22, ty+th+17), color, -1)
        cv2.putText(canvas, BADGES[label], (tx+4, ty+th+13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0,0,0), 1)

        # Actual size info
        if orig_w > 0:
            size_txt = f"{orig_w}x{orig_h}"
            cv2.putText(canvas, size_txt, (tx, ty+th+30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (140,180,140), 1)

        # Filename
        # Extract crop number from filename e.g. "WSCT6147_crop_3_normal.jpg" -> "#3"
        import re as _re
        crop_num_match = _re.search(r'_crop_(\d+)', crop_fn)
        crop_num = f"#{crop_num_match.group(1)}" if crop_num_match else ""
        short = (".."+crop_fn[-12:]) if len(crop_fn)>14 else crop_fn
        display = f"{crop_num}  {short}" if crop_num else short
        cv2.putText(canvas, display, (tx, ty+th+42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.28, (110,110,110), 1)

        if i == sel:
            ov = canvas.copy()
            cv2.rectangle(ov, (tx-2, ty-2), (tx+tw+2, ty+th+2), (255,255,255), -1)
            cv2.addWeighted(ov, 0.15, canvas, 0.85, 0, canvas)

    return canvas

# ── Window ────────────────────────────────────────────────────────────────────
WINDOW = "Pollinator Annotator"
cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW, WIN_W, WIN_H)
cv2.moveWindow(WINDOW, 0, 0)  # start at top-left
cv2.createTrackbar("Image", WINDOW, 0, max(1, total_images-1), on_trackbar)
cv2.setMouseCallback(WINDOW, on_mouse)

while True:
    tb_val = cv2.getTrackbarPos("Image", WINDOW)
    if tb_val != state["task_idx"] and click_buf[0] is None:
        state["task_idx"]     = tb_val
        state["selected_idx"] = None
        state["scroll_row"]   = 0

    if click_buf[0] is not None:
        val = click_buf[0]
        click_buf[0] = None
        if val == -2:
            # Clicked debug panel — show large image
            debug_path, img_name, _, _ = tasks[state["task_idx"]]
            show_debug_large(debug_path, img_name)
        elif val == -3:
            # Second click on selected crop — show preview
            sel = state["selected_idx"]
            if sel is not None:
                _, _, crops, _ = tasks[state["task_idx"]]
                if sel < len(crops):
                    crop_path, crop_fn = crops[sel]
                    show_preview(crop_path, crop_fn)
        elif val == -1:
            state["selected_idx"] = None
        else:
            state["selected_idx"] = val

    cv2.imshow(WINDOW, render())
    # waitKeyEx handles extended keys (arrows) on Windows
    key_raw = cv2.waitKeyEx(30)
    key = key_raw & 0xFF

    if key in (ord('p'), ord('P')):
        # P = preview selected crop
        sel = state["selected_idx"]
        if sel is not None:
            _, _, crops, _ = tasks[state["task_idx"]]
            if sel < len(crops):
                crop_path, crop_fn = crops[sel]
                show_preview(crop_path, crop_fn)

    elif key in (ord('u'), ord('U')):
        # U = unannotate ALL crops in current image
        _, _, crops, _ = tasks[state["task_idx"]]
        removed = 0
        for crop_path, crop_fn in crops:
            if crop_fn in progress:
                old_label = progress[crop_fn]
                old_dest  = OUTPUT_DIR / old_label / crop_fn
                if old_dest.exists():
                    old_dest.unlink()
                del progress[crop_fn]
                removed += 1
        if removed:
            save_progress(force=True)
            print(f"Unannotated {removed} crops in current image")
        state["selected_idx"] = None

    elif key in (ord('q'), ord('Q')):
        save_progress(force=True)
        break

    elif key in (ord('i'), ord('I'), ord('b'), ord('B'), ord('s'), ord('S')):
        label = {ord('i'):'insect', ord('I'):'insect',
                 ord('b'):'background', ord('B'):'background',
                 ord('s'):'skip', ord('S'):'skip'}[key]
        _, _, crops, _ = tasks[state["task_idx"]]
        sel = state["selected_idx"]
        if sel is not None and sel < len(crops):
            crop_path, crop_fn = crops[sel]
            apply_label(crop_fn, crop_path, label)
            state["selected_idx"] = None
        else:
            for crop_path, crop_fn in crops:
                if crop_fn not in progress:
                    apply_label(crop_fn, crop_path, label)

    elif key in (ord('d'), ord('D')) or key_raw in (83, 65363, 2555904, 63235):   # D / right arrow (Linux/macOS/Windows)
        new_idx = min(state["task_idx"]+1, total_images-1)
        state.update({"task_idx": new_idx, "selected_idx": None, "scroll_row": 0})
        cv2.setTrackbarPos("Image", WINDOW, new_idx)

    elif key in (ord('a'), ord('A')) or key_raw in (81, 65361, 2424832, 63234):   # A / left arrow
        new_idx = max(state["task_idx"]-1, 0)
        state.update({"task_idx": new_idx, "selected_idx": None, "scroll_row": 0})
        cv2.setTrackbarPos("Image", WINDOW, new_idx)

    elif key in (ord('w'), ord('W')) or key_raw in (82, 65362, 2490368, 63232):   # W / up arrow
        state["scroll_row"] = max(0, state["scroll_row"] - 1)

    elif key in (ord('x'), ord('X')) or key_raw in (84, 65364, 2621440, 63233):   # X / down arrow
        _, _, crops, _ = tasks[state["task_idx"]]
        total_rows = (len(crops) - 1) // CROP_COLS + 1
        max_scroll = max(0, total_rows - ROWS_VISIBLE)
        state["scroll_row"] = min(state["scroll_row"]+1, max_scroll)

cv2.destroyAllWindows()
save_progress()

i_n = len(list((OUTPUT_DIR/"insect").glob("*.jpg")))
b_n = len(list((OUTPUT_DIR/"background").glob("*.jpg")))
s_n = len(list((OUTPUT_DIR/"skip").glob("*.jpg")))
print(f"\nDone!  insect={i_n}  background={b_n}  skip={s_n}")
print(f"Saved to: {OUTPUT_DIR}")
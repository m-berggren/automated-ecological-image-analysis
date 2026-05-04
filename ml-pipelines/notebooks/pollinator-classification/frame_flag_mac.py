
#  - Play image folders and flag interesting frames on Mac using OpenCV.
# Usage:
#  - python frame_flag_mac.py [--list] IMAGE_ROOT --interval 1 --cache-size 24
#  - IMAGE_ROOT should contain one or more subfolders with images.
#   The script will play each folder as a slideshow, showing one image at a time.
#   Press the specified mark key (default "m") to mark the current image, or "u" to unmark it.
#   Marked images are saved in a JSON file (default "flags_all.json") for later preprocessing.
#   Use the --list option to just list the folders and image counts without playing.
#  - Controls while playing:
#   - m = mark current image
#   - u = unmark current image
#   - space / h = pause or resume slideshow
#   - a / d = previous or next image
#   - n = next folder
#   - b = previous folder
#   - q / Esc = quit all

#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
WINDOW = "frame mark"

LEFT_KEYS = {81, 2424832, 65361}
RIGHT_KEYS = {83, 2555904, 65363}


def parse_args():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Play image folders and mark interesting frames on Mac using OpenCV."
    )
    parser.add_argument("root", nargs="?", type=Path, help="Image root folder")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("INTERVAL", "2")),
        help="Seconds between images while playing",
    )
    parser.add_argument(
        "--flag-file",
        type=Path,
        default=Path(os.environ.get("FLAG_FILE", script_dir / "flags_all.json")),
        help="JSON file used to save marked images",
    )
    parser.add_argument(
        "--mark-key",
        default=os.environ.get("MARK_KEY", "m"),
        help="Single key used to mark the current image",
    )
    parser.add_argument("--max-width", type=int, default=1600)
    parser.add_argument("--max-height", type=int, default=950)
    parser.add_argument(
        "--cache-size",
        type=int,
        default=8,
        help="Number of decoded/resized images to keep in memory",
    )
    parser.add_argument(
        "--debug-keys",
        action="store_true",
        help="Print OpenCV key codes",
    )
    return parser.parse_args()


def image_files(folder):
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def playable_folders(root):
    root = root.resolve()
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        folder = Path(dirpath)
        imgs = image_files(folder)
        if imgs:
            yield folder, imgs


def load_flags(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_flags(path, flags):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(flags, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def read_image(path):
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def fit_image(img, max_w, max_h):
    h, w = img.shape[:2]
    scale = min(max_w / max(1, w), max_h / max(1, h), 1.0)

    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    if (new_w, new_h) == (w, h):
        return img

    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


class ImageCache:
    def __init__(self, max_items, max_w, max_h):
        self.max_items = max(1, max_items)
        self.max_w = max_w
        self.max_h = max_h
        self.cache = OrderedDict()

    def get(self, path):
        key = str(path.resolve())

        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]

        raw = read_image(path)
        fitted = fit_image(raw, self.max_w, self.max_h) if raw is not None else None

        self.cache[key] = fitted
        self.cache.move_to_end(key)

        while len(self.cache) > self.max_items:
            self.cache.popitem(last=False)

        return fitted


def put_text(img, text, org, scale=0.55, color=(235, 235, 235), thickness=1):
    cv2.putText(
        img,
        text,
        org,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def render_image(
    path,
    folder,
    folder_idx,
    folder_total,
    img_idx,
    img_total,
    flags,
    paused,
    max_w,
    max_h,
    cache,
):
    canvas_w, canvas_h = max_w, max_h
    top_h = 74
    bottom_h = 54

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    canvas[:] = (18, 18, 18)

    fitted = cache.get(path)

    if fitted is None:
        put_text(
            canvas,
            "Could not load image",
            (40, canvas_h // 2),
            0.9,
            (80, 120, 255),
            2,
        )
    else:
        ih, iw = fitted.shape[:2]
        x = (canvas_w - iw) // 2
        y = top_h + max(0, (canvas_h - top_h - bottom_h - ih) // 2)
        canvas[y : y + ih, x : x + iw] = fitted

    key = str(path.resolve())
    marked = bool(flags.get(key))

    cv2.rectangle(canvas, (0, 0), (canvas_w, top_h), (28, 28, 28), -1)
    cv2.rectangle(
        canvas,
        (0, canvas_h - bottom_h),
        (canvas_w, canvas_h),
        (28, 28, 28),
        -1,
    )

    folder_txt = f"[{folder_idx + 1}/{folder_total}] {folder}"
    image_txt = f"[{img_idx + 1}/{img_total}] {path.name}"

    status = "PAUSED" if paused else "PLAYING"
    if marked:
        status += " | MARKED"

    put_text(canvas, folder_txt, (12, 26), 0.50, (220, 220, 220), 1)
    put_text(canvas, image_txt, (12, 55), 0.58, (245, 245, 245), 1)
    put_text(
        canvas,
        status,
        (canvas_w - 260, 45),
        0.72,
        (60, 220, 255) if marked else (160, 220, 160),
        2,
    )

    help_txt = (
        "m=mark  u=unmark  space/h=pause  a/d=prev/next  "
        "Left/Right=backup  n=next folder  b=prev folder  q/Esc=quit"
    )
    put_text(canvas, help_txt, (12, canvas_h - 19), 0.50, (190, 190, 190), 1)

    return canvas


def show_folder(
    folder,
    imgs,
    folder_idx,
    folder_total,
    flags,
    flag_file,
    args,
    start_idx=0,
):
    idx = min(max(0, start_idx), len(imgs) - 1)
    paused = False
    dirty = True
    frame = None

    image_area_w = args.max_width
    image_area_h = args.max_height - 74 - 54
    cache = ImageCache(args.cache_size, image_area_w, image_area_h)

    next_deadline = time.monotonic() + max(0.05, args.interval)
    mark_key = args.mark_key.lower()

    print("=====================================")
    print(f"Folder: {folder}")
    print(f"Images: {len(imgs)}")
    print(f"{args.mark_key} = mark current image")
    print("u = unmark current image")
    print("space / h = pause or resume slideshow")
    print("a / d = previous or next image")
    print("Left / Right = backup previous or next image")
    print("n = next folder")
    print("b = previous folder")
    print("q / Esc = quit all")
    print(f"Flags: {flag_file}")
    print("=====================================")

    while True:
        if dirty:
            frame = render_image(
                imgs[idx],
                folder,
                folder_idx,
                folder_total,
                idx,
                len(imgs),
                flags,
                paused,
                args.max_width,
                args.max_height,
                cache,
            )
            cv2.imshow(WINDOW, frame)
            dirty = False
        else:
            cv2.imshow(WINDOW, frame)

        key = cv2.waitKeyEx(10)
        key_low = key & 0xFF if key >= 0 else -1
        ch = chr(key_low).lower() if 0 <= key_low <= 255 else ""

        if args.debug_keys and key != -1:
            print(f"key={key}, key_low={key_low}, ch={repr(ch)}")

        if key == 27 or ch == "q":
            return "quit", idx

        if ch == "n":
            return "next_folder", idx

        if ch == "b":
            return "prev_folder", idx

        if ch in (" ", "h"):
            paused = not paused
            next_deadline = time.monotonic() + max(0.05, args.interval)
            dirty = True

        elif ch == mark_key:
            flags[str(imgs[idx].resolve())] = True
            save_flags(flag_file, flags)
            print(f"Marked: {imgs[idx]}")
            dirty = True

        elif ch == "u":
            removed = flags.pop(str(imgs[idx].resolve()), None)
            save_flags(flag_file, flags)
            if removed is not None:
                print(f"Unmarked: {imgs[idx]}")
            dirty = True

        elif ch == "a" or key in LEFT_KEYS:
            idx = (idx - 1) % len(imgs)
            next_deadline = time.monotonic() + max(0.05, args.interval)
            dirty = True

        elif ch == "d" or key in RIGHT_KEYS:
            idx = (idx + 1) % len(imgs)
            next_deadline = time.monotonic() + max(0.05, args.interval)
            dirty = True

        if not paused and time.monotonic() >= next_deadline:
            idx = (idx + 1) % len(imgs)
            next_deadline = time.monotonic() + max(0.05, args.interval)
            dirty = True


def main():
    args = parse_args()

    if args.root is None:
        print("Usage: python slide_mark.py [--list] IMAGE_ROOT", file=sys.stderr)
        return 1

    if not args.root.is_dir():
        print(f"Image root does not exist: {args.root}", file=sys.stderr)
        return 1

    if len(args.mark_key) != 1:
        print("--mark-key must be a single character", file=sys.stderr)
        return 1

    folders = list(playable_folders(args.root))

    if args.list:
        for folder, imgs in folders:
            print(f"{len(imgs):6d}  {folder}")
        print("List complete.")
        return 0

    if not folders:
        print(f"No image folders found under: {args.root}", file=sys.stderr)
        return 1

    flag_file = args.flag_file.resolve()
    flags = load_flags(flag_file)

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, args.max_width, args.max_height)

    folder_positions = {}
    folder_idx = 0

    try:
        while 0 <= folder_idx < len(folders):
            folder, imgs = folders[folder_idx]
            start_idx = folder_positions.get(str(folder.resolve()), 0)

            result, last_idx = show_folder(
                folder,
                imgs,
                folder_idx,
                len(folders),
                flags,
                flag_file,
                args,
                start_idx=start_idx,
            )

            folder_positions[str(folder.resolve())] = last_idx

            if result == "quit":
                break
            elif result == "prev_folder":
                folder_idx = max(0, folder_idx - 1)
            else:
                folder_idx += 1

    finally:
        cv2.destroyAllWindows()

    save_flags(flag_file, flags)
    print(f"Done. Mark file: {flag_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
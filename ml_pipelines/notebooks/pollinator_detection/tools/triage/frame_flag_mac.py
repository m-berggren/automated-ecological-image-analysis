#!/usr/bin/env python3

# Browse camera image folders as a slideshow, mark frames that look like they
# contain a pollinator, then copy the marked frames (plus surrounding context
# frames) to a destination folder of your choice.
#
# What it does:
#   1. Opens a Finder dialog to select the camera image root folder
#      (skip this by passing IMAGE_ROOT on the command line).
#   2. Plays each camera subfolder as a slideshow — press m to mark a frame.
#   3. When you quit (Esc), if any frames were marked a second Finder dialog
#      opens so you can choose where to save the copies.
#   4. Copies every marked frame PLUS --context-frames frames before and after
#      each one into {dest}/{camera_name}_{timestamp}/.
#      Context frames are included so the preprocessing pipeline has prior
#      frames to use as background reference.
#   5. Saves all marked paths to flags_all.json (persists across sessions).
#
# Usage:
#   python3 frame_flag_mac.py                           # Finder picks image root
#   python3 frame_flag_mac.py IMAGE_ROOT                # use this folder directly
#   python3 frame_flag_mac.py --list IMAGE_ROOT         # list folders + counts, no slideshow
#   python3 frame_flag_mac.py --context-frames 2        # copy 2 frames before/after each mark (default)
#   python3 frame_flag_mac.py --export-dir /some/path   # set destination without Finder dialog
#   python3 frame_flag_mac.py --export-name my_session  # name the output subfolder
#   python3 frame_flag_mac.py --interval 0.05           # faster slideshow (50 ms/frame)
#
# Controls:
#   m           = mark current frame
#   u           = unmark current frame
#   space / h   = pause or resume slideshow
#   a / d       = previous or next image
#   left / right arrow = previous or next image
#   n           = next camera folder
#   b           = previous camera folder
#   Esc         = quit (destination picker opens if anything was marked)
#
# Note:
#   q is intentionally not used for quitting, because OpenCV on macOS can
#   sometimes misread other key codes as q.
#
# Important:
#   This script uses osascript for folder picking instead of tkinter, because
#   tkinter and OpenCV HighGUI can crash together on macOS.

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
WINDOW = 'frame mark'

LEFT_KEYS = {81, 2424832, 65361}
RIGHT_KEYS = {83, 2555904, 65363}


def choose_folder_with_applescript(prompt, default_location):
    default_location = str(Path(default_location).expanduser())

    script = f'''
        set chosenFolder to choose folder with prompt "{prompt}" default location POSIX file "{default_location}"
        return POSIX path of chosenFolder
    '''

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        print(f'Could not open Finder folder picker: {exc}', file=sys.stderr)
        return None

    if result.returncode != 0:
        return None

    folder = result.stdout.strip()

    if not folder:
        return None

    return Path(folder)


def choose_image_root_with_finder():
    return choose_folder_with_applescript(
        prompt='Select image root folder',
        default_location='/Volumes',
    )


def choose_export_folder_with_finder():
    return choose_folder_with_applescript(
        prompt='Select folder to save copied flagged images',
        default_location=Path.home() / 'Desktop',
    )


def parse_args():
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description='Play image folders and mark interesting frames on Mac using OpenCV.'
    )

    parser.add_argument(
        'root',
        nargs='?',
        type=Path,
        help='Image root folder. If omitted, a Finder folder picker will open.',
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List playable folders and image counts without opening the slideshow.',
    )

    parser.add_argument(
        '--interval',
        type=float,
        default=float(os.environ.get('INTERVAL', '0.08')),
        help='Seconds between images while playing.',
    )

    parser.add_argument(
        '--flag-file',
        type=Path,
        default=Path(os.environ.get('FLAG_FILE', script_dir / 'flags_all.json')),
        help='JSON file used to save marked images.',
    )

    parser.add_argument(
        '--export-dir',
        type=Path,
        default=Path.home() / 'Desktop' / 'pollinator_flagged_frames',
        help='Folder where copied marked images and context images will be saved.',
    )

    parser.add_argument(
        '--export-name',
        default=None,
        help='Name of export subfolder. If omitted, selected image path will be used.',
    )

    parser.add_argument(
        '--context-frames',
        type=int,
        default=2,
        help='Number of frames before and after each marked image to copy.',
    )

    parser.add_argument(
        '--mark-key',
        default=os.environ.get('MARK_KEY', 'm'),
        help='Single key used to mark current image.',
    )

    parser.add_argument(
        '--max-width',
        type=int,
        default=1600,
        help='Maximum display width.',
    )

    parser.add_argument(
        '--max-height',
        type=int,
        default=950,
        help='Maximum display height.',
    )

    parser.add_argument(
        '--cache-size',
        type=int,
        default=8,
        help='Number of decoded/resized images to keep in memory.',
    )

    parser.add_argument(
        '--debug-keys',
        action='store_true',
        help='Print OpenCV key codes.',
    )

    return parser.parse_args()


def safe_folder_part(text):
    text = str(text).strip()

    if not text:
        return 'flagged_images'

    bad_chars = '<>:"/\\|?*'
    for ch in bad_chars:
        text = text.replace(ch, '_')

    text = text.replace(' ', '_')
    return text


def path_to_export_name(path):
    path = Path(path).resolve()
    parts = list(path.parts)

    if 'Gruvan' in parts:
        parts = parts[parts.index('Gruvan') :]
    else:
        parts = [part for part in parts if part not in ('/', 'Volumes')]

    if not parts:
        return 'flagged_images'

    return safe_folder_part('_'.join(parts))


def image_files(folder):
    try:
        return sorted(
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
    except Exception as exc:
        print(f'Could not read folder: {folder} ({exc})', file=sys.stderr)
        return []


def playable_folders(root):
    root = root.resolve()

    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        folder = Path(dirpath)
        imgs = image_files(folder)

        if imgs:
            yield folder, imgs


def load_flags(path):
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f'Could not load flag file: {path} ({exc})', file=sys.stderr)
        return {}


def save_flags(path, flags):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(flags, indent=2, sort_keys=True), encoding='utf-8')
        tmp.replace(path)
        return True
    except Exception as exc:
        print(f'Could not save flag file: {path} ({exc})', file=sys.stderr)
        return False


def read_image(path):
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as exc:
        print(f'Could not read image: {path} ({exc})', file=sys.stderr)
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
    is_last=False,
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
            'Could not load image',
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

    folder_txt = f'[{folder_idx + 1}/{folder_total}] {folder}'
    last_tag = '  ★ LAST IMAGE ★' if is_last else ''
    image_txt = f'[{img_idx + 1}/{img_total}] {path.name}{last_tag}'

    status = 'PAUSED' if paused else 'PLAYING'
    if marked:
        status += ' | MARKED'

    folder_color = (80, 220, 255) if is_last else (220, 220, 220)
    image_color = (80, 220, 255) if is_last else (245, 245, 245)
    put_text(canvas, folder_txt, (12, 26), 0.50, folder_color, 1)
    put_text(canvas, image_txt, (12, 55), 0.58, image_color, 1)

    put_text(
        canvas,
        status,
        (canvas_w - 260, 45),
        0.72,
        (60, 220, 255) if marked else (160, 220, 160),
        2,
    )

    # Banner at the bottom of the top bar when on the last image
    if is_last:
        banner = (
            '── END OF FOLDER  |  n = next folder    b = prev folder    Esc = quit ──'
        )
        put_text(
            canvas,
            banner,
            (canvas_w // 2 - 370, top_h - 6),
            0.45,
            (255, 255, 255),
            1,
        )
        cv2.rectangle(canvas, (0, top_h - 18), (canvas_w, top_h - 1), (0, 130, 200), -1)
        put_text(
            canvas,
            banner,
            (canvas_w // 2 - 370, top_h - 5),
            0.45,
            (255, 255, 255),
            1,
        )

    help_txt = (
        'm=mark  u=unmark  space/h=play/pause  a/d=prev/next  '
        'Left/Right=prev/next  n=next folder  b=prev folder  Esc=quit'
    )

    put_text(canvas, help_txt, (12, canvas_h - 19), 0.50, (190, 190, 190), 1)

    return canvas


def key_to_char(key):
    if 0 <= key < 256:
        return chr(key).lower()
    return ''


def show_folder(
    folder,
    imgs,
    folder_idx,
    folder_total,
    flags,
    flag_file,
    args,
    session_marked,
    start_idx=0,
):
    idx = min(max(0, start_idx), len(imgs) - 1)

    # Start paused. It only shows the first image until space/h is pressed.
    paused = True

    dirty = True
    frame = None

    image_area_w = args.max_width
    image_area_h = args.max_height - 74 - 54
    cache = ImageCache(args.cache_size, image_area_w, image_area_h)

    next_deadline = time.monotonic() + max(0.01, args.interval)
    mark_key = args.mark_key.lower()

    print('=====================================')
    print(f'Folder: {folder}')
    print(f'Images: {len(imgs)}')
    print(f'{args.mark_key} = mark current image')
    print('u = unmark current image')
    print('space / h = play or pause slideshow')
    print('a / d = previous or next image')
    print('Left / Right = previous or next image')
    print('n = next folder')
    print('b = previous folder')
    print('Esc = quit all')
    print(f'Flags: {flag_file}')
    print('Starts paused. Press space or h to play.')
    print('=====================================')

    while True:
        is_last = idx == len(imgs) - 1

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
                is_last=is_last,
            )
            cv2.imshow(WINDOW, frame)
            dirty = False
        else:
            cv2.imshow(WINDOW, frame)

        # 20ms is more stable on macOS than a very tight 1ms loop.
        key = cv2.waitKeyEx(20)

        if args.debug_keys and key != -1:
            print(f'key={key}')

        # Only Esc quits. q is intentionally ignored.
        if key == 27:
            return 'quit', idx

        ch = key_to_char(key)

        if ch == 'n':
            return 'next_folder', idx

        if ch == 'b':
            return 'prev_folder', idx

        if ch in (' ', 'h'):
            paused = not paused
            next_deadline = time.monotonic() + max(0.01, args.interval)
            dirty = True

        elif ch == mark_key:
            img_key = str(imgs[idx].resolve())
            flags[img_key] = True
            session_marked.add(img_key)

            if save_flags(flag_file, flags):
                print(f'Marked and saved: {imgs[idx]}')
            else:
                print(f'Marked but could not save JSON: {imgs[idx]}', file=sys.stderr)

            dirty = True

        elif ch == 'u':
            img_key = str(imgs[idx].resolve())
            removed = flags.pop(img_key, None)
            session_marked.discard(img_key)

            if save_flags(flag_file, flags):
                if removed is not None:
                    print(f'Unmarked and saved: {imgs[idx]}')
                else:
                    print(f'Image was not marked: {imgs[idx]}')
            else:
                print(f'Unmarked but could not save JSON: {imgs[idx]}', file=sys.stderr)

            dirty = True

        elif ch == 'a' or key in LEFT_KEYS:
            idx = (idx - 1) % len(imgs)
            next_deadline = time.monotonic() + max(0.01, args.interval)
            dirty = True

        elif ch == 'd' or key in RIGHT_KEYS:
            idx = (idx + 1) % len(imgs)
            next_deadline = time.monotonic() + max(0.01, args.interval)
            dirty = True

        if not paused and time.monotonic() >= next_deadline:
            if is_last:
                # End of folder reached during playback — pause and show banner
                paused = True
                dirty = True
                print(f'End of folder: {folder}  (n = next folder)')
            else:
                idx += 1
                next_deadline = time.monotonic() + max(0.01, args.interval)
                dirty = True


def unique_folder_name(parent, name):
    candidate = parent / name

    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = parent / f'{name}_{counter}'
        if not candidate.exists():
            return candidate
        counter += 1


def export_marked_images_with_context(
    folders,
    session_marked,
    export_root,
    image_root,
    export_name=None,
    context_frames=2,
):
    marked_paths = {
        str(Path(path).resolve()) for path in session_marked if Path(path).is_file()
    }

    if not marked_paths:
        print('No images were marked in this run. No export folder was created.')
        return None

    export_root = export_root.expanduser()
    export_root.mkdir(parents=True, exist_ok=True)

    if export_name:
        base_name = safe_folder_part(export_name)
    else:
        base_name = path_to_export_name(image_root)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    export_dir = export_root / f'{base_name}_{timestamp}'
    export_dir.mkdir(parents=True, exist_ok=True)

    copied_sources = set()
    copied_count = 0

    for folder, imgs in folders:
        resolved_imgs = [str(p.resolve()) for p in imgs]

        marked_indexes = [
            idx for idx, img_key in enumerate(resolved_imgs) if img_key in marked_paths
        ]

        if not marked_indexes:
            continue

        target_folder = unique_folder_name(export_dir, folder.name)
        target_folder.mkdir(parents=True, exist_ok=True)

        for idx in marked_indexes:
            start = max(0, idx - context_frames)
            end = min(len(imgs), idx + context_frames + 1)

            for context_idx in range(start, end):
                src = imgs[context_idx]
                src_key = str(src.resolve())

                if src_key in copied_sources:
                    continue

                if src_key in marked_paths:
                    dst_name = src.stem + '_MARKED' + src.suffix
                else:
                    dst_name = src.name

                dst = target_folder / dst_name

                if dst.exists():
                    duplicate_folder = unique_folder_name(target_folder, '_duplicates')
                    duplicate_folder.mkdir(parents=True, exist_ok=True)
                    dst = duplicate_folder / dst_name

                shutil.copy2(src, dst)
                copied_sources.add(src_key)
                copied_count += 1

    if copied_count == 0:
        shutil.rmtree(export_dir)
        print(
            'No marked images from selected folders were copied. Empty export folder removed.'
        )
        return None

    print(f'Copied {copied_count} images with context to: {export_dir}')
    return export_dir


def main():
    args = parse_args()

    if args.root is None:
        print()
        print('Frame Flag — select the folder containing your camera images.')
        print('(A Finder dialog will open now.)')
        print()
        chosen_root = choose_image_root_with_finder()

        if chosen_root is None:
            print('No image root folder selected.', file=sys.stderr)
            return 1

        args.root = chosen_root

    if not args.root.is_dir():
        print(f'Image root does not exist: {args.root}', file=sys.stderr)
        return 1

    if len(args.mark_key) != 1:
        print('--mark-key must be a single character', file=sys.stderr)
        return 1

    if args.context_frames < 0:
        print('--context-frames must be 0 or greater', file=sys.stderr)
        return 1

    folders = list(playable_folders(args.root))

    if args.list:
        for folder, imgs in folders:
            print(f'{len(imgs):6d}  {folder}')
        print('List complete.')
        return 0

    if not folders:
        print(f'No image folders found under: {args.root}', file=sys.stderr)
        return 1

    print()
    print('═' * 60)
    print('  Frame Flag — macOS')
    print('═' * 60)
    print('  Browse camera images and mark frames that may contain')
    print('  an insect. When you quit, marked frames (plus context')
    print('  frames before and after each one) are copied to a')
    print('  folder you choose — without touching the originals.')
    print()
    print(f'  Image root   : {args.root}')
    print(f'  Folders found: {len(folders)}')
    print(f'  Context frames: {args.context_frames} before and after each marked frame')
    print()
    print('  Controls:')
    print(f'    {args.mark_key}         mark current frame')
    print('    u         unmark current frame')
    print('    space/h   play / pause')
    print('    a / ←    previous frame')
    print('    d / →    next frame')
    print('    n         next camera folder')
    print('    b         previous camera folder')
    print('    Esc       quit  (export dialog opens if anything was marked)')
    print('═' * 60)
    print()

    flag_file = args.flag_file.resolve()
    flags = load_flags(flag_file)

    # Only images marked during this run will be exported.
    session_marked = set()

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
                session_marked,
                start_idx=start_idx,
            )

            folder_positions[str(folder.resolve())] = last_idx

            if result == 'quit':
                break
            elif result == 'prev_folder':
                folder_idx = max(0, folder_idx - 1)
            else:
                folder_idx += 1

    finally:
        cv2.destroyAllWindows()
        save_flags(flag_file, flags)

    # Only ask for an export folder if something was actually marked this session.
    # The Finder dialog appears here — after browsing — not before.
    if (
        session_marked
        and args.export_dir == Path.home() / 'Desktop' / 'pollinator_flagged_frames'
    ):
        print(
            f'\n{len(session_marked)} frame(s) marked. Choose a folder to copy them to...'
        )
        chosen_export_dir = choose_export_folder_with_finder()
        if chosen_export_dir is None:
            print(f'No folder selected. Using default: {args.export_dir}')
        else:
            args.export_dir = chosen_export_dir

    export_dir = export_marked_images_with_context(
        folders,
        session_marked,
        args.export_dir,
        args.root,
        export_name=args.export_name,
        context_frames=args.context_frames,
    )

    print(f'Done. Mark file: {flag_file}')

    if export_dir is not None:
        print(f'Copied images folder: {export_dir}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

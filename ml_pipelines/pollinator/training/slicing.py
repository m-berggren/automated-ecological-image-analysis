"""
Tile-based dataset preprocessing for small-object detection.

Source images can be much larger than YOLO's training imgsz. Naive
downscaling shrinks small objects below the detector's effective receptive
field. Slicing source images into overlapping tiles preserves native-
resolution pixel detail while keeping per-sample size small, so YOLO sees
each pollinator at its real pixel scale.

Use `slice_dataset` to turn a YOLO-format root (images/{split}/ +
labels/{split}/) into a sliced dataset at `output_root` with the same
shape. Train YOLO against the sliced root as usual.

Tile config:
  tile_size:        pixels per tile edge (square tiles). Default 640.
  overlap:          fraction of overlap between adjacent tiles. Default 0.2.
                    Higher overlap reduces edge-clipped-bbox loss but
                    multiplies tile count.
  min_area:         clipped bbox kept only if remaining area is at least
                    min_area * original area. 0.1 keeps boundary-clipped
                    insects; 0.3 drops them (cleaner edges, fewer samples).
  keep_empty_tiles: how many label-free tiles to keep as negatives.
                    - False or 0: drop all empties (training sees only
                      positives; the model never learns "no insect here")
                    - True: keep every empty tile (typically 20-30x more
                      empties than positives at this tile size; swamps
                      gradient and explodes disk)
                    - int >= 1: keep up to N empties per labeled tile
                      (negative:positive ratio). 2-3 is a sane default.
                    - float in (0, 1]: keep this fraction of all empties.
                    - dict mapping split -> any of the above. Missing
                      splits default to False. Use this to balance train
                      tightly while leaving the test split untouched.
                    Empties are sampled deterministically with `seed`.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional, Union

from PIL import Image

logger = logging.getLogger(__name__)


def _tile_origins(extent: int, tile_size: int, overlap: float) -> list:
    """Origins along one axis. Last tile is right-aligned with the edge so
    we never produce a partial tile."""
    if extent <= tile_size:
        return [0]
    stride = max(1, int(tile_size * (1.0 - overlap)))
    starts = list(range(0, extent - tile_size, stride))
    if not starts or starts[-1] != extent - tile_size:
        starts.append(extent - tile_size)
    return starts


def _parse_yolo_line(line: str, img_w: int, img_h: int) -> Optional[tuple]:
    """Parse a YOLO label line into (class, x1, y1, x2, y2) pixel coords."""
    parts = line.strip().split()
    if not parts:
        return None
    try:
        cls = int(parts[0])
        cx = float(parts[1]) * img_w
        cy = float(parts[2]) * img_h
        w = float(parts[3]) * img_w
        h = float(parts[4]) * img_h
    except (ValueError, IndexError):
        return None
    return cls, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def _clip_to_tile(box: tuple, tile: tuple, min_area: float) -> Optional[tuple]:
    """Clip a (cls, x1, y1, x2, y2) bbox to the tile (tx1, ty1, tx2, ty2).

    Returns the clipped bbox in tile-local pixel coords, or None if the
    surviving area is below min_area * original area.
    """
    cls, x1, y1, x2, y2 = box
    tx1, ty1, tx2, ty2 = tile

    cx1, cy1 = max(x1, tx1), max(y1, ty1)
    cx2, cy2 = min(x2, tx2), min(y2, ty2)
    if cx2 <= cx1 or cy2 <= cy1:
        return None

    orig_area = (x2 - x1) * (y2 - y1)
    new_area = (cx2 - cx1) * (cy2 - cy1)
    if orig_area > 0 and new_area / orig_area < min_area:
        return None

    return cls, cx1 - tx1, cy1 - ty1, cx2 - tx1, cy2 - ty1


def _to_yolo_line(
    cls: int, x1: float, y1: float, x2: float, y2: float, w: int, h: int
) -> str:
    cx = (x1 + x2) / 2 / w
    cy = (y1 + y2) / 2 / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    return f'{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}'


def _resolve_target_empties(
    keep_empty_tiles: Union[bool, int, float], n_positive: int, n_empty: int
) -> int:
    """Map the tri-state keep_empty_tiles to a concrete target count.

    bool is checked before int because bool is a subclass of int in Python;
    without this, True/False would silently route to the int branch.
    """
    if isinstance(keep_empty_tiles, bool):
        return n_empty if keep_empty_tiles else 0
    if isinstance(keep_empty_tiles, int):
        if keep_empty_tiles < 0:
            raise ValueError('keep_empty_tiles int must be >= 0')
        return min(n_empty, n_positive * keep_empty_tiles)
    if isinstance(keep_empty_tiles, float):
        if not 0.0 <= keep_empty_tiles <= 1.0:
            raise ValueError('keep_empty_tiles float must be in [0, 1]')
        return int(round(n_empty * keep_empty_tiles))
    raise TypeError(
        f'keep_empty_tiles must be bool, int, or float; got {type(keep_empty_tiles).__name__}'
    )


def slice_dataset(
    dataset_root: str,
    output_root: str,
    tile_size: int = 640,
    overlap: float = 0.2,
    min_area: float = 0.1,
    splits: tuple = ('train', 'val', 'test'),
    keep_empty_tiles: Union[bool, int, float, dict] = False,
    seed: int = 42,
    jpeg_quality: int = 90,
) -> dict:
    """Slice a YOLO-format dataset into overlapping tiles.

    Empty tiles (no surviving boxes after clipping) are sampled according
    to `keep_empty_tiles`; see module docstring for the five accepted
    shapes. Sampling is deterministic for a given `seed`.

    Returns per-split counts: {split: {source_images, tiles, labeled_tiles,
    empties_total, empties_kept}}.
    """
    src = Path(dataset_root)
    dst = Path(output_root)
    stats: dict = {}

    for split in splits:
        src_img_dir = src / 'images' / split
        src_lbl_dir = src / 'labels' / split
        if not src_img_dir.exists():
            continue

        dst_img_dir = dst / 'images' / split
        dst_lbl_dir = dst / 'labels' / split
        dst_img_dir.mkdir(parents=True, exist_ok=True)
        dst_lbl_dir.mkdir(parents=True, exist_ok=True)

        # Pass 1: enumerate every tile candidate per source image. Store
        # (x0, y0, clipped_boxes) so we can decide what to write without
        # re-parsing labels.
        candidates: dict = {}  # img_path -> list[(x0, y0, clipped)]
        n_source = 0
        n_positive = 0
        n_empty = 0

        for img_path in sorted(src_img_dir.iterdir()):
            if img_path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                continue
            n_source += 1

            try:
                with Image.open(img_path) as img:
                    img.load()
                    width, height = img.size
            except Exception as e:
                logger.warning(f'failed to open {img_path.name}: {e}')
                continue

            label_path = src_lbl_dir / f'{img_path.stem}.txt'
            boxes: list = []
            if label_path.exists():
                for line in label_path.read_text().splitlines():
                    b = _parse_yolo_line(line, width, height)
                    if b is not None:
                        boxes.append(b)

            xs = _tile_origins(width, tile_size, overlap)
            ys = _tile_origins(height, tile_size, overlap)
            per_image: list = []
            for y0 in ys:
                for x0 in xs:
                    tile = (x0, y0, x0 + tile_size, y0 + tile_size)
                    clipped = [
                        cb
                        for cb in (_clip_to_tile(b, tile, min_area) for b in boxes)
                        if cb is not None
                    ]
                    per_image.append((x0, y0, clipped))
                    if clipped:
                        n_positive += 1
                    else:
                        n_empty += 1
            if per_image:
                candidates[img_path] = per_image

        # Resolve the empty-tile budget for this split. A dict lets the
        # caller balance train/val tightly while leaving test untouched.
        if isinstance(keep_empty_tiles, dict):
            keep_for_split = keep_empty_tiles.get(split, False)
        else:
            keep_for_split = keep_empty_tiles
        target_empties = _resolve_target_empties(keep_for_split, n_positive, n_empty)

        keep_empty_set: set = set()
        if target_empties > 0 and target_empties < n_empty:
            all_empties = [
                (img_path, x0, y0)
                for img_path, items in candidates.items()
                for x0, y0, clipped in items
                if not clipped
            ]
            rng = random.Random(seed)
            keep_empty_set = set(rng.sample(all_empties, target_empties))

        # Pass 2: open each source once and write the selected tiles.
        n_tiles = 0
        n_labeled = 0
        for img_path, items in candidates.items():
            try:
                with Image.open(img_path) as img:
                    img.load()
                    for x0, y0, clipped in items:
                        if not clipped:
                            if target_empties >= n_empty:
                                pass  # keep every empty
                            elif target_empties == 0:
                                continue
                            elif (img_path, x0, y0) not in keep_empty_set:
                                continue

                        stem = f'{img_path.stem}_t{y0}_{x0}'
                        tile_box = (x0, y0, x0 + tile_size, y0 + tile_size)
                        try:
                            tile_img = img.crop(tile_box).convert('RGB')
                            tile_img.save(
                                dst_img_dir / f'{stem}.jpg',
                                'JPEG',
                                quality=jpeg_quality,
                            )
                        except Exception as e:
                            logger.warning(f'failed to write tile {stem}: {e}')
                            continue

                        label_path = dst_lbl_dir / f'{stem}.txt'
                        if clipped:
                            lines = [
                                _to_yolo_line(*c, w=tile_size, h=tile_size)
                                for c in clipped
                            ]
                            label_path.write_text('\n'.join(lines) + '\n')
                            n_labeled += 1
                        else:
                            # Empty label file is the YOLO convention for
                            # an explicit background sample. Use 0 bytes so
                            # downstream "is this empty?" checks based on
                            # file size are unambiguous.
                            label_path.write_text('')

                        n_tiles += 1
            except Exception as e:
                logger.warning(f'failed during tiling of {img_path.name}: {e}')

        stats[split] = {
            'source_images': n_source,
            'tiles': n_tiles,
            'labeled_tiles': n_labeled,
            'empties_total': n_empty,
            'empties_kept': n_tiles - n_labeled,
        }
        logger.info(
            f'sliced {split}: {n_source} source -> {n_tiles} tiles '
            f'({n_labeled} labeled, {n_tiles - n_labeled} of {n_empty} empties kept)'
        )

    return stats

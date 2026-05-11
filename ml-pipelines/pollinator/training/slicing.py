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
                    min_area * original area. Avoids tiny slivers that
                    confuse training.
  keep_empty_tiles: when False (default) drop tiles that contain no labels
                    after clipping. Set True to include all tiles as
                    negative samples (helps reduce false positives but
                    slows training and biases away from rare classes).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

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


def slice_dataset(
    dataset_root: str,
    output_root: str,
    tile_size: int = 640,
    overlap: float = 0.2,
    min_area: float = 0.3,
    splits: tuple = ('train', 'val', 'test'),
    keep_empty_tiles: bool = False,
    jpeg_quality: int = 90,
) -> dict:
    """Slice a YOLO-format dataset into overlapping tiles.

    Returns per-split counts: {split: {source_images, tiles, labeled_tiles}}.
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

        n_source = 0
        n_tiles = 0
        n_labeled = 0

        for img_path in sorted(src_img_dir.iterdir()):
            if img_path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                continue
            n_source += 1

            try:
                with Image.open(img_path) as img:
                    img.load()
                    width, height = img.size

                    label_path = src_lbl_dir / f'{img_path.stem}.txt'
                    boxes: list = []
                    if label_path.exists():
                        for line in label_path.read_text().splitlines():
                            b = _parse_yolo_line(line, width, height)
                            if b is not None:
                                boxes.append(b)

                    xs = _tile_origins(width, tile_size, overlap)
                    ys = _tile_origins(height, tile_size, overlap)
                    for y0 in ys:
                        for x0 in xs:
                            tile = (x0, y0, x0 + tile_size, y0 + tile_size)
                            clipped = [
                                cb
                                for cb in (
                                    _clip_to_tile(b, tile, min_area) for b in boxes
                                )
                                if cb is not None
                            ]

                            if not clipped and not keep_empty_tiles:
                                continue

                            stem = f'{img_path.stem}_t{y0}_{x0}'
                            tile_img = img.crop(tile).convert('RGB')
                            tile_img.save(
                                dst_img_dir / f'{stem}.jpg',
                                'JPEG',
                                quality=jpeg_quality,
                            )

                            lines = [
                                _to_yolo_line(*c, w=tile_size, h=tile_size)
                                for c in clipped
                            ]
                            (dst_lbl_dir / f'{stem}.txt').write_text(
                                '\n'.join(lines) + '\n'
                            )

                            n_tiles += 1
                            if clipped:
                                n_labeled += 1
            except Exception as e:
                logger.warning(f'slicing failed on {img_path.name}: {e}')

        stats[split] = {
            'source_images': n_source,
            'tiles': n_tiles,
            'labeled_tiles': n_labeled,
        }
        logger.info(
            f'sliced {split}: {n_source} source -> {n_tiles} tiles '
            f'({n_labeled} with labels)'
        )

    return stats

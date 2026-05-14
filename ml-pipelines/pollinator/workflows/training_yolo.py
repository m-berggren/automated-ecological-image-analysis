"""End-to-end YOLO training workflow: optional tile slicing + train.

Composes pollinator.training.slicing (data prep) with pollinator.training.train_yolo
(the trainer) so callers only need one entry point. When use_tiles is True
the source dataset is sliced into <dataset_root>_tiled at tile_size, and the
trainer runs against that sliced dataset with img_size aligned to tile_size.

Both the Django backend (apps/pollinator/training.py) and the Colab notebook
import retrain_yolo from here, so the slice + train composition lives in one
place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..training.slicing import slice_dataset
from ..training.train_yolo import train_yolo


def retrain_yolo(
    dataset_root: str,
    output_dir: str,
    use_tiles: bool = True,
    tile_size: int = 640,
    overlap: float = 0.2,
    min_area: float = 0.3,
    keep_empty_tiles: bool = False,
    img_size: Optional[int] = None,
    **train_kwargs,
) -> dict:
    """Slice the source dataset if requested, then train YOLO on it.

    Args:
        dataset_root:     Source YOLO-format dataset (images/{train,val}, labels/{train,val}).
        output_dir:       Where ultralytics writes runs.
        use_tiles:        Slice source into overlapping tiles before training.
        tile_size:        Tile edge length in pixels.
        overlap:          Fractional overlap between adjacent tiles.
        min_area:         Minimum surviving area for a clipped bbox (drops slivers).
        keep_empty_tiles: When True, keep tiles with no labels as negatives.
        img_size:         YOLO input size. Defaults to tile_size when slicing,
                          else falls through to train_yolo's own default.
        **train_kwargs:   Forwarded to pollinator.training.train_yolo.train_yolo.

    Returns:
        train_yolo's result dict (weights paths, metrics, etc.).
    """
    if use_tiles:
        src = Path(dataset_root)
        sliced = src.parent / f'{src.name}_tiled'
        slice_dataset(
            dataset_root=str(src),
            output_root=str(sliced),
            tile_size=tile_size,
            overlap=overlap,
            min_area=min_area,
            keep_empty_tiles=keep_empty_tiles,
        )
        dataset_root = str(sliced)
        if img_size is None:
            img_size = tile_size

    if img_size is not None:
        train_kwargs.setdefault('img_size', img_size)

    return train_yolo(
        dataset_root=dataset_root,
        output_dir=output_dir,
        **train_kwargs,
    )

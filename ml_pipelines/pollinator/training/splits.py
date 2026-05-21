"""
Plot-aware train/val/test re-splitting for YOLO-format image datasets.

The default split produced by CVAT-export staging (or by a random image-level
shuffle) does not respect camera-plot structure: images from the same plot
can land in both train and test, and plots with more annotated images
contribute disproportionately to whichever split the random shuffle happens
to favour. This module's re-splitter groups images by plot and partitions
each plot independently into train/val/test, so every plot is represented in
every split in proportion to its size.

Filename conventions:
    By default plot names are parsed as the leading `<Plot>__<rest>` segment
    produced by `flatten-jpg.sh`. Pass `plot_from_stem` to override (e.g. the
    crop-based pipeline uses an `hdd_X_..._plotN_...` layout parsed in
    `sampling.parse_plot_key`).

Idempotency:
    A `.stratified_for` marker is written under `dataset_root` capturing the
    split parameters. Re-running with the same `marker_id` is a no-op.
"""

from __future__ import annotations

import json
import logging
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _default_plot_from_stem(stem: str) -> str:
    """Extract the plot name from `<Plot>__<rest>` (the convention produced
    by `flatten-jpg.sh`). Returns 'unknown' for stems without the marker."""
    return stem.split('__', 1)[0] if '__' in stem else 'unknown'


def restratify_by_plot(
    dataset_root: str,
    val_frac: float = 0.20,
    test_frac: float = 0.10,
    seed: int = 42,
    plot_from_stem: Optional[Callable[[str], str]] = None,
    marker_id: Optional[str] = None,
    splits: tuple = ('train', 'val', 'test'),
    image_suffixes: tuple = ('.jpg', '.jpeg', '.png'),
    label_suffix: str = '.txt',
) -> dict:
    """Re-split images and labels by plot so each plot contributes proportionally
    to train/val/test.

    Args:
        dataset_root:    YOLO-format dataset root with images/{split}/ and
                         labels/{split}/ subdirectories.
        val_frac:        Fraction of each plot's images to assign to val.
        test_frac:       Fraction of each plot's images to assign to test.
        seed:            Seed for deterministic per-plot shuffling.
        plot_from_stem:  Callable mapping an image stem to a plot name.
                         Defaults to `<Plot>__<rest>` parsing.
        marker_id:       String captured in `.stratified_for` for idempotency.
                         Defaults to a stable hash of the split parameters.
        splits:          Which split dirs to scan for source images.
        image_suffixes:  Image file extensions to consider.
        label_suffix:    Label file extension paired with each image.

    Returns:
        Per-plot counts dict: {plot_name: {total, train, val, test}}.
        The dict is also written to `dataset_root/stratified_split_counts.json`.

    Tiny plots (<10 images) are not partitioned and stay entirely in train so
    they still contribute to the model rather than producing single-image
    val/test splits with zero statistical power.
    """
    if not 0.0 <= val_frac < 1.0:
        raise ValueError(f'val_frac must be in [0, 1), got {val_frac}')
    if not 0.0 <= test_frac < 1.0:
        raise ValueError(f'test_frac must be in [0, 1), got {test_frac}')
    if val_frac + test_frac >= 1.0:
        raise ValueError(
            f'val_frac + test_frac must be < 1.0, got {val_frac + test_frac}'
        )

    plot_from_stem = plot_from_stem or _default_plot_from_stem
    marker_id = marker_id or (
        f'val={val_frac}|test={test_frac}|seed={seed}'
    )

    root = Path(dataset_root)
    marker = root / '.stratified_for'
    if marker.exists() and marker.read_text() == marker_id:
        logger.info(f'dataset already stratified for {marker_id}; skipping')
        counts_path = root / 'stratified_split_counts.json'
        if counts_path.exists():
            return json.loads(counts_path.read_text())
        return {}

    by_plot: dict = defaultdict(list)
    for split in splits:
        idir = root / 'images' / split
        if not idir.exists():
            continue
        for img in idir.iterdir():
            if img.suffix.lower() not in image_suffixes:
                continue
            plot = plot_from_stem(img.stem)
            by_plot[plot].append((split, img))

    if not by_plot:
        logger.warning(f'no images found under {root}/images/{splits}')
        return {}

    rng = random.Random(seed)
    per_plot_counts: dict = {}
    moves = 0

    for plot, items in sorted(by_plot.items()):
        rng.shuffle(items)
        n = len(items)
        if n < 10:
            # Tiny plot: keep all in train rather than producing useless
            # singleton val/test splits.
            n_test = 0
            n_val = 0
        else:
            n_test = max(1, int(n * test_frac))
            n_val = max(1, int(n * val_frac))
        n_train = n - n_test - n_val
        per_plot_counts[plot] = {
            'total': n, 'train': n_train, 'val': n_val, 'test': n_test,
        }

        for i, (src_split, img) in enumerate(items):
            if i < n_test:
                target_split = 'test'
            elif i < n_test + n_val:
                target_split = 'val'
            else:
                target_split = 'train'
            if src_split == target_split:
                continue
            for kind, ext in (('images', img.suffix), ('labels', label_suffix)):
                src = root / kind / src_split / (img.stem + ext)
                dst_dir = root / kind / target_split
                dst = dst_dir / src.name
                if src.exists():
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    if kind == 'images':
                        moves += 1

    logger.info(f'plot-stratified: moved {moves} images across splits')
    for plot, c in per_plot_counts.items():
        logger.info(
            f'  {plot}: {c["total"]} total -> '
            f'train={c["train"]}, val={c["val"]}, test={c["test"]}'
        )

    (root / 'stratified_split_counts.json').write_text(
        json.dumps(per_plot_counts, indent=2)
    )
    marker.write_text(marker_id)
    return per_plot_counts


def plot_holdout(
    dataset_root: str,
    test_plots: list,
    val_frac: float = 0.15,
    seed: int = 42,
    plot_from_stem: Optional[Callable[[str], str]] = None,
    marker_id: Optional[str] = None,
    splits: tuple = ('train', 'val', 'test'),
    image_suffixes: tuple = ('.jpg', '.jpeg', '.png'),
    label_suffix: str = '.txt',
) -> dict:
    """Hold entire plots out as the test set. All images from `test_plots`
    move to test; images from other plots are split val / train by val_frac.

    Gold-standard generalisation test: the model has never seen any image
    from the held-out plots, so test recall reflects transfer to unseen
    camera plots rather than to unseen frames from familiar plots.

    Args:
        test_plots: List of plot names (as returned by plot_from_stem) to
                    move entirely into test.
        val_frac:   Fraction of non-held-out images to use for val.
        Other args: see `restratify_by_plot`.

    Returns:
        Per-plot counts dict.
    """
    if not test_plots:
        raise ValueError('test_plots must contain at least one plot name')
    if not 0.0 <= val_frac < 1.0:
        raise ValueError(f'val_frac must be in [0, 1), got {val_frac}')

    plot_from_stem = plot_from_stem or _default_plot_from_stem
    test_plots_set = set(test_plots)
    marker_id = marker_id or (
        f"holdout={','.join(sorted(test_plots_set))}|val={val_frac}|seed={seed}"
    )

    root = Path(dataset_root)
    marker = root / '.holdout_for'
    if marker.exists() and marker.read_text() == marker_id:
        logger.info(f'dataset already split (holdout) for {marker_id}; skipping')
        counts_path = root / 'holdout_split_counts.json'
        if counts_path.exists():
            return json.loads(counts_path.read_text())
        return {}

    by_plot: dict = defaultdict(list)
    for split in splits:
        idir = root / 'images' / split
        if not idir.exists():
            continue
        for img in idir.iterdir():
            if img.suffix.lower() not in image_suffixes:
                continue
            plot = plot_from_stem(img.stem)
            by_plot[plot].append((split, img))

    if not by_plot:
        logger.warning(f'no images found under {root}/images/{splits}')
        return {}

    rng = random.Random(seed)
    per_plot_counts: dict = {}
    moves = 0

    for plot, items in sorted(by_plot.items()):
        n = len(items)
        if plot in test_plots_set:
            per_plot_counts[plot] = {
                'total': n, 'train': 0, 'val': 0, 'test': n,
            }
            for src_split, img in items:
                if src_split == 'test':
                    continue
                for kind, ext in (('images', img.suffix), ('labels', label_suffix)):
                    src = root / kind / src_split / (img.stem + ext)
                    dst_dir = root / kind / 'test'
                    if src.exists():
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dst_dir / src.name))
                        if kind == 'images':
                            moves += 1
            continue

        rng.shuffle(items)
        n_val = max(1, int(n * val_frac)) if n >= 5 else 0
        n_train = n - n_val
        per_plot_counts[plot] = {
            'total': n, 'train': n_train, 'val': n_val, 'test': 0,
        }
        for i, (src_split, img) in enumerate(items):
            target_split = 'val' if i < n_val else 'train'
            if src_split == target_split:
                continue
            for kind, ext in (('images', img.suffix), ('labels', label_suffix)):
                src = root / kind / src_split / (img.stem + ext)
                dst_dir = root / kind / target_split
                if src.exists():
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst_dir / src.name))
                    if kind == 'images':
                        moves += 1

    logger.info(
        f'plot-holdout (test={sorted(test_plots_set)}): moved {moves} images'
    )
    for plot, c in per_plot_counts.items():
        held = ' [HELD OUT]' if plot in test_plots_set else ''
        logger.info(
            f'  {plot}: {c["total"]} total -> '
            f'train={c["train"]}, val={c["val"]}, test={c["test"]}{held}'
        )

    (root / 'holdout_split_counts.json').write_text(
        json.dumps(per_plot_counts, indent=2)
    )
    marker.write_text(marker_id)
    return per_plot_counts

"""
training/sampling.py
=====================
Per-plot balanced background sampling for the binary classifier.

Background crops are grouped by (hdd, site, species, plot) parsed from the
filename. Each group gets an equal quota so no single camera plot dominates
the training data.
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def parse_plot_key(path: Path) -> str:
    """
    Extract (hdd, site, species, plot) key from a crop filename.

    Handles two formats:
        hdd_1_2025_cg_Vamy_p1_101_WSCT__...
        hdd_2_2025_desert_Asa_p2_20250729_102_WSCT__...

    Returns e.g. 'hdd1_cg_Vamy_p1', or 'unknown' if the filename does not
    match the expected layout.
    """
    parts = path.stem.split('_')
    try:
        if parts[0] == 'hdd' and len(parts) > 6:
            hdd = parts[1]
            site = parts[3]
            species = parts[4]
            plot = parts[5]
            return f'hdd{hdd}_{site}_{species}_{plot}'
    except IndexError:
        pass
    return 'unknown'


def sample_background_balanced(bg_dir: Path, n_total: int, seed: int) -> list:
    """
    Sample n_total background crops evenly across (hdd, site, species, plot)
    groups. Each group gets an equal quota; remainder distributed round-robin.
    """
    all_bg = []
    for ext in ('*.jpg', '*.jpeg', '*.png'):
        all_bg.extend(bg_dir.glob(ext))

    groups = {}
    for p in all_bg:
        key = parse_plot_key(p)
        groups.setdefault(key, []).append(p)

    rng = np.random.default_rng(seed)
    for key in groups:
        rng.shuffle(groups[key])

    n_groups = len(groups)
    if n_groups == 0 or n_total == 0:
        return []

    quota = n_total // n_groups
    remainder = n_total % n_groups

    logger.info(
        f'Background sampling: {n_groups} groups, quota={quota}/group, remainder={remainder}'
    )
    for key, imgs in sorted(groups.items()):
        logger.info(f'  {key:30}: {len(imgs):>5} available')

    sampled = []
    keys = sorted(groups.keys())
    for i, key in enumerate(keys):
        imgs = groups[key]
        take = quota + (1 if i < remainder else 0)
        take = min(take, len(imgs))
        sampled.extend(imgs[:take])

    rng.shuffle(sampled)
    logger.info(f'Sampled {len(sampled)} background crops (target {n_total})')
    return sampled

"""Seed species dataset bootstrap service."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def _base_data() -> Path:
    from django.conf import settings
    return settings.BASE_DIR / 'data' / 'seed'


def bootstrap_species_dataset(species: str) -> Path:
    """Create the folder structure and YAML config for a new seed species.

    Creates:
        root/data/seed/<species>_model/
        root/data/seed/<species>_model/train_sliced/
        root/data/seed/<species>_model/val/images/
        root/data/seed/<species>_model/<species>.yaml

    Returns the path to the YAML file.
    """
    BASE_DATA = _base_data()
    species = species.lower()
    species_dir = BASE_DATA / f'{species}_model'

    # Always create dirs if missing
    (species_dir / 'train_sliced').mkdir(parents=True, exist_ok=True)
    (species_dir / 'val' / 'images').mkdir(parents=True, exist_ok=True)
    (species_dir / 'val' / 'labels').mkdir(parents=True, exist_ok=True)

    # Always write YAML (overwrites if exists, fixing stale relative paths)
    yaml_path = species_dir / f'{species}.yaml'
    yaml_path.write_text(
        f'path: {species_dir}\n'
        f'train: train_sliced\n'
        f'val: val/images\n'
        f'\n'
        f'names:\n'
        f'  0: {species}\n'
    )

    logger.info(f'Dataset folder ready at {species_dir}')
    return yaml_path


def species_dataset_exists(species: str) -> bool:
    """Check if a species dataset folder already exists."""
    return (_base_data() / f'{species.lower()}_model').exists()
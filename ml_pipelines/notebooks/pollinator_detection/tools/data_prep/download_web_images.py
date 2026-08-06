#!/usr/bin/env python3
"""
download_web_images.py — Download iNaturalist reference images for classifier training.

Each run creates a new timestamped batch folder:
    data/training/web_images/batch_YYYYMMDD_HHMMSS/{class}/

Dedup is automatic: before downloading any photo, ALL existing batch folders are
scanned for photo IDs already on disk.  Re-running or starting a new batch will
never download an image you already have.

When training, choose which batches to use via WEB_BATCHES in the training notebook:
    WEB_BATCHES = []                              # all batches (default)
    WEB_BATCHES = ['batch_20260529_143000']       # only this batch
    WEB_BATCHES = ['batch_20260101', 'batch_...'] # specific batches

Requires:  pip install requests
"""

import requests
from datetime import datetime
from pathlib import Path

# ── Output root ───────────────────────────────────────────────────────────
# parents[0]=data_prep  parents[1]=tools  parents[2]=pollinator_detection root
WEB_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'training' / 'web_images'

# ── iNaturalist place IDs ─────────────────────────────────────────────────
SWEDEN = 7599
NORWAY = 7016

# ── iNaturalist taxon IDs ─────────────────────────────────────────────────
# Look up / verify at: https://www.inaturalist.org/taxa/<id>
#
# Class        Taxon                    iNaturalist ID
# ----------   ----------------------   ---------------
# bumblebee    Bombus (genus)           52775
# fly          Diptera (order)          47822
# butterfly    Lepidoptera (order)      47157
# other        Coleoptera (order)       47208   ← beetles
# other        Hymenoptera (order)      47201   ← wasps, ants (excl. Bombus)
# other        Hemiptera (order)        47744   ← true bugs

TAXON_BOMBUS = 52775  # Bombus spp. — bumblebees
TAXON_DIPTERA = 47822  # Diptera — flies
TAXON_LEPIDOPTERA = 47157  # Lepidoptera — butterflies & moths
TAXON_COLEOPTERA = 47208  # Coleoptera — beetles
TAXON_HYMENOPTERA = 47201  # Hymenoptera — wasps, ants, other bees
TAXON_HEMIPTERA = 47744  # Hemiptera — true bugs


# ── Helpers ───────────────────────────────────────────────────────────────


def _collect_ids_in_dir(directory: Path) -> set:
    """Collect photo IDs (photo_<id>.jpg) from one class folder."""
    if not directory.exists():
        return set()
    return {p.stem.split('_', 1)[-1] for p in directory.glob('photo_*.jpg')}


def _all_existing_ids(web_root: Path, class_name: str) -> set:
    """Scan every batch_*/ folder under web_root for already-downloaded photo IDs.

    Only files named photo_<id>.jpg are recognised.  The original batch_initial/
    files use the old {taxon}_{place}_{counter}.jpg scheme and contain no photo ID,
    so they are invisible to this check.  A small number of those images may be
    re-downloaded into a future batch under their correct photo_<id>.jpg name.
    This is a minor inefficiency (disk space) but not a correctness problem —
    use WEB_BATCHES in the training notebooks to control which batches are used.
    """
    ids: set = set()
    for batch_dir in web_root.glob('batch_*/'):
        ids |= _collect_ids_in_dir(batch_dir / class_name)
    # Also handle legacy flat layout (no batch_* sub-folders)
    ids |= _collect_ids_in_dir(web_root / class_name)
    return ids


def download_inaturalist(
    taxon_id,
    save_dir: Path,
    class_name: str,
    web_root: Path,
    n: int = 200,
    place_id: int = SWEDEN,
):
    """Download up to n research-grade photos from iNaturalist.

    save_dir   — destination class folder inside the new batch (created if needed)
    class_name — used to scan all other batch folders for existing IDs
    web_root   — root of web_images/ so all prior batches can be checked
    """
    save_dir.mkdir(parents=True, exist_ok=True)

    # Skip any photo ID already present in ANY batch folder
    existing_ids = _all_existing_ids(web_root, class_name)

    url = 'https://api.inaturalist.org/v1/observations'
    downloaded = 0
    skipped = 0
    page = 1

    while downloaded < n:
        params = {
            'taxon_id': taxon_id,
            'place_id': place_id,
            'photos': True,
            'per_page': 200,
            'page': page,
            'quality_grade': 'research',
        }
        try:
            resp = requests.get(url, params=params, timeout=30).json()
        except Exception as e:
            print(f'  Request failed: {e}')
            break

        results = resp.get('results', [])
        if not results:
            print(f'  No more results at page {page}')
            break

        for obs in results:
            if downloaded >= n:
                break
            photos = obs.get('photos', [])
            if not photos:
                continue
            photo = photos[0]
            photo_id = str(photo.get('id', ''))
            url_img = photo.get('url', '').replace('square', 'medium')
            if not url_img or not photo_id:
                continue
            if photo_id in existing_ids:
                skipped += 1
                continue
            try:
                img_data = requests.get(url_img, timeout=10).content
                (save_dir / f'photo_{photo_id}.jpg').write_bytes(img_data)
                existing_ids.add(photo_id)
                downloaded += 1
            except Exception as e:
                print(f'  Failed photo {photo_id}: {e}')

        print(f'  Page {page}: new={downloaded}  skipped(already have)={skipped}')
        page += 1

    print(f'  Done: {downloaded} new images → {save_dir}\n')


# ── Create this run's batch folder ────────────────────────────────────────
BATCH = WEB_ROOT / f'batch_{datetime.now().strftime("%Y%m%d_%H%M%S")}'

print()
print('═' * 60)
print('  Download Web Images — iNaturalist')
print('═' * 60)
print(f'  Batch   : {BATCH.name}')
print(f'  Root    : {WEB_ROOT}')
print()
print('  Dedup: all existing batch folders are scanned — images')
print('  already downloaded in any prior run are skipped.')
print()
print('  To choose which batches to use for training, set WEB_BATCHES')
print('  in the training notebook ([] = all batches).')
print('═' * 60)
print()


def _dest(cls):
    return BATCH / cls


# ── Bumblebee (Bombus spp.) ───────────────────────────────────────────────
print('── bumblebee ─────────────────────────────────────────────')
download_inaturalist(
    TAXON_BOMBUS, _dest('bumblebee'), 'bumblebee', WEB_ROOT, n=1000, place_id=SWEDEN
)
download_inaturalist(
    TAXON_BOMBUS, _dest('bumblebee'), 'bumblebee', WEB_ROOT, n=1000, place_id=NORWAY
)

# ── Fly (Diptera) ─────────────────────────────────────────────────────────
print('── fly ───────────────────────────────────────────────────')
download_inaturalist(
    TAXON_DIPTERA, _dest('fly'), 'fly', WEB_ROOT, n=600, place_id=SWEDEN
)
download_inaturalist(
    TAXON_DIPTERA, _dest('fly'), 'fly', WEB_ROOT, n=600, place_id=NORWAY
)

# ── Butterfly/moth (Lepidoptera) ──────────────────────────────────────────
print('── butterfly ─────────────────────────────────────────────')
download_inaturalist(
    TAXON_LEPIDOPTERA,
    _dest('butterfly'),
    'butterfly',
    WEB_ROOT,
    n=1000,
    place_id=SWEDEN,
)
download_inaturalist(
    TAXON_LEPIDOPTERA,
    _dest('butterfly'),
    'butterfly',
    WEB_ROOT,
    n=1000,
    place_id=NORWAY,
)

# ── Other (beetles + wasps + true bugs) ──────────────────────────────────
# Hymenoptera here = wasps/ants; Bombus is handled separately above (no overlap).
print('── other ─────────────────────────────────────────────────')
download_inaturalist(
    TAXON_COLEOPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=SWEDEN
)
download_inaturalist(
    TAXON_COLEOPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=NORWAY
)
download_inaturalist(
    TAXON_HYMENOPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=SWEDEN
)
download_inaturalist(
    TAXON_HYMENOPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=NORWAY
)
download_inaturalist(
    TAXON_HEMIPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=SWEDEN
)
download_inaturalist(
    TAXON_HEMIPTERA, _dest('other'), 'other', WEB_ROOT, n=500, place_id=NORWAY
)

print('═' * 60)
print(f'  All done.  Batch folder: {BATCH.name}')
print('═' * 60)

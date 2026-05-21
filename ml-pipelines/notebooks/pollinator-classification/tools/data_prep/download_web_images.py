#!/usr/bin/env python3
"""
download_web_images.py — Download iNaturalist reference images for classifier training.

Downloads research-grade insect photos from iNaturalist (Sweden + Norway) into
data/web_images/{class}/.

For the group / 5-class classifier: use all classes as-is.
For the binary classifier: all classes count as 'insect' — set USE_WEB_FOR_BINARY=True
in train_binary_group.ipynb or retrain_cropbased.ipynb.

Edit BASE at the top of this file if your project folder is in a different location.
Edit the n= counts per taxon to change how many images to download.

Requires:  pip install requests
"""

import requests
from pathlib import Path

print()
print('═' * 60)
print('  Download Web Images — iNaturalist')
print('═' * 60)
print('  Downloads research-grade insect photos from iNaturalist')
print('  (Sweden + Norway) for classifier training.')
print()
print('  Classes: bumblebee, fly, butterfly, other')
print('  Output : data/web_images/{class}/')
print()
print('  Group / 5-class classifier : use directly (each class as-is).')
print('  Binary classifier          : all classes count as insect —')
print('    set USE_WEB_FOR_BINARY=True in train_binary_group.ipynb or')
print('    retrain_cropbased.ipynb.')
print('═' * 60)
print()

BASE = "/Users/lianshi/Downloads/bachelor thesis/automated-ecological-image-analysis/ml-pipelines/notebooks/pollinator-classification/data/web_images"

# ── iNaturalist place IDs ──────────────────────────────────────────────────
SWEDEN = 7599
NORWAY = 7016

# ── iNaturalist taxon IDs ──────────────────────────────────────────────────
# Used for the group / 5-class classifiers.
# Also used for the binary classifier insect class when USE_WEB_FOR_BINARY=True.
# Look up or verify at: https://www.inaturalist.org/taxa/<id>
#
# Class        Taxon                    iNaturalist ID
# ----------   ----------------------   ---------------
# bumblebee    Bombus (genus)           52775
# fly          Diptera (order)          47822
# butterfly    Lepidoptera (order)      47157
# other        Coleoptera (order)       47208   ← beetles
# other        Hymenoptera (order)      47201   ← wasps, ants (excl. Bombus)
# other        Hemiptera (order)        47744   ← true bugs

TAXON_BOMBUS       = 52775   # Bombus spp. — bumblebees
TAXON_DIPTERA      = 47822   # Diptera — flies
TAXON_LEPIDOPTERA  = 47157   # Lepidoptera — butterflies & moths
TAXON_COLEOPTERA   = 47208   # Coleoptera — beetles
TAXON_HYMENOPTERA  = 47201   # Hymenoptera — wasps, ants, other bees
TAXON_HEMIPTERA    = 47744   # Hemiptera — true bugs


def download_inaturalist(taxon_id, save_dir, n=200, place_id=SWEDEN):
    """Download up to n research-grade photos from iNaturalist for a given taxon."""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    url        = "https://api.inaturalist.org/v1/observations"
    downloaded = 0
    page       = 1

    while downloaded < n:
        params = {
            "taxon_id":      taxon_id,
            "place_id":      place_id,
            "photos":        True,
            "per_page":      200,
            "page":          page,
            "quality_grade": "research",
        }
        try:
            resp = requests.get(url, params=params, timeout=30).json()
        except Exception as e:
            print(f"Request failed: {e}")
            break

        results = resp.get("results", [])
        if not results:
            print(f"No more results at page {page}")
            break

        for obs in results:
            if downloaded >= n:
                break
            photos = obs.get("photos", [])
            if not photos:
                continue
            photo   = photos[0]
            url_img = photo.get("url", "").replace("square", "medium")
            if not url_img:
                continue
            try:
                img_data = requests.get(url_img, timeout=10).content
                fname    = save_dir / f"{taxon_id}_{place_id}_{downloaded:04d}.jpg"
                fname.write_bytes(img_data)
                downloaded += 1
            except Exception as e:
                print(f"Failed: {e}")

        print(f"  Page {page}: downloaded so far = {downloaded}")
        page += 1

    print(f"Done: {downloaded} images saved to {save_dir}\n")


# ── Bumblebee (Bombus spp.) ────────────────────────────────────────────────
download_inaturalist(TAXON_BOMBUS, f"{BASE}/bumblebee", n=1000, place_id=SWEDEN)
download_inaturalist(TAXON_BOMBUS, f"{BASE}/bumblebee", n=1000, place_id=NORWAY)

# ── Fly (Diptera) ──────────────────────────────────────────────────────────
download_inaturalist(TAXON_DIPTERA, f"{BASE}/fly", n=600, place_id=SWEDEN)
download_inaturalist(TAXON_DIPTERA, f"{BASE}/fly", n=600, place_id=NORWAY)

# ── Butterfly/moth (Lepidoptera) ───────────────────────────────────────────
download_inaturalist(TAXON_LEPIDOPTERA, f"{BASE}/butterfly", n=1000, place_id=SWEDEN)
download_inaturalist(TAXON_LEPIDOPTERA, f"{BASE}/butterfly", n=1000, place_id=NORWAY)

# ── Other ──────────────────────────────────────────────────────────────────
# Note: Hymenoptera includes Bombus, but Bombus is downloaded separately above
# for the bumblebee class.  Hymenoptera here contributes to 'other' (wasps, ants).
download_inaturalist(TAXON_COLEOPTERA,  f"{BASE}/other", n=500, place_id=SWEDEN)
download_inaturalist(TAXON_COLEOPTERA,  f"{BASE}/other", n=500, place_id=NORWAY)
download_inaturalist(TAXON_HYMENOPTERA, f"{BASE}/other", n=500, place_id=SWEDEN)
download_inaturalist(TAXON_HYMENOPTERA, f"{BASE}/other", n=500, place_id=NORWAY)
download_inaturalist(TAXON_HEMIPTERA,   f"{BASE}/other", n=500, place_id=SWEDEN)
download_inaturalist(TAXON_HEMIPTERA,   f"{BASE}/other", n=500, place_id=NORWAY)

import requests
from pathlib import Path

BASE = "/Users/lianshi/Downloads/bachelor thesis/automated-ecological-image-analysis/ml-pipelines/notebooks/pollinator-classification/Insects_images/web_images"

SWEDEN = 7599
NORWAY = 7016

def download_inaturalist(taxon_id, save_dir, n=200, place_id=SWEDEN):
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
            # 每个观测只取第一张
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


# ── Fly (Diptera) ──────────────────────────────────────────────────────────
download_inaturalist(47822, f"{BASE}/fly", n=300, place_id=SWEDEN)
download_inaturalist(47822, f"{BASE}/fly", n=300, place_id=NORWAY)

# ── Butterfly/moth (Lepidoptera) ───────────────────────────────────────────
download_inaturalist(47157, f"{BASE}/butterfly", n=500, place_id=SWEDEN)
download_inaturalist(47157, f"{BASE}/butterfly", n=500, place_id=NORWAY)

# ── Other ──────────────────────────────────────────────────────────────────
download_inaturalist(47208, f"{BASE}/other", n=300, place_id=SWEDEN)  # Coleoptera
download_inaturalist(47208, f"{BASE}/other", n=300, place_id=NORWAY)
download_inaturalist(47201, f"{BASE}/other", n=200, place_id=SWEDEN)  # Hymenoptera
download_inaturalist(47201, f"{BASE}/other", n=200, place_id=NORWAY)
download_inaturalist(47744, f"{BASE}/other", n=150, place_id=SWEDEN)  # Hemiptera
download_inaturalist(47744, f"{BASE}/other", n=150, place_id=NORWAY)
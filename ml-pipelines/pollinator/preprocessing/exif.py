"""
preprocessing/exif.py
======================
EXIF metadata extraction and quality-gate checks (flash skip, foggy-frame skip
via Laplacian variance). Weather is inferred from shutter speed.

EXIF reads are LRU-cached by path so the sort pass and the metadata pass over
the same camera folder do not pay double I/O. Callers must treat returned
dicts as read-only.
"""

from functools import lru_cache
from typing import Optional

import cv2
from PIL import Image as PILImage
from PIL.ExifTags import TAGS

_EXIF_DT_TAG = next((k for k, v in TAGS.items() if v == 'DateTimeOriginal'), None)
_FLASH_TAG = 37385
_SHUTTER_TAG = next((k for k, v in TAGS.items() if v == 'ExposureTime'), None)
_CAMERA_TAG = next((k for k, v in TAGS.items() if v == 'Model'), None)


@lru_cache(maxsize=50000)
def _get_exif(path: str) -> dict:
    try:
        img = PILImage.open(path)
        exif = img._getexif() if hasattr(img, '_getexif') else {}
        return exif or {}
    except Exception:
        return {}


def get_exif_datetime(path: str) -> Optional[tuple]:
    """
    Return a sortable (year, month, day, hour, min, sec) tuple from
    EXIF DateTimeOriginal, or None if missing or unparseable.
    """
    exif = _get_exif(str(path))
    raw = exif.get(_EXIF_DT_TAG) if _EXIF_DT_TAG else None
    if not raw:
        return None
    try:
        date, time = raw.split(' ')
        y, m, d = (int(v) for v in date.split(':'))
        hh, mm, ss = (int(v) for v in time.split(':'))
        return (y, m, d, hh, mm, ss)
    except Exception:
        return None


def get_exif_metadata(path: str, cfg: dict) -> dict:
    exif = _get_exif(str(path))
    dt = exif.get(_EXIF_DT_TAG, '')
    flash = exif.get(_FLASH_TAG, 0)
    shutter = exif.get(_SHUTTER_TAG)
    camera = exif.get(_CAMERA_TAG, '')

    weather = 'unknown'
    if shutter and hasattr(shutter, 'denominator') and shutter.denominator:
        sunny_threshold = int(cfg.get('sunny_shutter_threshold', 200))
        weather = 'sunny' if shutter.denominator >= sunny_threshold else 'cloudy'

    skip = False
    skip_reason = ''
    lap_var = 0.0

    if cfg.get('skip_flash') and flash and flash != 0:
        skip = True
        skip_reason = 'flash'

    if not skip and cfg.get('skip_foggy'):
        try:
            img_arr = cv2.imread(path)
            if img_arr is not None:
                gray = cv2.cvtColor(img_arr, cv2.COLOR_BGR2GRAY)
                lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                if lap_var < cfg.get('foggy_threshold', 50):
                    skip = True
                    skip_reason = 'fog'
        except Exception:
            pass

    return {
        'datetime': dt,
        'camera_name': camera,
        'shutter_speed': str(shutter) if shutter else '',
        'weather': weather,
        'skip': skip,
        'skip_reason': skip_reason,
        'laplacian_var': lap_var,
    }

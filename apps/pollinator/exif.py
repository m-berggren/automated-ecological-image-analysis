"""Pollinator camera-trap EXIF extraction and image-quality heuristics.

Used at upload time to derive captured_at, weather (sunny/cloudy via the
Wingscapes shutter-speed heuristic), Laplacian variance for fog detection,
and auto-exclusion of flash/foggy images. Specific to the camera-trap
field-research workflow; other modules should not call into this.
"""

from __future__ import annotations

import datetime
from typing import Any

import numpy as np
from django.conf import settings
from PIL import ExifTags, Image


_JSON_SAFE = (str, int, float, bool, type(None))

EXIF_TAG_EXPOSURE_TIME = 33434
EXIF_TAG_SHUTTER_SPEED_VALUE = 37377  # APEX: ExposureTime = 1 / 2**value
_EXIF_IFD_POINTER = 0x8769


def _exif_to_dict(img: Image.Image) -> dict[str, Any]:
    raw = img.getexif()
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for tag_id, value in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        out[name] = _coerce(value)
    # Photographic tags (ExposureTime, ShutterSpeedValue, ISO, FNumber,
    # DateTimeOriginal, ...) live in the ExifIFD sub-block, not the top-
    # level dict. Merge them in so callers see one flat namespace. Without
    # this, weather/shutter_speed extraction silently fall through to
    # 'unknown' on cameras (e.g. Wingscapes TLCAM PRO) that only write
    # exposure data inside the sub-IFD.
    try:
        sub = raw.get_ifd(_EXIF_IFD_POINTER)
    except Exception:
        sub = {}
    for tag_id, value in sub.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        out[name] = _coerce(value)
    return out


def _shutter_denominator(exif: dict) -> int | None:
    """Return the integer N such that the shutter speed is 1/N second.

    Tries ExposureTime first (preferred — direct seconds value); falls
    back to ShutterSpeedValue (APEX, log2(1/exposure)) which is what
    Wingscapes cameras actually write."""
    exposure = exif.get('ExposureTime')
    if isinstance(exposure, (tuple, list)) and len(exposure) >= 2:
        try:
            return int(exposure[1])
        except (ValueError, TypeError):
            pass
    if isinstance(exposure, float) and exposure > 0:
        return int(1 / exposure)
    apex = exif.get('ShutterSpeedValue')
    if isinstance(apex, (int, float)) and apex > 0:
        return int(2 ** float(apex))
    return None


def _coerce(value: Any) -> Any:
    if isinstance(value, _JSON_SAFE):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8', errors='replace')
        except Exception:
            return None
    if isinstance(value, (tuple, list)):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
        try:
            return float(value)
        except Exception:
            return None
    return str(value)


def _parse_exif_datetime(s: str | None) -> datetime.datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.datetime.strptime(s, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        return None


def _derive_weather(exif_raw: dict, exif: dict) -> str:
    """Camera with fixed aperture (Wingscapes TLCAM PRO f/2.8): fast shutter
    → bright → sunny, slow shutter → dim → cloudy."""
    threshold = getattr(settings, 'SUNNY_SHUTTER_THRESHOLD', 150)
    denom = _shutter_denominator(exif)
    if denom is None:
        return 'unknown'
    return 'sunny' if denom > threshold else 'cloudy'


def _compute_laplacian_variance(img: Image.Image) -> float:
    gray = np.array(img.convert('L'), dtype=np.float64)
    from scipy.ndimage import laplace

    lap = laplace(gray)
    return float(lap.var())


def _compute_laplacian_variance_cv2(img: Image.Image) -> float:
    try:
        import cv2

        gray = np.array(img.convert('L'))
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except ImportError:
        return _compute_laplacian_variance(img)


def _determine_exclusion(
    flash_fired: bool | None,
    laplacian_var: float | None,
) -> tuple[bool, str]:
    if flash_fired and getattr(settings, 'AUTO_EXCLUDE_FLASH', True):
        return True, 'flash_fired'
    if laplacian_var is not None and getattr(settings, 'AUTO_EXCLUDE_FOGGY', True):
        threshold = getattr(settings, 'FOGGY_LAPLACIAN_THRESHOLD', 50)
        if laplacian_var < threshold:
            return True, 'out_of_focus'
    return False, ''


def _strip_nulls(value: Any) -> Any:
    """Camera EXIF often pads strings with NUL bytes (e.g. PrintIM tags).
    Postgres jsonb refuses U+0000, so scrub them at the source. Recurses
    through dicts and lists; non-strings pass through unchanged.
    """
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strip_nulls(v) for v in value]
    return value


def extract_image_metadata(file: Any) -> dict[str, Any]:
    """Returns width, height, captured_at, flash_fired, exif, weather,
    laplacian_var, shutter_speed, excluded, exclusion_reason."""
    pos = file.tell() if hasattr(file, 'tell') else None
    try:
        img = Image.open(file)
        img.load()
        width, height = img.size
        exif = _exif_to_dict(img)
        raw_exif = dict(img.getexif()) if img.getexif() else {}
        laplacian_var = _compute_laplacian_variance_cv2(img)
    finally:
        if pos is not None and hasattr(file, 'seek'):
            file.seek(pos)

    captured_at = _parse_exif_datetime(
        exif.get('DateTimeOriginal') or exif.get('DateTime'),
    )

    flash_fired: bool | None = None
    flash_value = exif.get('Flash')
    if isinstance(flash_value, int):
        flash_fired = bool(flash_value & 1)

    weather = _derive_weather(raw_exif, exif)

    denom = _shutter_denominator(exif)
    shutter_speed = f'1/{denom}' if denom else ''

    excluded, exclusion_reason = _determine_exclusion(flash_fired, laplacian_var)

    return _strip_nulls({
        'width': width,
        'height': height,
        'captured_at': captured_at,
        'flash_fired': flash_fired,
        'exif': exif,
        'weather': weather,
        'laplacian_var': round(laplacian_var, 1) if laplacian_var is not None else None,
        'shutter_speed': shutter_speed,
        'excluded': excluded,
        'exclusion_reason': exclusion_reason,
    })

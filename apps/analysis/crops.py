"""Detection crop writer.

write_detection_crop saves a tight bounding-box crop per detection so the
review UI can show the actual insect in the grid tile. Context (where in
the source image the detection sits) lives in the preview pane via a
bbox overlay on the full source image — not here.

Returns False (rather than raising) on bad inputs or PIL errors, so a
single corrupt image cannot abort an entire inference run.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from .models import Detection

logger = logging.getLogger(__name__)


def write_detection_crop(detection: Detection) -> bool:
    if not detection.image or not detection.image.file:
        return False
    bbox = detection.bbox or {}
    # Pipeline writes bbox as {x1, y1, x2, y2, w, h}; see
    # ml-pipelines/pollinator/workflows/{inference_yolo,merge}.py.
    try:
        x1 = float(bbox['x1'])
        y1 = float(bbox['y1'])
        x2 = float(bbox['x2'])
        y2 = float(bbox['y2'])
    except (KeyError, TypeError, ValueError):
        return False
    if x2 <= x1 or y2 <= y1:
        return False

    try:
        src = Path(detection.image.file.path)
        with Image.open(src) as img:
            crop = img.crop((x1, y1, x2, y2)).convert('RGB')
        buf = io.BytesIO()
        crop.save(buf, 'JPEG', quality=85)
    except Exception:
        logger.exception(f'Failed to render crop for detection {detection.pk}')
        return False

    name = f'runs/{detection.inference_run_id}/crops/det_{detection.pk}.jpg'
    saved = default_storage.save(name, ContentFile(buf.getvalue()))
    detection.crop.name = saved
    return True

"""
detection/yolo_detector.py
============================
YOLO pollinator detector with SAHI-tiled inference.

Loads a trained YOLO checkpoint and detects pollinators in full field
images. SAHI (Slicing Aided Hyper Inference) tiles the image into
overlapping 640x640 patches so small insects (~30px in 3008x1692 source)
appear at natural size inside their tile.

Usage:
    from pollinator.detection import YoloDetector

    det = YoloDetector("runs/pollinator/stage2_finetune/weights/best.pt")
    detections = det.predict("path/to/image.jpg")
    # [{class, confidence, x1, y1, x2, y2, w, h}, ...]
"""

import logging
from pathlib import Path
from typing import Optional, Union

import torch
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from ultralytics import YOLO

logger = logging.getLogger(__name__)

CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']


class YoloDetector:
    """
    YOLO-based pollinator detector.

    Wraps a trained YOLO checkpoint. By default uses SAHI tiled
    inference (matches notebook + production) so small insects in
    high-resolution field images are not missed. Set use_sahi=False
    for raw single-pass YOLO inference.
    """

    def __init__(
        self,
        checkpoint_path: str,
        confidence: float = 0.25,
        device: Optional[str] = None,
        use_sahi: bool = True,
        slice_size: int = 640,
        overlap: float = 0.2,
        iou: float = 0.5,
    ):
        """
        Args:
            checkpoint_path: Path to trained YOLO .pt file.
            confidence:      Minimum detection confidence threshold.
            device:          "cuda", "cpu", or None (auto-detect).
            use_sahi:        Tile the image for small-object detection (default True).
            slice_size:      SAHI tile size in pixels (must match training imgsz).
            overlap:         SAHI overlap ratio between tiles (0-1).
            iou:             SAHI postprocess IoU threshold for merging tile results.
        """
        self.checkpoint_path = str(checkpoint_path)
        self.confidence = confidence
        self.use_sahi = use_sahi
        self.slice_size = slice_size
        self.overlap = overlap
        self.iou = iou
        self.device = device or ('cuda:0' if torch.cuda.is_available() else 'cpu')
        self._load()
        logger.info(
            f'YoloDetector loaded: ckpt={self.checkpoint_path} '
            f'sahi={self.use_sahi} conf={self.confidence} device={self.device}'
        )

    def _load(self):
        if self.use_sahi:
            self.model = AutoDetectionModel.from_pretrained(
                model_type='ultralytics',
                model_path=self.checkpoint_path,
                confidence_threshold=self.confidence,
                device=self.device,
            )
        else:
            self.model = YOLO(self.checkpoint_path)

    def _predict_sahi(self, image_path: Union[str, Path]) -> list:
        result = get_sliced_prediction(
            str(image_path),
            self.model,
            slice_height=self.slice_size,
            slice_width=self.slice_size,
            overlap_height_ratio=self.overlap,
            overlap_width_ratio=self.overlap,
            postprocess_match_threshold=self.iou,
            verbose=0,
        )
        out = []
        for det in result.object_prediction_list:
            b = det.bbox
            out.append(
                {
                    'class': det.category.name,
                    'confidence': float(det.score.value),
                    'x1': int(round(b.minx)),
                    'y1': int(round(b.miny)),
                    'x2': int(round(b.maxx)),
                    'y2': int(round(b.maxy)),
                    'w': int(round(b.maxx - b.minx)),
                    'h': int(round(b.maxy - b.miny)),
                }
            )
        return out

    def _predict_raw(self, image_path: Union[str, Path]) -> list:
        results = self.model(str(image_path), conf=self.confidence, verbose=False)
        out = []
        for r in results:
            names = r.names
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_idx = int(box.cls.item())
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = (int(round(v)) for v in xyxy)
                out.append(
                    {
                        'class': names.get(cls_idx, str(cls_idx)),
                        'confidence': float(box.conf.item()),
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                        'w': x2 - x1,
                        'h': y2 - y1,
                    }
                )
        return out

    def predict(self, image_path: Union[str, Path]) -> list:
        """
        Run detection on a single full image.

        Args:
            image_path: Path to the image file.

        Returns:
            List of detection dicts with keys:
                class, confidence, x1, y1, x2, y2, w, h
        """
        if self.use_sahi:
            return self._predict_sahi(image_path)
        return self._predict_raw(image_path)

    def predict_batch(self, image_paths: list) -> list:
        """
        Run detection on a list of images.

        Args:
            image_paths: List of paths to image files.

        Returns:
            List of dicts with keys:
                path, detections (list, see predict()), error (optional)
        """
        results = []
        for p in image_paths:
            try:
                detections = self.predict(p)
                results.append(
                    {
                        'path': str(p),
                        'detections': detections,
                    }
                )
            except Exception as e:
                logger.warning(f'Failed to detect on {p}: {e}')
                results.append(
                    {
                        'path': str(p),
                        'detections': [],
                        'error': str(e),
                    }
                )
        return results

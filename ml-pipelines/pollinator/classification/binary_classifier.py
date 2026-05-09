"""
classification/binary_classifier.py
=====================================
Binary classifier: insect vs background.

Loads a trained EfficientNet-B2 or InsectNet checkpoint and classifies
a single crop image or a batch of crops. Architecture is auto-detected
from the checkpoint's state_dict keys.

Usage:
    from pollinator.classification import BinaryClassifier

    clf = BinaryClassifier("path/to/binary_best.pth")
    label, confidence = clf.predict("path/to/crop.jpg")
    # label: "insect" or "background"
    # confidence: float 0-1
"""

import logging
from pathlib import Path
from typing import Optional, Union

import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as T
from PIL import Image

logger = logging.getLogger(__name__)

CLASSES = ["background", "insect"]


def _letterbox(img: Image.Image, size: int) -> Image.Image:
    w, h  = img.size
    max_s = max(w, h)
    sq    = Image.new("RGB", (max_s, max_s), (0, 0, 0))
    sq.paste(img, ((max_s - w) // 2, (max_s - h) // 2))
    return sq.resize((size, size), Image.BILINEAR)


def _make_transform(img_size: int) -> T.Compose:
    return T.Compose([
        T.Lambda(lambda img: _letterbox(img, img_size)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def _build_efficientnet_b2() -> nn.Module:
    model = torchvision.models.efficientnet_b2(weights=None)
    in_f  = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_f, 2)
    return model


def _build_insectnet() -> nn.Module:
    model    = torchvision.models.regnet_y_32gf()
    model.fc = nn.Linear(3712, 2)
    return model


class BinaryClassifier:
    """
    Binary insect/background classifier.

    Loads a checkpoint saved by crop_binary_classifier.ipynb and
    classifies individual crops or batches. Architecture (EfficientNet-B2
    or InsectNet backbone) is auto-detected from the checkpoint.
    """

    def __init__(self, checkpoint_path: str, device: Optional[str] = None):
        """
        Args:
            checkpoint_path: Path to .pth file saved during training.
            device:          "cuda", "cpu", or None (auto-detect).
        """
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self._load(checkpoint_path)
        logger.info(
            f"BinaryClassifier loaded: arch={self.arch} "
            f"img={self.img_size}px device={self.device}"
        )

    def _load(self, path: str):
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.img_size = ckpt.get("img_size", 256)

        # Auto-detect architecture from state_dict keys
        # (checkpoint may store "model_name" or "model" or neither)
        state_keys = list(ckpt["state_dict"].keys())
        if any("trunk_output" in k or "stem." in k for k in state_keys):
            self.arch = "insectnet"
            model = _build_insectnet()
        else:
            self.arch = "efficientnet"
            model = _build_efficientnet_b2()

        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        self.model     = model.to(self.device)
        self.transform = _make_transform(self.img_size)

    def predict(self, image_path: Union[str, Path],
                threshold: float = 0.5) -> tuple:
        """
        Classify a single crop image.

        Args:
            image_path: Path to .jpg/.png crop file.
            threshold:  Minimum insect probability to classify as insect.
                        Lower = higher recall; higher = higher precision.

        Returns:
            (label, confidence)
            label:      "insect" or "background"
            confidence: probability of insect class (0-1)
        """
        img = Image.open(image_path).convert("RGB")
        x   = self.transform(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0]
        insect_prob = float(probs[1])
        label       = "insect" if insect_prob >= threshold else "background"
        return label, insect_prob

    def predict_batch(self, image_paths: list,
                      threshold: float = 0.5) -> list:
        """
        Classify a batch of crop images.

        Args:
            image_paths: List of paths to crop images.
            threshold:   Minimum insect probability to classify as insect.
                         Lower = higher recall; higher = higher precision.

        Returns:
            List of dicts with keys:
                path, label, confidence, is_insect
        """
        results = []
        for p in image_paths:
            try:
                img  = Image.open(p).convert("RGB")
                x    = self.transform(img).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    probs = torch.softmax(self.model(x), dim=1)[0]
                insect_prob = float(probs[1])
                is_insect   = insect_prob >= threshold
                results.append({
                    "path":       str(p),
                    "label":      "insect" if is_insect else "background",
                    "confidence": insect_prob,
                    "is_insect":  is_insect,
                })
            except Exception as e:
                logger.warning(f"Failed to classify {p}: {e}")
                results.append({
                    "path":       str(p),
                    "label":      "error",
                    "confidence": 0.0,
                    "is_insect":  False,
                })
        return results
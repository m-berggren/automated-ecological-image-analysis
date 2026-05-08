"""
classification/group_classifier.py
=====================================
Group classifier: bumblebee / fly / butterfly_moth / other.

Loads a trained EfficientNet-B2 or InsectNet checkpoint and assigns
a confirmed insect crop to one of four pollinator categories.
Architecture is auto-detected from the checkpoint's state_dict keys.

Usage:
    from pollinator.classification import GroupClassifier

    clf = GroupClassifier("path/to/group_best.pth")
    label, confidence, all_probs = clf.predict("path/to/crop.jpg")
    # label: pollinator category name
    # confidence: probability of predicted class (0-1)
    # all_probs: dict of {class_name: probability}
    
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

CLASSES = ["bumblebee", "fly", "butterfly_moth", "other"]


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


def _build_efficientnet_b2(num_classes: int) -> nn.Module:
    model = torchvision.models.efficientnet_b2(weights=None)
    in_f  = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_f, num_classes)
    return model


def _build_insectnet(num_classes: int) -> nn.Module:
    model    = torchvision.models.regnet_y_32gf()
    model.fc = nn.Linear(3712, num_classes)
    return model


class GroupClassifier:
    """
    Four-class pollinator group classifier.

    Classifies confirmed insect crops into:
    bumblebee / fly / butterfly_moth / other
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
            f"GroupClassifier loaded: arch={self.arch} "
            f"classes={self.classes} img={self.img_size}px device={self.device}"
        )

    def _load(self, path: str):
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.img_size = ckpt.get("img_size", 224)
        self.classes  = ckpt.get("classes", CLASSES)
        n             = len(self.classes)

        # Auto-detect architecture from state_dict keys
        state_keys = list(ckpt["state_dict"].keys())
        if any("trunk_output" in k or "stem." in k for k in state_keys):
            self.arch = "insectnet"
            model = _build_insectnet(n)
        else:
            self.arch = "efficientnet"
            model = _build_efficientnet_b2(n)

        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        self.model     = model.to(self.device)
        self.transform = _make_transform(self.img_size)

    def predict(self, image_path: Union[str, Path]) -> tuple:
        """
        Classify a single confirmed insect crop.

        Args:
            image_path: Path to .jpg/.png crop file.

        Returns:
            (label, confidence, all_probs)
            label:      pollinator category name
            confidence: probability of predicted class (0-1)
            all_probs:  dict of {class_name: probability}
        """
        img = Image.open(image_path).convert("RGB")
        x   = self.transform(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0]
        idx       = probs.argmax().item()
        label     = self.classes[idx]
        conf      = float(probs[idx])
        all_probs = {c: float(probs[i]) for i, c in enumerate(self.classes)}
        return label, conf, all_probs

    def predict_batch(self, image_paths: list) -> list:
        """
        Classify a batch of confirmed insect crops.

        Args:
            image_paths: List of paths to crop images.

        Returns:
            List of dicts with keys:
                path, label, confidence, all_probs
        """
        results = []
        for p in image_paths:
            try:
                label, conf, all_probs = self.predict(p)
                results.append({
                    "path":       str(p),
                    "label":      label,
                    "confidence": conf,
                    "all_probs":  all_probs,
                })
            except Exception as e:
                logger.warning(f"Failed to classify {p}: {e}")
                results.append({
                    "path":       str(p),
                    "label":      "error",
                    "confidence": 0.0,
                    "all_probs":  {},
                })
        return results
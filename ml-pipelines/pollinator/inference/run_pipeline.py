"""
inference/run_pipeline.py
==========================
End-to-end pollinator detection pipeline

Runs:
  1. Background subtraction preprocessing  → candidate crops
  2. Binary classifier                     → filter background crops
  3. Group classifier                      → assign pollinator category

Usage (CLI):
    python -m pollinator.inference.run_pipeline \
        --image_dir path/to/camera_folder \
        --output_dir path/to/output \
        --binary_model path/to/binary_best.pth \
        --group_model path/to/group_best.pth

Usage (as module):
    from pollinator.inference.run_pipeline import run_pipeline

    results = run_pipeline(
        image_dir    = "path/to/images",
        output_dir   = "path/to/output",
        binary_model = "path/to/binary_best.pth",
        group_model  = "path/to/group_best.pth",
    )
"""

import argparse
import csv
import logging
from pathlib import Path
from typing import Optional

from ..preprocessing.pipeline import run_preprocessing, DEFAULT_CONFIG
from ..classification.binary_classifier import BinaryClassifier
from ..classification.group_classifier import GroupClassifier

logger = logging.getLogger(__name__)

OUTPUT_FIELDS = [
    "image_name", "crop_filename", "datetime", "weather",
    "detection_scope", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
    "is_insect", "binary_confidence",
    "pollinator_type", "group_confidence",
    "bumblebee_prob", "fly_prob", "butterfly_moth_prob", "other_prob",
]


def run_pipeline(
    image_dir:    str,
    output_dir:   str,
    binary_model: str,
    group_model:  str,
    config:       Optional[dict] = None,
    binary_threshold: float = 0.5,
    device:       Optional[str] = None,
    debug:        bool = False,
) -> dict:
    """
    Run full pollinator detection pipeline on a camera folder.

    IMPORTANT: The camera angle must be consistent throughout the image
    sequence. If the camera was repositioned mid-sequence, split the
    folder at that point before running.

    Args:
        image_dir:         Path to folder with images from one camera plot.
        output_dir:        Path to output folder.
        binary_model:      Path to trained binary classifier checkpoint.
        group_model:       Path to trained group classifier checkpoint.
        config:            Optional preprocessing config overrides.
        binary_threshold:  Minimum confidence to classify as insect (default 0.5).
                           Lower this (e.g. 0.3) to increase recall at the cost
                           of more false positives for manual review.
        device:            "cuda", "cpu", or None (auto-detect).
        debug:             Save debug images from preprocessing.

    Returns:
        dict with keys:
            - output_csv:       Path to final results CSV
            - n_candidates:     Crops extracted by preprocessing
            - n_insects:        Crops classified as insect
            - n_background:     Crops classified as background
            - pollinator_counts: Dict of {category: count}
    """
    image_dir  = Path(image_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Preprocessing ────────────────────────────────────────────
    logger.info(f"Step 1: Preprocessing {image_dir}")
    prep_result = run_preprocessing(
        image_dir  = str(image_dir),
        output_dir = str(output_dir / "preprocessing"),
        config     = config,
        debug      = debug,
    )
    crop_dir = Path(prep_result["crop_dir"])
    n_candidates = prep_result["n_crops"]
    logger.info(f"  Extracted {n_candidates} candidate crops")

    if n_candidates == 0:
        logger.info("No candidates found. Done.")
        return {
            "output_csv":       str(output_dir / "results.csv"),
            "n_candidates":     0,
            "n_insects":        0,
            "n_background":     0,
            "pollinator_counts": {},
        }

    # ── Step 2: Binary classification ────────────────────────────────────
    logger.info(f"Step 2: Binary classification (threshold={binary_threshold})")
    binary_clf = BinaryClassifier(binary_model, device=device)

    crop_paths = sorted(crop_dir.glob("*.jpg")) + sorted(crop_dir.glob("*.png"))
    binary_results = binary_clf.predict_batch(crop_paths)

    insect_crops = [
        r for r in binary_results
        if r["is_insect"] and r["confidence"] >= binary_threshold
    ]
    background_crops = [r for r in binary_results if not r["is_insect"]
                        or r["confidence"] < binary_threshold]

    logger.info(f"  Insect: {len(insect_crops)} | Background: {len(background_crops)}")

    # ── Step 3: Group classification ─────────────────────────────────────
    logger.info("Step 3: Group classification")
    group_clf = GroupClassifier(group_model, device=device)

    insect_paths = [Path(r["path"]) for r in insect_crops]
    group_results = group_clf.predict_batch(insect_paths)

    # Build lookup: path -> group result
    group_lookup = {r["path"]: r for r in group_results}

    # ── Step 4: Write output CSV ─────────────────────────────────────────
    # Read preprocessing CSV to get metadata per crop
    prep_csv = output_dir / "preprocessing" / "results.csv"
    meta_lookup = {}
    if prep_csv.exists():
        with open(prep_csv) as f:
            for row in csv.DictReader(f):
                fn = row.get("crop_filename", "")
                if fn:
                    meta_lookup[fn] = row

    output_csv = output_dir / "results.csv"
    pollinator_counts = {"bumblebee": 0, "fly": 0, "butterfly_moth": 0, "other": 0}

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for br in binary_results:
            crop_path = Path(br["path"])
            crop_fn   = crop_path.name
            meta      = meta_lookup.get(crop_fn, {})
            is_insect = br["is_insect"] and br["confidence"] >= binary_threshold

            row = {
                "image_name":       meta.get("image_name", ""),
                "crop_filename":    crop_fn,
                "datetime":         meta.get("datetime", ""),
                "weather":          meta.get("weather", ""),
                "detection_scope":  meta.get("detection_scope", ""),
                "bbox_x":           meta.get("bbox_x", ""),
                "bbox_y":           meta.get("bbox_y", ""),
                "bbox_w":           meta.get("bbox_w", ""),
                "bbox_h":           meta.get("bbox_h", ""),
                "is_insect":        is_insect,
                "binary_confidence": round(br["confidence"], 4),
                "pollinator_type":  "",
                "group_confidence": "",
                "bumblebee_prob":   "",
                "fly_prob":         "",
                "butterfly_moth_prob": "",
                "other_prob":       "",
            }

            if is_insect and str(crop_path) in group_lookup:
                gr = group_lookup[str(crop_path)]
                row["pollinator_type"]     = gr["label"]
                row["group_confidence"]    = round(gr["confidence"], 4)
                row["bumblebee_prob"]      = round(gr["all_probs"].get("bumblebee", 0), 4)
                row["fly_prob"]            = round(gr["all_probs"].get("fly", 0), 4)
                row["butterfly_moth_prob"] = round(gr["all_probs"].get("butterfly_moth", 0), 4)
                row["other_prob"]          = round(gr["all_probs"].get("other", 0), 4)
                if gr["label"] in pollinator_counts:
                    pollinator_counts[gr["label"]] += 1

            writer.writerow(row)

    logger.info(f"Results saved to {output_csv}")
    logger.info(f"Pollinator counts: {pollinator_counts}")

    return {
        "output_csv":        str(output_csv),
        "n_candidates":      n_candidates,
        "n_insects":         len(insect_crops),
        "n_background":      len(background_crops),
        "pollinator_counts": pollinator_counts,
    }


# ── CLI entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run full pollinator detection pipeline")
    parser.add_argument("--image_dir",    required=True)
    parser.add_argument("--output_dir",   required=True)
    parser.add_argument("--binary_model", required=True)
    parser.add_argument("--group_model",  required=True)
    parser.add_argument("--threshold",    type=float, default=0.5)
    parser.add_argument("--debug",        action="store_true")
    args = parser.parse_args()

    result = run_pipeline(
        image_dir        = args.image_dir,
        output_dir       = args.output_dir,
        binary_model     = args.binary_model,
        group_model      = args.group_model,
        binary_threshold = args.threshold,
        debug            = args.debug,
    )
    print(f"\nResults:")
    print(f"  Candidates:  {result['n_candidates']}")
    print(f"  Insects:     {result['n_insects']}")
    print(f"  Background:  {result['n_background']}")
    print(f"  Counts:      {result['pollinator_counts']}")
    print(f"  CSV:         {result['output_csv']}")

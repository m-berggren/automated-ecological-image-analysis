"""Resolved paths for the fly operating-curve evaluation scripts.

Every external location the scripts read or write is declared here once, so the
folder is portable: move it and only the defaults below (or the matching
environment variables) need attention.

Small inputs are vendored next to this file so a run is self-contained:
  predictions/  captured per-plot combined-pipeline detections (*_results.json)
                plus the YOLO-only vetted_predictions.json

Large inputs (the 358-frame vetted set, the hand-picked grid frames) are not
vendored; they live in the thesis repo, which is located by THESIS_AID_ROOT or,
failing that, by walking up for a sibling directory named 'thesis-aid'. Each
such path is also directly overridable by its own FLY_EVAL_* variable.

Outputs default to ./figures next to the scripts.

Override any path without editing this file:
    FLY_EVAL_DATASET   vetted dataset root (expects images/ and labels/)
    FLY_EVAL_PRED_DIR  directory of *_results.json predictions
    FLY_EVAL_VETTED    YOLO-only vetted_predictions.json
    FLY_EVAL_GRID      hand-picked establishing frames for the failure grid
    FLY_EVAL_CURVE     swept operating-curve JSON (sweep writes, figures read)
    FLY_EVAL_OUT       output directory for figures and derived artifacts
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Marks a default that could not be resolved. require() rejects it with a hint
# instead of a confusing "file not found" on a guessed absolute path.
_UNRESOLVED = HERE / '_set_FLY_EVAL_DATASET_or_THESIS_AID_ROOT'


def _path(var: str, default: Path) -> Path:
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else default


def _discover_thesis() -> Path | None:
    """Locate the thesis repo that owns the large, un-vendored inputs.

    Honors THESIS_AID_ROOT, otherwise walks up from this file looking for a
    sibling directory named 'thesis-aid'. Returns None if neither resolves, in
    which case the affected paths must be set explicitly via FLY_EVAL_*.
    """
    env = os.environ.get('THESIS_AID_ROOT')
    if env:
        return Path(env).expanduser()
    for ancestor in HERE.parents:
        cand = ancestor / 'thesis-aid'
        if cand.is_dir():
            return cand
    return None


_THESIS = _discover_thesis()


def _thesis_path(rel: str) -> Path:
    return _THESIS / rel if _THESIS else _UNRESOLVED


# Vetted field set: 358 frames + YOLO-normalized labels (large, not vendored).
DATASET = _path('FLY_EVAL_DATASET', _thesis_path('yolo-test-inference-with-annotations'))
IMAGES = DATASET / 'images'
LABELS = DATASET / 'labels'

# Captured per-plot combined-pipeline predictions (conf 0.05), one per plot.
PRED_DIR = _path('FLY_EVAL_PRED_DIR', HERE / 'predictions')

# YOLO-only stored predictions used by analyze_vetted.py.
VETTED_JSON = _path('FLY_EVAL_VETTED', PRED_DIR / 'vetted_predictions.json')

# Hand-picked establishing frames for the failure grid (large, not vendored).
GRID = _path('FLY_EVAL_GRID', _thesis_path('grid'))

# Swept operating-curve data: sweep_operating_curve.py writes it, the figure
# script reads it.
OPERATING_CURVE_JSON = _path('FLY_EVAL_CURVE', HERE / 'operating_curve.json')

# Where figures and derived artifacts land.
OUT_DIR = _path('FLY_EVAL_OUT', HERE / 'figures')


def require(path: Path, what: str) -> Path:
    """Fail loud if an expected input is missing, with a fixup hint."""
    if not path.exists():
        raise FileNotFoundError(
            f'{what} not found at {path}. Set the matching FLY_EVAL_* '
            f'environment variable or place the data there.')
    return path

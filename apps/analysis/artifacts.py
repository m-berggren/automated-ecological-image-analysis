"""Ingest Ultralytics run-directory outputs as ModelArtifact rows + metrics.

Two callers share this: the manual model-upload endpoint (apps/analysis/views.py)
streams UploadedFile objects, while incremental training
(apps/pollinator/training.py) has the run directory on local disk. The
filename->kind mapping and results.csv parsing live here so both stay in sync.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from django.core.files.base import ContentFile

from .models import ModelArtifact, ModelArtifactKind

logger = logging.getLogger(__name__)

# Ultralytics YOLO training-run filenames (basename only) -> ModelArtifactKind.
# Names not listed are skipped unless they match a *_batch* sample-tile prefix.
ARTIFACT_NAME_MAP = {
    'BoxF1_curve.png': ModelArtifactKind.F1_CURVE,
    'BoxP_curve.png': ModelArtifactKind.PRECISION_CURVE,
    'BoxPR_curve.png': ModelArtifactKind.PR_CURVE,
    'BoxR_curve.png': ModelArtifactKind.RECALL_CURVE,
    'F1_curve.png': ModelArtifactKind.F1_CURVE,
    'P_curve.png': ModelArtifactKind.PRECISION_CURVE,
    'PR_curve.png': ModelArtifactKind.PR_CURVE,
    'R_curve.png': ModelArtifactKind.RECALL_CURVE,
    'confusion_matrix.png': ModelArtifactKind.CONFUSION_MATRIX,
    'confusion_matrix_normalized.png': ModelArtifactKind.CONFUSION_MATRIX,
    'labels.jpg': ModelArtifactKind.LABELS,
    'labels_correlogram.jpg': ModelArtifactKind.LABELS,
    'results.csv': ModelArtifactKind.RESULTS_CSV,
    'results.png': ModelArtifactKind.TRAINING_CURVE,
}
SAMPLE_PREDICTION_PREFIXES = ('train_batch', 'val_batch')

# Ultralytics column names vary by task: '(B)' suffix for detection boxes,
# '(M)' for segmentation. Map both to the canonical names the UI renders.
_RESULTS_ALIASES = {
    'precision': ('metrics/precision(B)', 'metrics/precision'),
    'recall': ('metrics/recall(B)', 'metrics/recall'),
    'mAP50': ('metrics/mAP50(B)', 'metrics/mAP50'),
    'mAP50-95': ('metrics/mAP50-95(B)', 'metrics/mAP50-95'),
}


def classify_artifact(basename: str) -> tuple[str | None, str]:
    """Return (ModelArtifactKind value, caption) for a known run-folder asset,
    or (None, '') if unrecognised. Caption disambiguates confusion-matrix
    variants and names sample-prediction tiles."""
    if basename in ARTIFACT_NAME_MAP:
        caption = 'normalized' if basename == 'confusion_matrix_normalized.png' else ''
        return ARTIFACT_NAME_MAP[basename], caption
    if any(basename.startswith(p) for p in SAMPLE_PREDICTION_PREFIXES):
        return ModelArtifactKind.SAMPLE_PREDICTIONS, basename
    return None, ''


# Ultralytics args.yaml hyperparameter keys -> the yolo_-prefixed parameter
# names shown on the model card. Shared so manually-uploaded and incrementally
# trained models expose identical fields. 'model'/'data' are intentionally
# omitted: they're transient run paths, not informative hyperparameters.
_ARGS_YAML_KEYS = ('epochs', 'imgsz', 'batch', 'lr0', 'optimizer', 'patience')


def params_from_args_yaml(text: str) -> dict:
    """Pull the standard hyperparameters out of an Ultralytics args.yaml,
    prefixed yolo_ to match the manual-upload path. Empty on any failure."""
    try:
        import yaml

        data = yaml.safe_load(text)
    except Exception:
        logger.exception('Failed to parse args.yaml')
        return {}
    if not isinstance(data, dict):
        return {}
    return {f'yolo_{k}': data[k] for k in _ARGS_YAML_KEYS if k in data}


def metrics_from_results_csv(text: str) -> dict:
    """Extract final-epoch validation metrics from Ultralytics results.csv text.
    Returns canonical names (precision, recall, mAP50, mAP50-95); empty on
    any failure so a malformed file never aborts ingestion."""
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = [r for r in reader if any((v or '').strip() for v in r.values())]
    except Exception:
        logger.exception('Failed to parse results.csv')
        return {}
    if not rows:
        return {}
    final = rows[-1]
    out: dict = {}
    for nice, candidates in _RESULTS_ALIASES.items():
        for col in candidates:
            if col in final and final[col].strip():
                try:
                    out[nice] = float(final[col])
                except ValueError:
                    pass
                break
    return out


def metrics_from_results_json(text: str) -> dict:
    """Extract canonical metrics from a classifier *_results.json
    (EfficientNet / InsectNet trainers). Binary writes test_acc/test_f1/...,
    group writes val_acc/test_arctic_acc/val_macro_f1/...; both map to the
    accuracy/f1/recall/precision names the UI renders. Empty on any failure."""
    try:
        data = json.loads(text)
    except Exception:
        logger.exception('Failed to parse results.json')
        return {}
    if not isinstance(data, dict):
        return {}

    def pick(*keys: str):
        for k in keys:
            v = data.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None

    out: dict = {}
    candidates = {
        'accuracy': ('test_acc', 'test_arctic_acc', 'val_acc', 'acc'),
        'f1': (
            'test_f1',
            'test_arctic_macro_f1',
            'val_macro_f1',
            'macro_f1',
            'best_val_f1',
        ),
        'recall': ('test_recall', 'recall'),
        'precision': ('test_precision', 'precision'),
    }
    for nice, keys in candidates.items():
        value = pick(*keys)
        if value is not None:
            out[nice] = value
    return out


def ingest_run_dir(model_version, run_dir: Path) -> tuple[int, dict, dict]:
    """Scan an Ultralytics run dir (top-level files only) for known artifacts,
    copy each into media as a ModelArtifact row linked to model_version, and
    return (artifact_count, flat_metrics_from_results_csv, params_from_args_yaml).

    Top-level only: the nested weights/ subdir holds best.pt/last.pt, which are
    the model file, not artifacts. Failures on a single file are logged and
    skipped rather than aborting the whole ingest."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        logger.warning(f'Artifact ingest: run dir not found: {run_dir}')
        return 0, {}, {}
    metrics: dict = {}
    params: dict = {}
    ingested = 0
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name == 'results.csv':
            metrics.update(metrics_from_results_csv(path.read_text(errors='replace')))
        elif name.endswith('results.json'):
            metrics.update(metrics_from_results_json(path.read_text(errors='replace')))
        elif name == 'args.yaml':
            params.update(params_from_args_yaml(path.read_text(errors='replace')))
        kind_value, caption = classify_artifact(name)
        if kind_value is None:
            continue
        try:
            art = ModelArtifact(
                model_version=model_version, kind=kind_value, caption=caption
            )
            art.file.save(name, ContentFile(path.read_bytes()), save=True)
            ingested += 1
        except Exception:
            logger.exception(f'Failed to ingest artifact {path}')
    return ingested, metrics, params

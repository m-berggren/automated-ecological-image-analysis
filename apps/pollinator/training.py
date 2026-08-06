"""Pollinator incremental retraining.

run_training_job is the synchronous core: builds a training dataset from
flagged detections, dispatches to the right ML training function with the
selected ModelVersion's weights as the resume source, persists the
resulting ModelVersion. spawn_training_job runs it in a daemon thread.

Pollinator-specific by design. Seeds will mirror this in apps/seeds/.
"""

from __future__ import annotations

import logging
import random
import shutil
import threading
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

ProgressCallback = Callable[[int, int, str, str], None]

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone
from PIL import Image

from apps.analysis.cancellation import RunCancelled
from apps.analysis.models import (
    Detection,
    DetectionStatus,
    JobStatus,
    ModelVersion,
    TrainingJob,
)
from apps.analysis.storage import (
    link_or_copy,
    move_weights_into_place,
    resolve_model_path,
)
from apps.datasets.models import Module

logger = logging.getLogger(__name__)


_ACTIVITY_LOG_CAP = 200


# Per-track defaults. config keys override these.
PER_TRACK_DEFAULTS: dict = {
    'detector': {
        'kind': 'detector',
        'epochs': 20,
        'lr': 1e-4,
        'batch': 16,
        'patience': 10,
        'img_size': 640,
        'mosaic': 0.3,
        'mixup': 0.0,
        'copy_paste': 0.0,
    },
    'binary': {
        'kind': 'binary_classifier',
        'epochs': 20,
        'lr': 5e-4,
        'batch': 32,
        'patience': 5,
        'img_size': 256,
    },
    'group': {
        'kind': 'group_classifier',
        'epochs': 20,
        'lr': 5e-4,
        'batch': 32,
        'patience': 5,
        'img_size': 224,
        'unfreeze_last_block': True,
    },
}

POLLINATOR_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']

# Aliases for class labels emitted by ML models trained on a different
# vocabulary. Ingestion (services.py) and the read serializers route
# every class label through canonical_class() so the rest of the system
# only sees the canonical names in POLLINATOR_CLASSES. Add entries here
# when wiring in a model whose label space drifts.
POLLINATOR_CLASS_ALIASES: dict[str, str] = {
    # The group classifier was trained on a merged butterfly+moth class.
    'butterfly_moth': 'butterfly',
}


def canonical_class(label: str | None) -> str:
    """Normalize a raw model label to a canonical pollinator class.

    Returns '' for empty/None input so callers can do ``canonical or None``
    without an extra guard. Unknown labels pass through unchanged (they
    won't match POLLINATOR_CLASSES downstream and will be filtered out
    of the training pool, which is the right behavior — surfacing them
    rather than silently coercing).
    """
    if not label:
        return ''
    lower = label.lower()
    return POLLINATOR_CLASS_ALIASES.get(lower, lower)


# Tile training defaults. Source images are sliced into overlapping tiles
# before YOLO training so small pollinators stay at native pixel scale.
# Inference must use the same geometry; the config is persisted on the
# resulting ModelVersion.parameters['tile_config'] and read back by
# apps.pollinator.services.
TILE_CONFIG_DEFAULTS: dict = {
    'use_tiles': True,
    'tile_size': 640,
    'overlap': 0.2,
    'min_area': 0.1,
    'keep_empty_tiles': {'train': 2, 'val': 5, 'test': True},
}


def _resolve_tile_config(source: ModelVersion, config: dict) -> dict:
    """Merge tile config: defaults < source model's recorded config < job override.
    Incremental retrains inherit the source's geometry automatically."""
    cfg = dict(TILE_CONFIG_DEFAULTS)
    src_cfg = (source.parameters or {}).get('tile_config') or {}
    cfg.update(src_cfg)
    cfg.update((config or {}).get('tile_config') or {})
    return cfg


# ──────────────────────────────────────────────────────────────────────────
# Progress reporting
# ──────────────────────────────────────────────────────────────────────────


def _make_progress_callback(job_id: int):  # pragma: no cover
    """Build the (processed, total, message, level) callback the ML pipeline
    invokes per epoch. Mirrors the inference progress callback pattern."""

    def cb(processed: int, total: int, message: str = '', level: str = 'info') -> None:
        # Cancellation check on every tick. Status is owned by the cancel
        # endpoint; we just read and raise. RunCancelled inherits
        # BaseException so it bypasses ML pipeline's `except Exception`.
        current = (
            TrainingJob.objects.filter(pk=job_id)
            .values_list('status', flat=True)
            .first()
        )
        if current == JobStatus.CANCELLED:
            raise RunCancelled(f'Training job {job_id} cancelled by user')

        try:
            updates: dict = {'current_epoch': processed, 'total_epochs': total}
            if message:
                job = TrainingJob.objects.get(pk=job_id)
                log = list(job.activity_log or [])
                log.append(
                    {
                        'time': timezone.now().isoformat(),
                        'message': message,
                        'level': level,
                    }
                )
                job.activity_log = log[-_ACTIVITY_LOG_CAP:]
                for k, v in updates.items():
                    setattr(job, k, v)
                job.save(update_fields=list(updates.keys()) + ['activity_log'])
            else:
                TrainingJob.objects.filter(pk=job_id).update(**updates)
        except RunCancelled:
            raise
        except Exception:
            logger.exception(f'Progress callback failed for job {job_id}')

    return cb


class _ActivityLogHandler(logging.Handler):
    """Mirrors the ml-pipeline's `pollinator.*` INFO logs (dataset split,
    background sampling, per-epoch metrics, etc.) into the job's activity_log
    so the in-app training log matches the console output.

    Scoped to the training thread (one job runs at a time, but inference may
    log on `pollinator.*` from another thread concurrently) and fail-safe:
    a logging error must never abort training."""

    # Min seconds between DB flushes. Buffering avoids a write per log line,
    # which on SQLite would lock the DB and starve the UI's status polls.
    _FLUSH_INTERVAL = 2.0

    def __init__(self, job_id: int, thread_ident: int):
        super().__init__(level=logging.INFO)
        self.job_id = job_id
        self.thread_ident = thread_ident
        self._buffer: list[dict] = []
        self._last_flush = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        if threading.get_ident() != self.thread_ident:
            return
        try:
            # Trim only blank leading/trailing lines; keep interior spacing so
            # the trainers' aligned tables (right-padded columns) render right
            # in the monospace log panel.
            message = record.getMessage().strip('\n')
            if not message.strip():
                return
            self._buffer.append(
                {
                    'time': timezone.now().isoformat(),
                    'message': message,
                    'level': record.levelname.lower(),
                }
            )
            import time as _time

            if _time.monotonic() - self._last_flush >= self._FLUSH_INTERVAL:
                self.flush()
        except Exception:
            pass

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            import time as _time

            job = TrainingJob.objects.get(pk=self.job_id)
            log = list(job.activity_log or [])
            log.extend(self._buffer)
            job.activity_log = log[-_ACTIVITY_LOG_CAP:]
            job.save(update_fields=['activity_log'])
            self._buffer.clear()
            self._last_flush = _time.monotonic()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────
# Dataset construction
# ──────────────────────────────────────────────────────────────────────────


def _export_crop(detection: Detection, dst_path: Path) -> bool:  # pragma: no cover
    """Crop the detection bbox out of its source image, save as JPG.
    Returns True on success; False if the source file or bbox is invalid.

    Bbox shape matches what the pipeline writes (see apps/analysis/crops.py
    and ml-pipelines/pollinator/workflows/merge.py): {x1, y1, x2, y2, w, h}.
    Missing or malformed keys fail fast rather than silently degrading to
    a (0,0,w,h) top-left crop."""
    if not detection.image.file:
        return False
    bbox = detection.bbox or {}
    try:
        x1 = float(bbox['x1'])
        y1 = float(bbox['y1'])
        x2 = float(bbox['x2'])
        y2 = float(bbox['y2'])
    except (KeyError, TypeError, ValueError):
        return False
    if x2 <= x1 or y2 <= y1:
        return False
    src = Path(detection.image.file.path)
    with Image.open(src) as img:
        crop = img.crop((x1, y1, x2, y2)).convert('RGB')
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dst_path, 'JPEG')
    return True


def _stratified_image_split(
    images_by_dominant: dict, splits: dict, seed: int = 42
) -> tuple[list, list, list]:
    """Per-class image-level split. Returns (train, val, test) lists of image ids."""
    rng = random.Random(seed)
    train, val, test = [], [], []
    for ids in images_by_dominant.values():
        ids = list(ids)
        rng.shuffle(ids)
        n = len(ids)
        n_test = max(1, n * splits['test'] // 100) if n > 2 else 0
        n_val = max(1, n * splits['val'] // 100) if n > 2 else 0
        n_train = n - n_test - n_val
        train.extend(ids[:n_train])
        val.extend(ids[n_train : n_train + n_val])
        test.extend(ids[n_train + n_val :])
    return train, val, test


def _effective_class(d: Detection) -> str:
    """Reviewer-corrected label if set, else the model's original prediction.
    Used everywhere a detection is being treated as ground truth (eligibility,
    dataset writing, stratification)."""
    return d.reviewer_label or d.predicted_class


def _build_detector_dataset(  # pragma: no cover
    flagged: list, class_filter: list, splits: dict, output_dir: Path
) -> int:
    """Write YOLO-format dataset at output_dir/{images,labels}/{train,val,test}/.
    Returns total number of images written. 0 means nothing matched the filter."""
    class_to_idx = {c: i for i, c in enumerate(class_filter)}

    # Group detections by image (multi-detection images get one label file).
    # Uses the reviewer's corrected label when present so YOLO trains on the
    # ground-truth class, not the model's original (possibly wrong) guess.
    by_image: dict = defaultdict(list)
    for d in flagged:
        if _effective_class(d) not in class_to_idx:
            continue
        by_image[d.image_id].append(d)

    if not by_image:
        return 0

    # Stratify per-image by dominant class for the split.
    images_by_dominant: dict = defaultdict(list)
    for image_id, dets in by_image.items():
        counts: dict = defaultdict(int)
        for d in dets:
            counts[_effective_class(d)] += 1
        dominant = max(counts.items(), key=lambda kv: kv[1])[0]
        images_by_dominant[dominant].append(image_id)

    train, val, test = _stratified_image_split(images_by_dominant, splits)
    split_map = {'train': train, 'val': val, 'test': test}

    written = 0
    for split, image_ids in split_map.items():
        img_dir = output_dir / 'images' / split
        lbl_dir = output_dir / 'labels' / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for image_id in image_ids:
            dets = by_image[image_id]
            image = dets[0].image
            if not image.file:
                continue
            src = Path(image.file.path)

            with Image.open(src) as img:
                width, height = img.size

            stem = f'img_{image_id}'
            dst_img = img_dir / f'{stem}.jpg'
            if not dst_img.exists():
                link_or_copy(src, dst_img)

            lines = []
            for d in dets:
                cls_idx = class_to_idx[_effective_class(d)]
                bbox = d.bbox or {}
                try:
                    x1 = float(bbox['x1'])
                    y1 = float(bbox['y1'])
                    x2 = float(bbox['x2'])
                    y2 = float(bbox['y2'])
                except (KeyError, TypeError, ValueError):
                    continue
                if x2 <= x1 or y2 <= y1:
                    continue
                w = x2 - x1
                h = y2 - y1
                cx = (x1 + w / 2) / width
                cy = (y1 + h / 2) / height
                lines.append(
                    f'{cls_idx} {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}'
                )
            (lbl_dir / f'{stem}.txt').write_text('\n'.join(lines) + '\n')
            written += 1

    return written


def _build_classifier_dataset(  # pragma: no cover
    flagged: list,
    output_dir: Path,
    class_filter: list,
    background_detections: Optional[list] = None,
) -> int:
    """Write classifier dataset under output_dir/<class>/<id>.jpg (+ background/ if given).
    Returns total number of crops written. Uses reviewer_label when set so
    corrected detections land in the right class folder."""
    n = 0
    for d in flagged:
        cls = _effective_class(d)
        if cls not in class_filter:
            continue
        if _export_crop(d, output_dir / cls / f'det_{d.id}.jpg'):
            n += 1
    if background_detections:
        for d in background_detections:
            if _export_crop(d, output_dir / 'background' / f'det_{d.id}.jpg'):
                n += 1
    return n


# ──────────────────────────────────────────────────────────────────────────
# Main job runner
# ──────────────────────────────────────────────────────────────────────────


def _validate_config(config: dict) -> tuple[str, int, list, dict, int]:
    """Pull and validate fields from job.config. Raises ValueError on bad input.
    Returns: (track, from_model_version_id, class_filter, splits, epochs)."""
    track = config.get('track')
    from_id = config.get('from_model_version_id')
    if not track or not from_id:
        raise ValueError('config requires track and from_model_version_id')
    if track not in PER_TRACK_DEFAULTS:
        raise ValueError(f'unknown track: {track}')

    splits = {
        'train': int(config.get('train_split', 80)),
        'val': int(config.get('val_split', 20)),
        'test': int(config.get('test_split', 0)),
    }
    if splits['train'] + splits['val'] + splits['test'] != 100:
        raise ValueError('train_split + val_split + test_split must equal 100')
    if splits['train'] <= 0 or splits['val'] <= 0:
        raise ValueError('train_split and val_split must both be positive')

    class_filter = config.get('class_filter') or POLLINATOR_CLASSES
    if not class_filter:
        raise ValueError('class_filter must be non-empty')

    epochs = int(config.get('epochs') or PER_TRACK_DEFAULTS[track]['epochs'])
    if epochs <= 0:
        raise ValueError('epochs must be positive')

    return track, int(from_id), list(class_filter), splits, epochs


def _lineage_model_ids(source_model: Optional[ModelVersion]) -> list[int]:
    """ModelVersion ids in source_model's ancestry chain, including itself,
    walked via the source_model_version FK. Empty for a None source."""
    ids: list[int] = []
    seen: set[int] = set()
    mv = source_model
    while mv is not None and mv.pk not in seen:
        seen.add(mv.pk)
        ids.append(mv.pk)
        mv = mv.source_model_version
    return ids


def _consumed_detection_ids(source_model: Optional[ModelVersion]) -> set[int]:
    """Detection IDs already consumed by completed training jobs in
    source_model's ancestry chain (lineage), whose resulting model still
    exists.

    Lineage-scoped, not track-global: fine-tuning a model excludes only what
    that model's own ancestry already trained on, so a fresh/unrelated base
    model (no ancestry, e.g. a manual upload) starts with the full pool
    available. A None source therefore consumes nothing.

    resulting_model is SET_NULL on delete, and a deleted model also drops out
    of any descendant's ancestry chain, so deleting a model releases its
    detections back into the pool."""
    lineage_ids = _lineage_model_ids(source_model)
    if not lineage_ids:
        return set()
    return set(
        TrainingJob.objects.filter(
            module=Module.POLLINATORS,
            status=JobStatus.COMPLETED,
            resulting_model_id__in=lineage_ids,
        ).values_list('training_detections__id', flat=True)
    ) - {None}


def _collect_detector_pool(
    class_filter: list,
    source_model: Optional[ModelVersion],
    exclude_image_ids: Optional[set[int]] = None,
) -> list:
    """YOLO eligibility: images where every Detection has status != PENDING.
    Returns the ACCEPTED detections on those images as bbox labels (rejected
    detections on the same image are ignored — they're already false
    positives the reviewer flagged out). Excludes detections already consumed
    by source_model's lineage, and any images the user deselected in the pool
    drawer (the detector's training unit is the image, so exclusions are by
    image id)."""
    consumed = _consumed_detection_ids(source_model)
    exclude_image_ids = exclude_image_ids or set()
    images_with_pending = set(
        Detection.objects.filter(
            inference_run__module=Module.POLLINATORS,
            status=DetectionStatus.PENDING,
        ).values_list('image_id', flat=True)
    )
    qs = (
        Detection.objects.filter(
            inference_run__module=Module.POLLINATORS,
            status=DetectionStatus.ACCEPTED,
        )
        .exclude(image_id__in=images_with_pending)
        # Opt-in: the detector trains only on images the reviewer explicitly
        # marked "Include in YOLO training".
        .filter(image__include_in_training=True)
        .select_related('image')
    )
    return [
        d
        for d in qs
        if d.id not in consumed
        and d.image_id not in exclude_image_ids
        and (d.reviewer_label or d.predicted_class) in class_filter
    ]


def _collect_binary_pool(
    source_model: Optional[ModelVersion],
    exclude_ids: Optional[set[int]] = None,
    include_excluded: bool = False,
) -> tuple[list, list]:
    """Binary eligibility: accepted (insect) + rejected (background).
    Excludes detections already consumed by source_model's lineage, and any
    detections the user deselected in the pool drawer (by detection id). Crops
    flagged exclude_from_training are dropped for actual training; the pool
    drawer passes include_excluded=True so they still render (greyed)."""
    consumed = _consumed_detection_ids(source_model)
    exclude_ids = exclude_ids or set()

    def base(detection_status):
        qs = Detection.objects.filter(
            inference_run__module=Module.POLLINATORS,
            status=detection_status,
        )
        if not include_excluded:
            qs = qs.exclude(exclude_from_training=True)
        return qs.select_related('image')

    accepted = [
        d
        for d in base(DetectionStatus.ACCEPTED)
        if d.id not in consumed and d.id not in exclude_ids
    ]
    rejected = [
        d
        for d in base(DetectionStatus.REJECTED)
        if d.id not in consumed and d.id not in exclude_ids
    ]
    return accepted, rejected


def _collect_group_pool(
    class_filter: list,
    source_model: Optional[ModelVersion],
    exclude_ids: Optional[set[int]] = None,
    include_excluded: bool = False,
) -> list:
    """Group eligibility: accepted detections only; class comes from
    reviewer_label (if corrected) or predicted_class. Excludes detections
    already consumed by source_model's lineage, and any detections the user
    deselected in the pool drawer (by detection id). Crops flagged
    exclude_from_training are dropped for actual training; the pool drawer
    passes include_excluded=True so they still render (greyed)."""
    consumed = _consumed_detection_ids(source_model)
    exclude_ids = exclude_ids or set()
    qs = Detection.objects.filter(
        inference_run__module=Module.POLLINATORS,
        status=DetectionStatus.ACCEPTED,
    )
    if not include_excluded:
        qs = qs.exclude(exclude_from_training=True)
    qs = qs.select_related('image')
    return [
        d
        for d in qs
        if d.id not in consumed
        and d.id not in exclude_ids
        and (d.reviewer_label or d.predicted_class) in class_filter
    ]


def _next_version_name(track: str) -> str:
    """e.g. 'detector-v4' — one more than the highest existing for this kind."""
    kind = PER_TRACK_DEFAULTS[track]['kind']
    n = ModelVersion.objects.filter(module=Module.POLLINATORS, kind=kind).count() + 1
    return f'{track}-v{n}'


def _train_detector(  # pragma: no cover
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    class_filter: list,
    config: dict,
    epochs: int,
    progress_cb: ProgressCallback,
) -> tuple[str, dict, dict]:
    """Run YOLO incremental fine-tune. Returns (weights_path, metrics, parameters)."""
    from pollinator.workflows.training_yolo import retrain_yolo

    defaults = PER_TRACK_DEFAULTS['detector']
    tile_cfg = _resolve_tile_config(source, config)

    img_size = (
        int(tile_cfg['tile_size'])
        if tile_cfg['use_tiles']
        else int(
            config.get('img_size')
            or (source.parameters or {}).get('img_size')
            or defaults['img_size']
        )
    )
    if img_size % 32 != 0:
        raise ValueError(f'img_size must be a multiple of 32, got {img_size}')

    result = retrain_yolo(
        dataset_root=str(dataset_dir),
        output_dir=str(weights_dir),
        use_tiles=tile_cfg['use_tiles'],
        tile_size=tile_cfg['tile_size'],
        overlap=tile_cfg['overlap'],
        min_area=tile_cfg['min_area'],
        keep_empty_tiles=tile_cfg['keep_empty_tiles'],
        img_size=img_size,
        model_size=str(resolve_model_path(source.model_file_path)),
        batch=defaults['batch'],
        seed=42,
        epochs_stage1=0,  # incremental: skip frozen-backbone stage
        epochs_stage2=epochs,
        lr_stage2=defaults['lr'],
        patience_s2=defaults['patience'],
        copy_paste=defaults['copy_paste'],
        mixup=defaults['mixup'],
        mosaic=defaults['mosaic'],
        classes=class_filter,
        progress_callback=progress_cb,
    )
    weights_path = str(weights_dir / 'stage2_finetune' / 'weights' / 'best.pt')
    metrics = {
        'val': result.get('val_metrics', {}),
        'test': result.get('test_metrics', {}),
    }
    # Hyperparameters (yolo_imgsz/epochs/lr0/batch/...) are merged in after
    # training from the run's args.yaml, matching the manual-upload path so
    # both model cards expose identical fields. Keep only the
    # incremental-specific context here.
    parameters = {
        'source_model_version_id': source.pk,
        'class_filter': class_filter,
        'mode': 'incremental',
        'tile_config': tile_cfg,
    }
    return weights_path, metrics, parameters


def _train_binary(  # pragma: no cover
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    splits: dict,
    epochs: int,
    progress_cb: ProgressCallback,
) -> tuple[str, dict, dict]:
    from pollinator.workflows.training_binary import retrain_binary as train_binary

    defaults = PER_TRACK_DEFAULTS['binary']
    result = train_binary(
        data_dirs=[str(dataset_dir)],
        model_type='efficientnet',
        resume_from=str(resolve_model_path(source.model_file_path)),
        output_dir=str(weights_dir),
        epochs=epochs,
        batch=defaults['batch'],
        lr=defaults['lr'],
        val_frac=splits['val'] / 100,
        test_frac=splits['test'] / 100,
        seed=42,
        progress_callback=progress_cb,
    )
    weights_path = str(weights_dir / 'efficientnet_binary_best.pth')
    parameters = {
        'img_size': result.get('img_size', defaults['img_size']),
        'epochs': epochs,
        'lr': defaults['lr'],
        'batch': defaults['batch'],
        'source_model_version_id': source.pk,
        'mode': 'incremental',
    }
    return weights_path, result, parameters


def _train_group(  # pragma: no cover
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    splits: dict,
    epochs: int,
    progress_cb: ProgressCallback,
) -> tuple[str, dict, dict]:
    from pollinator.workflows.training_group import retrain_group as train_group

    defaults = PER_TRACK_DEFAULTS['group']
    result = train_group(
        data_dirs=[str(dataset_dir)],
        web_dir=None,  # incremental: no web mixing
        model_type='insectnet',
        resume_from=str(resolve_model_path(source.model_file_path)),
        unfreeze_last_block=defaults['unfreeze_last_block'],
        output_dir=str(weights_dir),
        epochs_s1=0,  # incremental: skip stage 1
        epochs_s2=epochs,
        batch=defaults['batch'],
        lr_s2=defaults['lr'],
        val_frac=splits['val'] / 100,
        test_frac=splits['test'] / 100,
        seed=42,
        progress_callback=progress_cb,
    )
    weights_path = str(weights_dir / 'group_insectnet_best.pth')
    parameters = {
        'img_size': result.get('img_size', defaults['img_size']),
        'epochs': epochs,
        'lr': defaults['lr'],
        'batch': defaults['batch'],
        'source_model_version_id': source.pk,
        'mode': 'incremental',
    }
    return weights_path, result, parameters


def run_training_job(job: TrainingJob) -> None:  # pragma: no cover
    """Synchronous core. Status flow: pending → running → completed / failed."""
    import time

    # Declared up front so the finally block can clean it up even if the
    # job fails before dataset assembly. Trained weights live in weights_dir
    # (sibling of dataset_dir), so this cleanup never touches them.
    dataset_dir: Optional[Path] = None
    # Staged user-uploaded detector dataset (if any); removed in finally.
    uploaded_dir: Optional[Path] = None

    # Mirror ml-pipeline INFO logs into the job's activity_log for the live UI
    # log. Attached to the `pollinator` logger root; detached in finally.
    pipeline_logger = logging.getLogger('pollinator')
    log_handler = _ActivityLogHandler(job.pk, threading.get_ident())
    pipeline_logger.addHandler(log_handler)

    try:
        job.status = JobStatus.RUNNING
        job.save(update_fields=['status'])

        config = job.config or {}
        track, from_id, class_filter, splits, epochs = _validate_config(config)
        train_started_monotonic = time.monotonic()

        source = ModelVersion.objects.get(pk=from_id)

        # Samples the user deselected in the pool drawer. Detector ids are
        # image ids (its training unit); classifier ids are detection ids.
        excluded_ids: set[int] = set()
        for x in config.get('excluded_sample_ids') or []:
            try:
                excluded_ids.add(int(x))
            except (TypeError, ValueError):
                pass

        # Collect detections — per-track eligibility + consumption guard.
        # `consumed_detections` is the exact set we stamp onto the job's
        # training_detections M2M after a successful run; it can include
        # rejected detections (binary background) too.
        if track == 'detector':
            eligible = _collect_detector_pool(class_filter, source, excluded_ids)
            consumed_detections = eligible
            token = config.get('uploaded_detector_token')
            if token:
                from .detector_upload import staging_dir_for

                uploaded_dir = staging_dir_for(token)
                if uploaded_dir is None:
                    raise ValueError(
                        f'uploaded detector dataset {token!r} not found or expired; '
                        f're-upload before starting the job'
                    )
        elif track == 'binary':
            accepted, rejected = _collect_binary_pool(source, excluded_ids)
            if not accepted:
                raise ValueError('No accepted detections available for binary training')
            if not rejected:
                raise ValueError('No rejected detections available as background')
            eligible = accepted  # for image_count / class subdirs
            consumed_detections = accepted + rejected
        else:  # group
            eligible = _collect_group_pool(class_filter, source, excluded_ids)
            consumed_detections = eligible

        # An uploaded dataset is sufficient on its own for the detector track,
        # so only block when there's neither reviewed data nor an upload.
        if not eligible and uploaded_dir is None:
            raise ValueError(
                f'No new data available for {track} retraining — either everything '
                f'is already consumed by previous training, or no detections match '
                f'the selected class filter.'
            )

        job.image_count = len({d.image_id for d in eligible})
        job.total_epochs = epochs
        job.save(update_fields=['image_count', 'total_epochs'])

        # Build dataset
        output_root = Path(settings.MEDIA_ROOT) / 'training' / str(job.pk)
        dataset_dir = output_root / 'dataset'
        weights_dir = output_root / 'weights'
        weights_dir.mkdir(parents=True, exist_ok=True)

        if track == 'detector':
            n = _build_detector_dataset(eligible, class_filter, splits, dataset_dir)
            if uploaded_dir is not None:
                from .detector_upload import merge_uploaded_into_dataset

                n += merge_uploaded_into_dataset(
                    uploaded_dir, dataset_dir, class_filter, splits
                )
                job.image_count = n
                job.save(update_fields=['image_count'])
            if n == 0:
                raise ValueError('Detector dataset build produced 0 images')
            weights_path, metrics, parameters = _train_detector(
                source,
                dataset_dir,
                weights_dir,
                class_filter,
                config,
                epochs,
                _make_progress_callback(job.pk),
            )
        elif track == 'binary':
            n = _build_classifier_dataset(
                accepted,  # noqa: F821 — defined in the branch above
                dataset_dir,
                POLLINATOR_CLASSES,
                background_detections=rejected,  # noqa: F821
            )
            if n == 0:
                raise ValueError('Binary classifier dataset build produced 0 crops')
            weights_path, metrics, parameters = _train_binary(
                source,
                dataset_dir,
                weights_dir,
                splits,
                epochs,
                _make_progress_callback(job.pk),
            )
        else:  # group
            n = _build_classifier_dataset(eligible, dataset_dir, class_filter)
            if n == 0:
                raise ValueError('Group classifier dataset build produced 0 crops')
            weights_path, metrics, parameters = _train_group(
                source,
                dataset_dir,
                weights_dir,
                splits,
                epochs,
                _make_progress_callback(job.pk),
            )

        train_duration = int(time.monotonic() - train_started_monotonic)
        finished_at = timezone.now()

        # Persist new ModelVersion + finalise job + stamp consumed detections
        # so future runs of the same track exclude them.
        # Honour a user-supplied name when given and free; otherwise auto-name.
        # Falling back on collision avoids failing a finished training run just
        # because the chosen name was taken between submit and completion.
        desired_name = (config.get('version_name') or '').strip()
        if (
            not desired_name
            or ModelVersion.objects.filter(version_name=desired_name).exists()
        ):
            desired_name = _next_version_name(track)

        with transaction.atomic():
            new_mv = ModelVersion.objects.create(
                module=Module.POLLINATORS,
                kind=PER_TRACK_DEFAULTS[track]['kind'],
                version_name=desired_name,
                model_file_path=weights_path,
                description=f'Incremental retrain of {source.version_name}',
                metrics=metrics,
                parameters=parameters,
                source_model_version=source,
                sample_count=len(consumed_detections),
                training_duration_seconds=train_duration,
                trained_at=finished_at,
                is_active=False,
                created_by=job.initiated_by,
            )
            job.resulting_model = new_mv
            job.status = JobStatus.COMPLETED
            job.completed_at = finished_at
            job.metrics = metrics
            job.save(
                update_fields=[
                    'resulting_model',
                    'status',
                    'completed_at',
                    'metrics',
                ]
            )
            job.training_detections.set(consumed_detections)

        # Capture run outputs (confusion matrix, curves, metrics) as
        # ModelArtifact rows + a clean metrics map for every track, so all
        # model cards are equally rich. The detector reads the Ultralytics
        # stage2_finetune dir (results.csv + args.yaml + plots); the
        # classifiers read the trainer's output dir (*_results.json +
        # confusion_matrix.png). Parsed metrics replace the model card's
        # metrics; the job keeps its original (nested/raw) metrics for history.
        # Capture run_dir BEFORE moving the weights file, since the dir is
        # derived from the weights path.
        from apps.analysis.artifacts import ingest_run_dir

        if track == 'detector':
            run_dir = Path(weights_path).parent.parent  # .../stage2_finetune
        else:
            run_dir = Path(weights_path).parent  # classifier output dir
        ingested, run_metrics, run_params = ingest_run_dir(new_mv, run_dir)

        # Move weights into the canonical models/<module>/<id>/weights<ext>
        # location and update the row. The training/<job_pk>/ tree is wiped
        # by the finally block below; weights need to be out of it first.
        weights_src = Path(weights_path)
        ext = weights_src.suffix or '.pt'
        canonical = move_weights_into_place(
            weights_src, Module.POLLINATORS, new_mv.id, ext
        )
        new_mv.model_file_path = str(canonical)
        new_mv.save(update_fields=['model_file_path'])
        update_fields: list[str] = []
        if run_metrics:
            new_mv.metrics = run_metrics
            update_fields.append('metrics')
        if run_params:
            new_mv.parameters = {**(new_mv.parameters or {}), **run_params}
            update_fields.append('parameters')
        if update_fields:
            new_mv.save(update_fields=update_fields)
        logger.info(
            f'TrainingJob {job.pk}: ingested {ingested} artifact(s) for '
            f'ModelVersion {new_mv.pk}'
        )

        logger.info(f'TrainingJob {job.pk} completed → ModelVersion {new_mv.pk}')

    except RunCancelled:
        # Status is already CANCELLED. No ModelVersion was created and no
        # training_detections were stamped (both happen inside the atomic
        # block after the ML work completes). Clean stop, not a failure.
        logger.info(f'TrainingJob {job.pk} cancelled by user')
        job.completed_at = timezone.now()
        job.save(update_fields=['completed_at'])
    except Exception as e:
        logger.exception(f'TrainingJob {job.pk} failed')
        job.status = JobStatus.FAILED
        job.error_message = f'{type(e).__name__}: {e}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at'])
        raise
    finally:
        log_handler.flush()  # persist any buffered log lines
        pipeline_logger.removeHandler(log_handler)
        if uploaded_dir is not None:
            shutil.rmtree(uploaded_dir, ignore_errors=True)
        if dataset_dir is not None:
            # Successful runs already moved weights into the canonical
            # models/<module>/<id>/ location, so the entire training/<job_pk>/
            # tree (dataset, tiled slices, leftover Ultralytics run outputs)
            # is disposable. On failure before the move we lose the
            # intermediate weights too, but a failed run produced no
            # ModelVersion that depends on them.
            shutil.rmtree(dataset_dir.parent, ignore_errors=True)


def _run_in_thread(job_id: int) -> None:  # pragma: no cover
    try:
        job = TrainingJob.objects.get(pk=job_id)
        run_training_job(job)
    except TrainingJob.DoesNotExist:
        logger.error(f'Training thread: job {job_id} not found')
    except Exception:
        logger.exception(f'Training thread {job_id} crashed')
    finally:
        close_old_connections()


def spawn_training_job(job: TrainingJob) -> None:  # pragma: no cover
    """Start a daemon thread that runs the training for the given job."""
    threading.Thread(
        target=_run_in_thread,
        args=(job.pk,),
        daemon=True,
        name=f'train-{job.pk}',
    ).start()

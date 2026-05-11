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
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional

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
from apps.analysis.storage import resolve_model_path
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


# ──────────────────────────────────────────────────────────────────────────
# Progress reporting
# ──────────────────────────────────────────────────────────────────────────


def _make_progress_callback(job_id: int):
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


# ──────────────────────────────────────────────────────────────────────────
# Dataset construction
# ──────────────────────────────────────────────────────────────────────────


def _export_crop(detection: Detection, dst_path: Path) -> bool:
    """Crop the detection bbox out of its source image, save as JPG.
    Returns True on success; False if the source file or bbox is invalid."""
    if not detection.image.file:
        return False
    src = Path(detection.image.file.path)
    bbox = detection.bbox or {}
    x = float(bbox.get('x', 0))
    y = float(bbox.get('y', 0))
    w = float(bbox.get('w', 0))
    h = float(bbox.get('h', 0))
    if w <= 0 or h <= 0:
        return False
    with Image.open(src) as img:
        crop = img.crop((x, y, x + w, y + h)).convert('RGB')
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


def _build_detector_dataset(
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
                dst_img.symlink_to(src)

            lines = []
            for d in dets:
                cls_idx = class_to_idx[_effective_class(d)]
                bbox = d.bbox or {}
                x = float(bbox.get('x', 0))
                y = float(bbox.get('y', 0))
                w = float(bbox.get('w', 0))
                h = float(bbox.get('h', 0))
                if w <= 0 or h <= 0:
                    continue
                cx = (x + w / 2) / width
                cy = (y + h / 2) / height
                lines.append(
                    f'{cls_idx} {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}'
                )
            (lbl_dir / f'{stem}.txt').write_text('\n'.join(lines) + '\n')
            written += 1

    return written


def _build_classifier_dataset(
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
        'val': int(config.get('val_split', 10)),
        'test': int(config.get('test_split', 10)),
    }
    if splits['train'] + splits['val'] + splits['test'] != 100:
        raise ValueError('train_split + val_split + test_split must equal 100')

    class_filter = config.get('class_filter') or POLLINATOR_CLASSES
    if not class_filter:
        raise ValueError('class_filter must be non-empty')

    epochs = int(config.get('epochs') or PER_TRACK_DEFAULTS[track]['epochs'])
    if epochs <= 0:
        raise ValueError('epochs must be positive')

    return track, int(from_id), list(class_filter), splits, epochs


def _consumed_detection_ids(track: str) -> set[int]:
    """Detection IDs already used in a successfully-completed training job
    for this track. Pulled across all jobs and unioned."""
    return set(
        TrainingJob.objects.filter(
            module=Module.POLLINATORS,
            status=JobStatus.COMPLETED,
            config__track=track,
        ).values_list('training_detections__id', flat=True)
    ) - {None}


def _collect_detector_pool(class_filter: list) -> list:
    """YOLO eligibility: images where every Detection has status != PENDING.
    Returns the ACCEPTED detections on those images as bbox labels (rejected
    detections on the same image are ignored — they're already false
    positives the reviewer flagged out)."""
    consumed = _consumed_detection_ids('detector')
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
        .select_related('image')
    )
    if class_filter:
        # Use reviewer_label when set, else predicted_class.
        # Filter applied client-side because the right field varies per row.
        pass
    return [
        d
        for d in qs
        if d.id not in consumed
        and (d.reviewer_label or d.predicted_class) in class_filter
    ]


def _collect_binary_pool() -> tuple[list, list]:
    """Binary eligibility: accepted (insect) + rejected (background)."""
    consumed = _consumed_detection_ids('binary')
    accepted = [
        d
        for d in Detection.objects.filter(
            inference_run__module=Module.POLLINATORS,
            status=DetectionStatus.ACCEPTED,
        ).select_related('image')
        if d.id not in consumed
    ]
    rejected = [
        d
        for d in Detection.objects.filter(
            inference_run__module=Module.POLLINATORS,
            status=DetectionStatus.REJECTED,
        ).select_related('image')
        if d.id not in consumed
    ]
    return accepted, rejected


def _collect_group_pool(class_filter: list) -> list:
    """Group eligibility: accepted detections only; class comes from
    reviewer_label (if corrected) or predicted_class."""
    consumed = _consumed_detection_ids('group')
    qs = Detection.objects.filter(
        inference_run__module=Module.POLLINATORS,
        status=DetectionStatus.ACCEPTED,
    ).select_related('image')
    return [
        d
        for d in qs
        if d.id not in consumed
        and (d.reviewer_label or d.predicted_class) in class_filter
    ]


def _next_version_name(track: str) -> str:
    """e.g. 'detector-v4' — one more than the highest existing for this kind."""
    kind = PER_TRACK_DEFAULTS[track]['kind']
    n = ModelVersion.objects.filter(module=Module.POLLINATORS, kind=kind).count() + 1
    return f'{track}-v{n}'


def _train_detector(
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    class_filter: list,
    config: dict,
    epochs: int,
    progress_cb,
) -> tuple[str, dict, dict]:
    """Run YOLO incremental fine-tune. Returns (weights_path, metrics, parameters)."""
    from pollinator.training.train_yolo import train_yolo

    defaults = PER_TRACK_DEFAULTS['detector']
    img_size = int(
        config.get('img_size')
        or (source.parameters or {}).get('img_size')
        or defaults['img_size']
    )
    if img_size % 32 != 0:
        raise ValueError(f'img_size must be a multiple of 32, got {img_size}')

    result = train_yolo(
        dataset_root=str(dataset_dir),
        output_dir=str(weights_dir),
        model_size=str(resolve_model_path(source.model_file_path)),
        img_size=img_size,
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
    parameters = {
        'img_size': img_size,
        'epochs': epochs,
        'lr': defaults['lr'],
        'batch': defaults['batch'],
        'source_model_version_id': source.pk,
        'class_filter': class_filter,
        'mode': 'incremental',
    }
    return weights_path, metrics, parameters


def _train_binary(
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    splits: dict,
    epochs: int,
    progress_cb,
) -> tuple[str, dict, dict]:
    from pollinator.training.train_binary import train_binary

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


def _train_group(
    source: ModelVersion,
    dataset_dir: Path,
    weights_dir: Path,
    splits: dict,
    epochs: int,
    progress_cb,
) -> tuple[str, dict, dict]:
    from pollinator.training.train_group import train_group

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


def run_training_job(job: TrainingJob) -> None:
    """Synchronous core. Status flow: pending → running → completed / failed."""
    import time

    try:
        job.status = JobStatus.RUNNING
        job.save(update_fields=['status'])

        config = job.config or {}
        track, from_id, class_filter, splits, epochs = _validate_config(config)
        train_started_monotonic = time.monotonic()

        source = ModelVersion.objects.get(pk=from_id)

        # Collect detections — per-track eligibility + consumption guard.
        # `consumed_detections` is the exact set we stamp onto the job's
        # training_detections M2M after a successful run; it can include
        # rejected detections (binary background) too.
        if track == 'detector':
            eligible = _collect_detector_pool(class_filter)
            consumed_detections = eligible
        elif track == 'binary':
            accepted, rejected = _collect_binary_pool()
            if not accepted:
                raise ValueError('No accepted detections available for binary training')
            if not rejected:
                raise ValueError('No rejected detections available as background')
            eligible = accepted  # for image_count / class subdirs
            consumed_detections = accepted + rejected
        else:  # group
            eligible = _collect_group_pool(class_filter)
            consumed_detections = eligible

        if not eligible:
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
        with transaction.atomic():
            new_mv = ModelVersion.objects.create(
                module=Module.POLLINATORS,
                kind=PER_TRACK_DEFAULTS[track]['kind'],
                version_name=_next_version_name(track),
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


def _run_in_thread(job_id: int) -> None:
    try:
        job = TrainingJob.objects.get(pk=job_id)
        run_training_job(job)
    except TrainingJob.DoesNotExist:
        logger.error(f'Training thread: job {job_id} not found')
    except Exception:
        logger.exception(f'Training thread {job_id} crashed')
    finally:
        close_old_connections()


def spawn_training_job(job: TrainingJob) -> None:
    """Start a daemon thread that runs the training for the given job."""
    threading.Thread(
        target=_run_in_thread,
        args=(job.pk,),
        daemon=True,
        name=f'train-{job.pk}',
    ).start()

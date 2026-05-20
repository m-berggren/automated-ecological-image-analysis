"""Execution of the pollinator inference pipeline.

The Django worker drives the ML pipeline one image at a time. After every
image we persist any detections it produced, write per-detection crops,
bump ``processed_image_count`` on the run, and check whether the row has
been flipped to ``paused``/``cancelled`` by the user.

``run_inference_pipeline`` is the synchronous core. ``spawn_inference_pipeline``
wraps it in a daemon thread for HTTP-triggered runs. The threading model is
fine for development. In production swap for a persistent queue (Celery / RQ)
without changing the body of run_inference_pipeline.
"""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import close_old_connections
from django.utils import timezone
from PIL import Image

from apps.analysis.cancellation import RunCancelled
from apps.analysis.models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    ModelVersion,
)
from apps.analysis.storage import resolve_model_path

from .models import PollinatorDetection
from .training import canonical_class

logger = logging.getLogger(__name__)


_ACTIVITY_LOG_CAP = 200


class RunPaused(BaseException):
    """Raised between images when the run's status is flipped to PAUSED.

    Like ``RunCancelled``, inherits from ``BaseException`` so it bypasses
    bare ``except Exception:`` blocks inside the ML code and lands at the
    worker's own pause handler.
    """


def _peek_status(run_id: int) -> str | None:
    return (
        InferenceRun.objects.filter(pk=run_id).values_list('status', flat=True).first()
    )


def _append_log(run_id: int, message: str, level: str = 'info') -> None:
    """Append one entry to the run's activity_log (capped at the latest 200).

    The polling UI on PollinatorsDetect reads activity_log in newest-first
    order, so it's safe to keep this best-effort: a failed update logs and
    continues rather than aborting the run.
    """
    try:
        run = InferenceRun.objects.get(pk=run_id)
        log = list(run.activity_log or [])
        log.append(
            {
                'time': timezone.now().isoformat(),
                'message': message,
                'level': level,
            }
        )
        run.activity_log = log[-_ACTIVITY_LOG_CAP:]
        run.save(update_fields=['activity_log'])
    except Exception:
        logger.exception(f'Activity log write failed for run {run_id}')


def _persist_image_results(
    run: InferenceRun,
    image,
    detections: list[dict],
    crop_dir: Path,
) -> tuple[int, dict, dict]:
    """Write Detection + PollinatorDetection rows + crop files for one image.

    Returns (count, by_class_delta, by_source_delta) so the caller can roll
    them into the run-level aggregates.
    """
    if not detections:
        return 0, {}, {}

    by_class: dict[str, int] = {}
    by_source: dict[str, int] = {}

    # Open the source image once so we can render every crop for this frame
    # without re-decoding the JPEG.
    src_path = Path(image.file.path)
    try:
        src_img = Image.open(src_path)
        src_img.load()
        src_img = src_img.convert('RGB')
    except Exception:
        logger.exception(f'Failed to open source image {src_path}')
        return 0, {}, {}

    image_stem = src_path.stem
    crop_dir.mkdir(parents=True, exist_ok=True)

    # Build the row objects in memory first so we can persist both tables
    # with two bulk_create calls (3 SQL per image total, instead of 3 SQL
    # per detection). Crops are rendered after bulk_create so we have the
    # final Detection pks if anything ever wants them, and one bulk_update
    # writes every crop FileField at the end.
    det_objs: list[Detection] = []
    pol_kwargs: list[dict] = []
    for d in detections:
        bbox = d.get('bbox') or {}
        # Normalize raw model labels (e.g. InsectNet emits 'butterfly_moth')
        # to canonical pollinator classes before they reach the DB.
        yolo_class = canonical_class(d.get('yolo_class')) or ''
        insectnet_class = canonical_class(d.get('insectnet_class')) or ''
        primary_class = yolo_class or insectnet_class
        primary_conf = (
            d.get('yolo_confidence') if yolo_class else d.get('insectnet_confidence')
        )
        det_objs.append(
            Detection(
                inference_run=run,
                image=image,
                bbox=bbox,
                confidence=float(primary_conf or 0.0),
                predicted_class=primary_class,
                area=float(bbox.get('w', 0)) * float(bbox.get('h', 0)),
                status=DetectionStatus.PENDING,
            )
        )
        pol_kwargs.append(
            {
                'yolo_class': yolo_class,
                'yolo_confidence': d.get('yolo_confidence'),
                'insectnet_class': insectnet_class,
                'insectnet_confidence': d.get('insectnet_confidence'),
                'binary_confidence': d.get('binary_confidence'),
                'class_probs': d.get('class_probs') or {},
                'source': d.get('source') or '',
                'merge_iou': d.get('merge_iou'),
            }
        )
        if primary_class:
            by_class[primary_class] = by_class.get(primary_class, 0) + 1
        src_key = d.get('source') or ''
        if src_key:
            by_source[src_key] = by_source.get(src_key, 0) + 1

    created = Detection.objects.bulk_create(det_objs)
    PollinatorDetection.objects.bulk_create(
        [PollinatorDetection(detection=det, **kw) for det, kw in zip(created, pol_kwargs)]
    )

    # Render crops, then one bulk_update writes every FileField name.
    crops_to_update: list[Detection] = []
    for idx, (det, d) in enumerate(zip(created, detections), start=1):
        bbox = d.get('bbox') or {}
        try:
            x1 = float(bbox['x1'])
            y1 = float(bbox['y1'])
            x2 = float(bbox['x2'])
            y2 = float(bbox['y2'])
        except (KeyError, TypeError, ValueError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        try:
            crop_img = src_img.crop((x1, y1, x2, y2))
            buf = io.BytesIO()
            crop_img.save(buf, 'JPEG', quality=85)
            relative_name = (
                f'runs/{run.module}/{run.pk}/crops/{image_stem}_{idx:02d}.jpg'
            )
            saved = default_storage.save(relative_name, ContentFile(buf.getvalue()))
            det.crop.name = saved
            crops_to_update.append(det)
        except Exception:
            logger.exception(f'Failed to write crop for detection {det.pk}')

    if crops_to_update:
        Detection.objects.bulk_update(crops_to_update, ['crop'])

    return len(created), by_class, by_source


def _build_pipeline(run: InferenceRun):
    """Materialise the ML pipeline object for this run.

    Loads model file paths from the run's frozen config, resolves them
    against the storage backend, and instantiates PollinatorInferencePipeline
    with the same knobs the user picked on PollinatorsUpload.
    """
    from pollinator.workflows.inference import PollinatorInferencePipeline

    config = run.config or {}
    yolo_id = (config.get('yolo') or {}).get('model_version_id')
    binary_id = (config.get('binary_classifier') or {}).get('model_version_id')
    group_id = (config.get('group_classifier') or {}).get('model_version_id')
    if not yolo_id or not binary_id or not group_id:
        raise ValueError(
            'Run config must include yolo.model_version_id, '
            'binary_classifier.model_version_id, and '
            'group_classifier.model_version_id'
        )

    yolo_mv = ModelVersion.objects.get(pk=yolo_id)
    binary_mv = ModelVersion.objects.get(pk=binary_id)
    group_mv = ModelVersion.objects.get(pk=group_id)

    yolo_path = resolve_model_path(yolo_mv.model_file_path)
    binary_path = resolve_model_path(binary_mv.model_file_path)
    group_path = resolve_model_path(group_mv.model_file_path)

    prep_config: dict = {}
    if isinstance(config.get('preprocessing'), dict):
        prep_config.update(config['preprocessing'])

    yolo_conf = float((config.get('yolo') or {}).get('confidence', 0.25))
    binary_thr = float((config.get('binary_classifier') or {}).get('confidence', 0.5))
    group_thr = float((config.get('group_classifier') or {}).get('confidence', 0.0))
    iou_thr = float(config.get('iou_threshold', 0.3))

    yolo_tile_cfg = (yolo_mv.parameters or {}).get('tile_config') or {}
    yolo_slice_size = int(yolo_tile_cfg.get('tile_size', 640))
    yolo_overlap = float(yolo_tile_cfg.get('overlap', 0.2))

    return PollinatorInferencePipeline(
        yolo_model=str(yolo_path),
        binary_model=str(binary_path),
        group_model=str(group_path),
        config=prep_config,
        yolo_confidence=yolo_conf,
        yolo_slice_size=yolo_slice_size,
        yolo_overlap=yolo_overlap,
        binary_threshold=binary_thr,
        group_threshold=group_thr,
        iou_threshold=iou_thr,
    )


def run_inference_pipeline(run: InferenceRun) -> None:
    """Run the pollinator pipeline for one InferenceRun, persist results.

    Status flow: pending -> running -> completed / paused / cancelled / failed.

    The per-image checkpoint (``processed_image_count`` + per-image detection
    rows) means a paused run can resume by reading ``processed_image_count``
    and skipping that many images.
    """
    try:
        run.status = JobStatus.RUNNING
        if run.started_at is None:
            run.started_at = timezone.now()
        run.save(update_fields=['status', 'started_at'])

        upload = run.upload
        if upload is None:
            raise ValueError('Run has no upload; cannot determine image set')

        # Order by EXIF capture time so the per-image loop matches the
        # camera's chronological sequence (background-subtraction needs
        # adjacent frames in time, not adjacent uploads). id is a stable
        # tiebreaker for images whose EXIF is missing or duplicated.
        images = list(
            upload.images.all().order_by('captured_at', 'id'),
        )
        if not images:
            raise ValueError('Upload has no images to process')

        # 1-based start_at_image from the UI; clamp to the available range.
        config = run.config or {}
        start_at = int(config.get('start_at_image', 1) or 1)
        start_at = max(1, start_at)
        # Resume from wherever the loop last checkpointed if that's further
        # along than the user's start_at_image.
        resume_from = max(start_at, run.processed_image_count + 1)

        run.image_count = len(images)
        run.save(update_fields=['image_count'])

        _append_log(
            run.pk,
            f'Starting run on {len(images)} images (from image {resume_from}).',
        )

        _append_log(run.pk, 'Loading models…')
        pipeline = _build_pipeline(run)

        # Prime against the full sorted image set so background sampling is
        # representative even when we're resuming mid-sequence.
        image_paths = [Path(img.file.path) for img in images if img.file]
        _append_log(run.pk, 'Sampling background…')
        pipeline.prime(image_paths)

        crop_dir = (
            Path(settings.MEDIA_ROOT) / 'runs' / run.module / str(run.pk) / 'crops'
        )

        total_det = run.detection_count
        by_class = dict(run.detections_by_class or {})
        by_source = dict(run.detections_by_source or {})

        for idx, image in enumerate(images, start=1):
            if idx < resume_from:
                continue

            status = _peek_status(run.pk)
            if status == JobStatus.CANCELLED:
                raise RunCancelled(f'Inference run {run.pk} cancelled by user')
            if status == JobStatus.PAUSED:
                raise RunPaused(f'Inference run {run.pk} paused by user')

            if not image.file:
                continue
            img_path = Path(image.file.path)

            try:
                detections = pipeline.process_image(img_path)
            except Exception:
                logger.exception(f'Pipeline failed on {img_path.name}')
                run.failed_image_count = (run.failed_image_count or 0) + 1
                run.processed_image_count = idx
                run.save(
                    update_fields=['failed_image_count', 'processed_image_count'],
                )
                continue

            n, cls_delta, src_delta = _persist_image_results(
                run, image, detections, crop_dir
            )
            total_det += n
            for k, v in cls_delta.items():
                by_class[k] = by_class.get(k, 0) + v
            for k, v in src_delta.items():
                by_source[k] = by_source.get(k, 0) + v

            run.processed_image_count = idx
            run.detection_count = total_det
            run.detections_by_class = by_class
            run.detections_by_source = by_source
            run.save(
                update_fields=[
                    'processed_image_count',
                    'detection_count',
                    'detections_by_class',
                    'detections_by_source',
                ],
            )

        run.status = JobStatus.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at'])
        _append_log(
            run.pk,
            f'Run complete: {total_det} detections across {run.processed_image_count} images.',
        )
        logger.info(f'Inference run {run.pk} completed: {total_det} detections')

    except RunPaused:
        # User-initiated pause. Status is already PAUSED (set by the pause
        # endpoint). Detections for completed images stay; resume picks up
        # at processed_image_count + 1.
        logger.info(f'Inference run {run.pk} paused by user')
        _append_log(
            run.pk,
            f'Paused at image {run.processed_image_count}/{run.image_count}.',
            level='warn',
        )
    except RunCancelled:
        logger.info(f'Inference run {run.pk} cancelled by user')
        run.completed_at = timezone.now()
        run.save(update_fields=['completed_at'])
        _append_log(run.pk, 'Cancelled by user.', level='warn')
    except Exception as e:
        logger.exception(f'Inference run {run.pk} failed')
        run.status = JobStatus.FAILED
        run.error_message = f'{type(e).__name__}: {e}'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'completed_at'])
        raise


def _run_in_thread(run_id: int) -> None:
    """Background-thread entry. Each thread gets its own DB connection;
    close_old_connections at the end prevents leaks for short-lived runs."""
    try:
        run = InferenceRun.objects.get(pk=run_id)
        run_inference_pipeline(run)
    except InferenceRun.DoesNotExist:
        logger.error(f'Background worker: run {run_id} not found')
    except Exception:
        logger.exception(f'Background run {run_id} crashed')
    finally:
        close_old_connections()


def spawn_inference_pipeline(run: InferenceRun) -> None:
    """Start a daemon thread that runs the pipeline for the given run.

    Returns immediately. The caller (typically the start/resume view)
    should serialise the run row before this returns so the response
    includes ``status='pending'`` (the worker will flip to running shortly).
    """
    thread = threading.Thread(
        target=_run_in_thread,
        args=(run.pk,),
        daemon=True,
        name=f'run-{run.pk}',
    )
    thread.start()

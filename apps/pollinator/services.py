"""Execution of the pollinator inference pipeline.

run_inference_pipeline is the synchronous core: invoked directly it blocks
until the pipeline finishes. spawn_inference_pipeline runs the same work in
a daemon thread so the HTTP request can return immediately.

The pollinator package is imported lazily inside run_inference_pipeline so
Django can boot without the heavy ML dependencies (torch, ultralytics,
etc). They are only required when an actual run executes.

The threading-based runner is fine for development and small deployments.
A process restart kills any in-flight run, leaving its row stuck in
status='running'. Production should swap this for a persistent queue
(Celery, RQ, or similar) without changing the run_inference_pipeline body.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.analysis.cancellation import RunCancelled
from apps.analysis.crops import write_detection_crop
from apps.analysis.engulfment import apply_engulfment_exclusions
from apps.analysis.models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    ModelVersion,
)
from apps.analysis.storage import resolve_model_path

from .models import PollinatorDetection

logger = logging.getLogger(__name__)


_ACTIVITY_LOG_CAP = 200


def _make_progress_callback(run_id: int):
    """Build a callback the pipeline calls at progress milestones.

    Updates processed_image_count on every call. When a message is
    provided, appends a {time, message, level} entry to activity_log
    (capped at the last 200 entries).
    """

    def cb(processed: int, total: int, message: str = '', level: str = 'info') -> None:
        # Cancellation check: re-read the row's status. If externally flipped
        # to CANCELLED, raise — propagates through the ML pipeline (which uses
        # `except Exception:`) and lands at the worker's try/except for
        # cooperative cancellation.
        current = (
            InferenceRun.objects.filter(pk=run_id)
            .values_list('status', flat=True)
            .first()
        )
        if current == JobStatus.CANCELLED:
            raise RunCancelled(f'Inference run {run_id} cancelled by user')

        try:
            updates: dict = {'processed_image_count': processed}
            if total:
                updates['image_count'] = total
            if message:
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
                for k, v in updates.items():
                    setattr(run, k, v)
                run.save(update_fields=list(updates.keys()) + ['activity_log'])
            else:
                InferenceRun.objects.filter(pk=run_id).update(**updates)
        except RunCancelled:
            raise
        except Exception:
            logger.exception(f'Progress callback failed for run {run_id}')

    return cb


def run_inference_pipeline(run: InferenceRun) -> None:
    """Run the pollinator pipeline for one InferenceRun, persist results.

    Status flow: pending -> running -> completed / failed.
    On failure, error_message is populated and the exception is re-raised
    so the caller can decide whether to surface it (sync view) or just log
    it (async worker).
    """
    try:
        run.status = JobStatus.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=['status', 'started_at'])

        from pollinator.workflows.inference import run_pipeline as _run_pipeline

        upload = run.upload
        if upload is None:
            raise ValueError('Run has no upload; cannot determine image set')

        images = list(upload.images.all())
        if not images:
            raise ValueError('Upload has no images to process')

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
        if 'preprocessing' in config and isinstance(config['preprocessing'], dict):
            prep_config.update(config['preprocessing'])

        yolo_conf = float((config.get('yolo') or {}).get('confidence', 0.25))
        binary_thr = float(
            (config.get('binary_classifier') or {}).get('confidence', 0.5)
        )
        # Group threshold defaults to 0 -> keep every group call (current
        # behaviour). When the upload sets it, sub-threshold group calls are
        # stripped to insectnet_class='' inside the pipeline.
        group_thr = float((config.get('group_classifier') or {}).get('confidence', 0.0))
        # Frontend start_at_image is 1-based; library skip_first_n is 0-based.
        skip_first = max(0, int(config.get('start_at_image', 1)) - 1)

        # Tile geometry recorded on the YOLO ModelVersion when it was trained.
        # Inference must slice at the same scale or detections degrade.
        yolo_tile_cfg = (yolo_mv.parameters or {}).get('tile_config') or {}
        yolo_slice_size = int(yolo_tile_cfg.get('tile_size', 640))
        yolo_overlap = float(yolo_tile_cfg.get('overlap', 0.2))

        # The pipeline expects all images for one camera plot in a single dir.
        # Symlink the upload's files into a temp dir so other uploads in the
        # same module folder do not bleed into this run.
        with tempfile.TemporaryDirectory(prefix=f'run_{run.pk}_') as tmpdir:
            tmp = Path(tmpdir)
            for img in images:
                if not img.file:
                    continue
                src = Path(img.file.path)
                dst = tmp / Path(img.file.name).name
                if not dst.exists():
                    dst.symlink_to(src)

            output_dir = Path(settings.MEDIA_ROOT) / 'runs' / str(run.pk)
            output_dir.mkdir(parents=True, exist_ok=True)

            progress_cb = _make_progress_callback(run.pk)

            result = _run_pipeline(
                image_dir=str(tmp),
                output_dir=str(output_dir),
                yolo_model=str(yolo_path),
                binary_model=str(binary_path),
                group_model=str(group_path),
                config=prep_config,
                yolo_confidence=yolo_conf,
                yolo_slice_size=yolo_slice_size,
                yolo_overlap=yolo_overlap,
                binary_threshold=binary_thr,
                group_threshold=group_thr,
                skip_first_n=skip_first,
                progress_callback=progress_cb,
            )

        json_path = Path(result['output_json'])
        with open(json_path) as f:
            output = json.load(f)

        run_summary = output.get('run', {})
        detections_json = output.get('detections', [])

        images_by_name = {Path(img.file.name).name: img for img in images if img.file}

        det_objs: list[Detection] = []
        pol_data: list[dict] = []
        for d in detections_json:
            image = images_by_name.get(d.get('image_name'))
            if image is None:
                continue
            bbox = d.get('bbox') or {}
            yolo_class = d.get('yolo_class') or ''
            insectnet_class = d.get('insectnet_class') or ''
            primary_class = yolo_class or insectnet_class
            primary_conf = (
                d.get('yolo_confidence')
                if yolo_class
                else d.get('insectnet_confidence')
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
            pol_data.append(
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

        with transaction.atomic():
            created = Detection.objects.bulk_create(det_objs)
            PollinatorDetection.objects.bulk_create(
                [
                    PollinatorDetection(detection=det, **data)
                    for det, data in zip(created, pol_data)
                ]
            )

        # Render the per-detection crop files after the rows are committed
        # so we have stable detection pks for the filenames, and so a PIL
        # failure on one image can't roll back the whole run. Ping the
        # progress callback every 50 crops so the activity log advances
        # past the final pipeline tick instead of looking frozen.
        total_dets = len(created)
        n_images = int(run_summary.get('n_images', len(images)))
        if total_dets:
            try:
                progress_cb(n_images, n_images, f'Writing {total_dets} crops...')
            except RunCancelled:
                pass
        crop_updates: list[Detection] = []
        for idx, det in enumerate(created, start=1):
            if write_detection_crop(det):
                crop_updates.append(det)
            if idx % 50 == 0 or idx == total_dets:
                # Heavy work is already done; finishing the remaining crops
                # is cheap. Don't propagate a cancel here — we'd just orphan
                # half-written files. The post-loop status check below honours
                # the cancellation request instead.
                try:
                    progress_cb(n_images, n_images, f'Crops: {idx}/{total_dets}')
                except RunCancelled:
                    pass
        if crop_updates:
            Detection.objects.bulk_update(crop_updates, ['crop'])

        # If cancel landed while crops were being written, preserve the
        # CANCELLED status instead of overwriting with COMPLETED. The user
        # gets a cancelled run with detections + crops they can still review
        # or delete; either is more useful than discarding everything.
        current_status = (
            InferenceRun.objects.filter(pk=run.pk)
            .values_list('status', flat=True)
            .first()
        )
        if current_status == JobStatus.CANCELLED:
            logger.info(
                f'Run {run.pk} cancelled after inference; detections + crops preserved'
            )
            return

        run.status = JobStatus.COMPLETED
        run.completed_at = timezone.now()
        run.processed_image_count = int(run_summary.get('n_images', len(images)))
        run.detection_count = len(det_objs)
        run.detections_by_class = run_summary.get('detections_by_class', {})
        run.detections_by_source = run_summary.get('detections_by_source', {})
        run.save(
            update_fields=[
                'status',
                'completed_at',
                'processed_image_count',
                'detection_count',
                'detections_by_class',
                'detections_by_source',
            ]
        )
        excluded = apply_engulfment_exclusions(run.pk)
        if excluded:
            logger.info(
                f'Inference run {run.pk}: auto-excluded {excluded} engulfing bbox(es)'
            )
        logger.info(f'Inference run {run.pk} completed: {len(det_objs)} detections')

    except RunCancelled:
        # Status is already CANCELLED (set by the cancel endpoint). No
        # Detection rows have been persisted (bulk_create is inside the
        # transaction.atomic block below the try). Just stamp the
        # finalisation fields and exit without re-raising — this is a
        # clean user-initiated stop, not a failure.
        logger.info(f'Inference run {run.pk} cancelled by user')
        run.completed_at = timezone.now()
        run.save(update_fields=['completed_at'])
    except Exception as e:
        logger.exception(f'Inference run {run.pk} failed')
        run.status = JobStatus.FAILED
        run.error_message = f'{type(e).__name__}: {e}'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'completed_at'])
        raise


def _run_in_thread(run_id: int) -> None:
    """Background-thread entry point. Each thread gets its own DB connection;
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

    Returns immediately. The caller (typically the create view) should
    serialise the run row before this returns so the response includes
    status='pending' (the worker will flip to running shortly after).
    """
    thread = threading.Thread(
        target=_run_in_thread,
        args=(run.pk,),
        daemon=True,
        name=f'run-{run.pk}',
    )
    thread.start()

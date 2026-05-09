"""Synchronous execution of the pollinator inference pipeline.

This is Tier 4a: the run is executed in-process from the create view, which
means the HTTP request blocks until the pipeline finishes. Tier 4b moves
this onto a background worker.

The pollinator package is imported lazily inside run_inference_pipeline so
Django can boot without the heavy ML dependencies (torch, ultralytics,
etc). They are only required when an actual run executes.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    ModelVersion,
)

logger = logging.getLogger(__name__)


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

        from pollinator.inference import run_pipeline as _run_pipeline

        upload = run.upload
        if upload is None:
            raise ValueError('Run has no upload; cannot determine image set')

        images = list(upload.images.all())
        if not images:
            raise ValueError('Upload has no images to process')

        config = run.config or {}
        yolo_id = (config.get('yolo') or {}).get('model_version_id')
        classifier_id = (config.get('classifier') or {}).get('model_version_id')
        if not yolo_id or not classifier_id:
            raise ValueError(
                'Run config must include yolo.model_version_id and '
                'classifier.model_version_id'
            )

        yolo_mv = ModelVersion.objects.get(pk=yolo_id)
        classifier_mv = ModelVersion.objects.get(pk=classifier_id)

        # Convention for now: a "classifier" ModelVersion's model_file_path
        # points to a directory containing binary_best.pth + group_best.pth.
        # If we later split binary and group into separate ModelVersion rows,
        # the frontend needs two model_version_id fields and this resolves
        # to two paths directly.
        classifier_dir = Path(classifier_mv.model_file_path)
        binary_path = classifier_dir / 'binary_best.pth'
        group_path = classifier_dir / 'group_best.pth'

        # Translate the frontend's nested config into the pipeline's flat shape.
        prep_config: dict = {}
        if 'preprocessing' in config and isinstance(config['preprocessing'], dict):
            prep_config.update(config['preprocessing'])
        adv = config.get('advanced') or {}
        if 'crop_padding' in adv:
            prep_config['crop_pad_frac'] = adv['crop_padding']
        if 'background_sample_size' in adv:
            prep_config['background_sample_size'] = adv['background_sample_size']

        yolo_conf = float((config.get('yolo') or {}).get('confidence', 0.25))
        binary_thr = float(
            (config.get('classifier') or {}).get('binary_confidence', 0.5)
        )
        # Frontend start_at_image is 1-based; library skip_first_n is 0-based.
        skip_first = max(0, int(config.get('start_at_image', 1)) - 1)

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

            result = _run_pipeline(
                image_dir=str(tmp),
                output_dir=str(output_dir),
                yolo_model=yolo_mv.model_file_path,
                binary_model=str(binary_path),
                group_model=str(group_path),
                config=prep_config,
                yolo_confidence=yolo_conf,
                binary_threshold=binary_thr,
                skip_first_n=skip_first,
            )

        json_path = Path(result['output_json'])
        with open(json_path) as f:
            output = json.load(f)

        run_summary = output.get('run', {})
        detections_json = output.get('detections', [])

        images_by_name = {
            Path(img.file.name).name: img for img in images if img.file
        }

        det_objs = []
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
            det_objs.append(Detection(
                inference_run=run,
                image=image,
                bbox=bbox,
                confidence=float(primary_conf or 0.0),
                predicted_class=primary_class,
                area=float(bbox.get('w', 0)) * float(bbox.get('h', 0)),
                yolo_class=yolo_class,
                yolo_confidence=d.get('yolo_confidence'),
                insectnet_class=insectnet_class,
                insectnet_confidence=d.get('insectnet_confidence'),
                binary_confidence=d.get('binary_confidence'),
                class_probs=d.get('class_probs') or {},
                source=d.get('source') or '',
                merge_iou=d.get('merge_iou'),
                status=DetectionStatus.PENDING,
            ))
        Detection.objects.bulk_create(det_objs)

        run.status = JobStatus.COMPLETED
        run.completed_at = timezone.now()
        run.processed_image_count = int(run_summary.get('n_images', len(images)))
        run.detection_count = len(det_objs)
        run.detections_by_class = run_summary.get('detections_by_class', {})
        run.detections_by_source = run_summary.get('detections_by_source', {})
        run.save(update_fields=[
            'status', 'completed_at', 'processed_image_count',
            'detection_count', 'detections_by_class', 'detections_by_source',
        ])
        logger.info(f'Inference run {run.pk} completed: {len(det_objs)} detections')

    except Exception as e:
        logger.exception(f'Inference run {run.pk} failed')
        run.status = JobStatus.FAILED
        run.error_message = f'{type(e).__name__}: {e}'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_message', 'completed_at'])
        raise

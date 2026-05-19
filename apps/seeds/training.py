"""Seed species training pipeline.

run_training_job runs the full training process for one TrainingJob: reads the job
config, resolves dataset (YOLO yaml per species), selects model and training (scratch or incremental),
then performs post-training evaluation.

If training_mode is 'incremental', it loads an existing ModelVersion as the starting point.
If it's 'scratch', it trains from a base pretrained model.

spawn_training_job just runs this in a background thread so the API
doesn't block while training runs.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
import os

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.analysis.models import (
    JobStatus,
    ModelVersion,
    TrainingJob,
)

from apps.datasets.models import Module
from apps.analysis.cancellation import RunCancelled

from ml_pipelines.seed_src.training.train import train_species_model
from ml_pipelines.seed_src.utils.metrics import calculate_tp_fp_fn  # for post-training evaluation

logger = logging.getLogger(__name__)

_ACTIVITY_LOG_CAP = 200


# ──────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────

BASE_DATA = settings.BASE_DIR / 'data' / 'seed'

# Dynamically discover species from existing folders
SPECIES_LIST = [
    d.replace('_model', '')
    for d in os.listdir(BASE_DATA)
    if os.path.isdir(BASE_DATA / d) and d.endswith('_model')
] if BASE_DATA.exists() else []

CONFIG_MAP = {s: str(BASE_DATA / f'{s}_model' / f'{s}.yaml') for s in SPECIES_LIST}

# ──────────────────────────────────────────────────────────────────────────
# Progress reporting
# ──────────────────────────────────────────────────────────────────────────


def _make_progress_callback(job_id: int):
    def cb(processed: int, total: int, message: str = '', level: str = 'info'):
        # Cancellation check on every tick. Status is owned by the cancel
        # endpoint; we just read and raise. RunCancelled inherits
        # BaseException so it bypasses ML pipeline's `except Exception`.
        print(f'Progress callback: job={job_id} epoch={processed}/{total}')
        current = (
            TrainingJob.objects.filter(pk=job_id)
            .values_list('status', flat=True)
            .first()
        )
        if current == JobStatus.CANCELLED:
            raise RunCancelled(f'Training job {job_id} cancelled by user')

        try:
            job = TrainingJob.objects.get(pk=job_id)

            job.current_epoch = processed
            job.total_epochs = total

            if message:
                log = list(job.activity_log or [])
                log.append(
                    {
                        'time': timezone.now().isoformat(),
                        'message': message,
                        'level': level,
                    }
                )
                job.activity_log = log[-_ACTIVITY_LOG_CAP:]
            job.save()

        except RunCancelled:
            raise
        except Exception:
            logger.exception(f'Progress callback failed for job {job_id}')

    return cb


# ──────────────────────────────────────────────────────────────────────────
# Main job runner
# ──────────────────────────────────────────────────────────────────────────


def _validate_config(config: dict) -> tuple[str, str, int, int | None]:
    """
    Validate Seeds training config.
    Returns:
        species,
        training_mode,
        epochs,
        source_model_id (only for incremental)
    """
    species = config.get('species')
    if not species:
        raise ValueError("config requires 'species'")
    training_mode = config.get('training_mode', 'scratch')

    if training_mode not in ('scratch', 'incremental'):
        raise ValueError("training_mode must be 'scratch' or 'incremental'")

    epochs = int(config.get('epochs', 30))
    if epochs <= 0:
        raise ValueError('epochs must be positive')

    source_model_id = config.get('source_model_id')
    if training_mode == 'incremental' and not source_model_id:
        raise ValueError('incremental training requires source_model_id')

    return species, training_mode, epochs, source_model_id


def run_training_job(job: TrainingJob) -> None:
    """Synchronous core. Status flow: pending → running → completed / failed.
    scratch --> train from base YOLO weights
    incremental --> fine-tune from existing ModelVersion
    """
    try:
        job.status = JobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])

        config = job.config or {}
        species, training_mode, epochs, source_model_id = _validate_config(config)

        # Model selection
        source_model = None
        finetune_from = None

        if training_mode == 'incremental':
            source_model = ModelVersion.objects.get(pk=source_model_id)
            finetune_from = source_model.model_file_path
        else:
            source_model = None
            finetune_from = None

        # Resolve dataset YAML (pre-built slicing pipeline)
        data_yaml_path = str(BASE_DATA / f'{species}_model' / f'{species}.yaml')

        if not Path(data_yaml_path).exists():
            raise FileNotFoundError(f'Dataset YAML not found: {data_yaml_path}')

        progress_cb = _make_progress_callback(job.pk)

        # Train model
        train_started = time.monotonic()
        weights_path = train_species_model(
            species_name=species,
            data_yaml_path=data_yaml_path,
            epochs=epochs,
            finetune_from=finetune_from,
            run_name=f'{species}_{training_mode}_{job.pk}',
            progress_callback=progress_cb,
        )

        train_duration = int(time.monotonic() - train_started)
        version_name = f'{species.upper()}-{job.pk:02d}'

        # Persist new ModelVersion + finalise job
        # By default, the most recent model version is automatically set as active
        with transaction.atomic():
            ModelVersion.objects.filter(
                module=Module.SEEDS,
                parameters__species=species,
                is_active=True,
            ).update(is_active=False)

            new_mv = ModelVersion.objects.create(
                module=Module.SEEDS,
                kind='detector',
                version_name=version_name,
                model_file_path=weights_path,
                source_model_version=source_model,
                training_duration_seconds=train_duration,
                trained_at=timezone.now(),
                is_active=True,
                parameters={
                    'species': species,
                    'mode': training_mode,
                    'epochs': epochs,
                },
            )

            job.resulting_model = new_mv
            job.status = JobStatus.COMPLETED
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    'resulting_model',
                    'status',
                    'completed_at',
                ]
            )

        logger.info(f'Seeds TrainingJob {job.pk} completed')

    except RunCancelled:
        # Status is already CANCELLED. No ModelVersion was created and no
        # training_detections were stamped (both happen inside the atomic
        # block after the ML work completes). Clean stop, not a failure.
        job.completed_at = timezone.now()
        job.save(update_fields=['completed_at'])
        logger.info(f'Seeds TrainingJob {job.pk} cancelled by user')
    except Exception as e:
        logger.exception(f'Seeds TrainingJob {job.pk} failed')
        job.status = JobStatus.FAILED
        job.error_message = f'{type(e).__name__}: {e}'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at'])
        raise


# TODO: Post-training evaluation function (evaluation metrics, viability, etc.)


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
        name=f'seeds-train-{job.pk}',
    ).start()

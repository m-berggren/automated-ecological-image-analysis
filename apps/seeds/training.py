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
import random
import shutil
import threading
import time
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.analysis.artifacts import ingest_run_dir
from apps.analysis.models import (
    JobStatus,
    ModelVersion,
    TrainingJob,
)
from apps.analysis.storage import move_weights_into_place

from apps.datasets.models import Module
from apps.analysis.cancellation import RunCancelled

from ml_pipelines.seed_src.training.slice_dataset import process_image
from ml_pipelines.seed_src.training.train import train_species_model
from ml_pipelines.seed_src.utils.metrics import calculate_tp_fp_fn, calculate_precision_recall_f1_score

logger = logging.getLogger(__name__)

_ACTIVITY_LOG_CAP = 200

_IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}


# ──────────────────────────────────────────────────────────────────────────
# Storage layout
# ──────────────────────────────────────────────────────────────────────────


def _staging_root() -> Path:
    """Where uploads land before a TrainingJob exists.

    The upload endpoint writes here keyed by a per-session UUID; when
    SeedTrainingJobCreateView creates the TrainingJob it moves the staging
    dir into _job_dir(job.pk). Both layouts mirror each other:
    {images,labels}/.
    """
    return Path(settings.MEDIA_ROOT) / 'training' / 'seeds' / 'staging'


def _job_dir(job_pk: int) -> Path:
    """Per-job ephemeral dir under MEDIA_ROOT/training/<job_pk>/.

    Holds the raw uploaded images/labels, the sliced dataset, the dataset
    YAML, and (via train_species_model project=) the ultralytics run
    output. Wiped on job completion or failure; the canonical weights file
    gets moved out beforehand.
    """
    return Path(settings.MEDIA_ROOT) / 'training' / str(job_pk)


def _split_files(
    files: list[Path],
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> tuple[list[Path], list[Path], list[Path]]:
    """Deterministic train/val/test split with small-dataset fallbacks.

    Rules:
        X >= 10  - apply ratios (rounding val and test up to >= 1 when
                   their ratio is > 0).
        2..9     - 1 val image, no test, rest train. A test set on this
                   little data is noise.
        1        - train only, no val/test. The eval block warns and skips.
        0        - returns three empty lists; caller's job to refuse.

    Same input order + seed always produce the same split, so a retry of a
    failed job consumes the same train/val partition.
    """
    n = len(files)
    if n == 0:
        return [], [], []

    ordered = sorted(files, key=lambda p: p.name)
    random.Random(seed).shuffle(ordered)

    if n == 1:
        return ordered, [], []
    if n < 10:
        return ordered[1:], ordered[:1], []

    n_val = max(1, round(n * val_ratio)) if val_ratio > 0 else 0
    n_test = max(1, round(n * test_ratio)) if test_ratio > 0 else 0
    n_train = n - n_val - n_test
    if n_train < 1:
        # Defensive: ratios that leave nothing for train. Steal back from
        # test first, then val.
        deficit = 1 - n_train
        take_from_test = min(deficit, n_test)
        n_test -= take_from_test
        deficit -= take_from_test
        n_val -= deficit
        n_train = 1
    return (
        ordered[:n_train],
        ordered[n_train : n_train + n_val],
        ordered[n_train + n_val :],
    )


def _prepare_job_dataset(
    species: str,
    job_pk: int,
    val_ratio: float,
    test_ratio: float,
) -> tuple[Path, Path, int]:
    """Slice job uploads into a YOLO dataset under MEDIA_ROOT/training/<job_pk>/.

    Reads images + labels from <job_dir>/{images,labels}/ (placed there by
    the upload + rename flow), splits with _split_files, slices the train
    portion, copies val/test verbatim. Returns (yaml_path, val_imgs_dir,
    sliced_train_count). Raises FileNotFoundError when the job has no
    uploaded images.
    """
    job_dir = _job_dir(job_pk)
    upload_imgs = job_dir / 'images'
    upload_lbls = job_dir / 'labels'

    if not upload_imgs.exists() or not any(
        p for p in upload_imgs.iterdir() if p.suffix.lower() in _IMAGE_EXTS
    ):
        raise FileNotFoundError(
            f'No training images for job {job_pk} '
            f'(expected files under {upload_imgs}).'
        )

    # Only consider images that actually have a label file. The slicer
    # would skip them anyway; filtering here keeps the split honest about
    # how much training signal exists.
    all_images = [
        p for p in upload_imgs.iterdir() if p.suffix.lower() in _IMAGE_EXTS
    ]
    paired = [
        p for p in all_images
        if (upload_lbls / f'{p.stem}.txt').exists()
    ]
    if not paired:
        # Empty paired means we'd slice 0 tiles and ultralytics would
        # bail with a confusing "images not found" — emit a clear job
        # error instead so the UI surface it as a real message.
        n_labels = sum(
            1 for p in upload_lbls.iterdir() if p.suffix.lower() == '.txt'
        ) if upload_lbls.exists() else 0
        raise ValueError(
            f'No image/label pairs found. Got {len(all_images)} image(s) '
            f'and {n_labels} label file(s), but no pair shares the same '
            f'filename stem (e.g. "foo.jpg" needs "foo.txt"). Check that '
            f'your YOLO label .txt files match the image filenames.'
        )

    train_files, val_files, test_files = _split_files(
        paired, val_ratio, test_ratio, seed=job_pk
    )

    dataset_dir = job_dir / 'dataset'
    sliced_train_imgs = dataset_dir / 'train_sliced' / 'images'
    sliced_train_lbls = dataset_dir / 'train_sliced' / 'labels'
    val_imgs = dataset_dir / 'val' / 'images'
    val_lbls = dataset_dir / 'val' / 'labels'
    test_imgs = dataset_dir / 'test' / 'images'
    test_lbls = dataset_dir / 'test' / 'labels'
    for d in (sliced_train_imgs, sliced_train_lbls, val_imgs, val_lbls,
              test_imgs, test_lbls):
        d.mkdir(parents=True, exist_ok=True)

    # Slice every train image. process_image emits multiple tiles per
    # source (basename_x<X>_y<Y>.png) and shifts the polygon coords.
    for img_file in train_files:
        lbl_file = upload_lbls / f'{img_file.stem}.txt'
        process_image(
            str(img_file),
            str(lbl_file),
            str(sliced_train_imgs),
            str(sliced_train_lbls),
        )

    # Val + test stay raw — both YOLO's per-epoch eval and the post-train
    # SAHI eval expect full-resolution images with original polygons.
    for img_file in val_files:
        shutil.copy2(img_file, val_imgs / img_file.name)
        shutil.copy2(upload_lbls / f'{img_file.stem}.txt', val_lbls / f'{img_file.stem}.txt')
    for img_file in test_files:
        shutil.copy2(img_file, test_imgs / img_file.name)
        shutil.copy2(upload_lbls / f'{img_file.stem}.txt', test_lbls / f'{img_file.stem}.txt')

    val_has_images = any(p.suffix.lower() in _IMAGE_EXTS for p in val_imgs.iterdir())

    # Ultralytics resolves a *relative* `path:` against its global
    # `datasets_dir` setting (~/.config/Ultralytics/settings.json), not
    # against the YAML file's location — so we have to use an absolute
    # path. Path.as_posix() forces forward slashes, which keeps Windows
    # paths from littering the YAML with backslashes that have tripped
    # PyYAML + ultralytics in the past.
    yaml_path = job_dir / f'{species}.yaml'
    yaml_path.write_text(
        f'path: {dataset_dir.as_posix()}\n'
        'train: train_sliced/images\n'
        # Fall back to train when no val images exist — YOLO still needs a
        # readable val: key. The eval block below short-circuits in that
        # case anyway.
        f'val: {"val/images" if val_has_images else "train_sliced/images"}\n'
        '\n'
        'names:\n'
        f'  0: {species}\n'
    )

    sliced_count = sum(
        1 for p in sliced_train_imgs.iterdir() if p.suffix.lower() in _IMAGE_EXTS
    )
    return yaml_path, val_imgs, sliced_count

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


def _validate_config(
    config: dict,
) -> tuple[str, str, int, int | None, float, float]:
    """Validate Seeds training config.

    Returns: (species, training_mode, epochs, source_model_id, val_ratio,
    test_ratio). The two ratios are the user's target split for the per-job
    upload; _split_files applies small-dataset fallbacks when honouring
    them would leave train empty.
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

    val_ratio = float(config.get('val_ratio', 0.1))
    test_ratio = float(config.get('test_ratio', 0.0))
    if not (0 <= val_ratio < 1):
        raise ValueError('val_ratio must be in [0, 1)')
    if not (0 <= test_ratio < 1):
        raise ValueError('test_ratio must be in [0, 1)')
    if val_ratio + test_ratio >= 1:
        raise ValueError('val_ratio + test_ratio must leave room for train')

    return species, training_mode, epochs, source_model_id, val_ratio, test_ratio


def run_training_job(job: TrainingJob) -> None:
    """Synchronous core. Status flow: pending → running → completed / failed.
    scratch --> train from base YOLO weights
    incremental --> fine-tune from existing ModelVersion
    """
    job_dir: Path | None = None
    try:
        job.status = JobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])

        config = job.config or {}
        (
            species, training_mode, epochs, source_model_id,
            val_ratio, test_ratio,
        ) = _validate_config(config)
        job_dir = _job_dir(job.pk)

        # Model selection
        source_model = None
        finetune_from = None

        if training_mode == 'incremental':
            source_model = ModelVersion.objects.get(pk=source_model_id)
            finetune_from = source_model.model_file_path
        else:
            source_model = None
            finetune_from = None

        # Split + slice the job's uploaded images into a YOLO dataset and
        # write a fresh YAML. _prepare_job_dataset raises FileNotFoundError
        # when the job has no uploaded training images.
        yaml_path, val_imgs_dir, sliced_train_count = _prepare_job_dataset(
            species, job.pk, val_ratio, test_ratio,
        )
        data_yaml_path = str(yaml_path)
        val_has_images = any(
            p.suffix.lower() in _IMAGE_EXTS for p in val_imgs_dir.iterdir()
        )

        progress_cb = _make_progress_callback(job.pk)
        print(f'Starting training job {job.pk} — species={species} mode={training_mode} epochs={epochs}')

        # Train model. project= keeps ultralytics' run output inside the
        # per-job dir, so cleanup is just rmtree(job_dir) — no CWD-relative
        # runs/obb/ tree to chase.
        train_started = time.monotonic()
        weights_path = train_species_model(
            species_name=species,
            data_yaml_path=data_yaml_path,
            epochs=epochs,
            finetune_from=finetune_from,
            run_name=f'{species}_{training_mode}_{job.pk}',
            progress_callback=progress_cb,
            project=str(job_dir / 'yolo'),
        )

        train_duration = int(time.monotonic() - train_started)
        version_name = f'{species.upper()}-{job.pk:02d}'
        print(f'Training done in {train_duration}s, weights at {weights_path}')

        # Run post-training evaluation
        if val_has_images:
            progress_cb(0, 0, 'Running post-training evaluation...', 'info')
            try:
                from ml_pipelines.seed_src.utils.helpers import load_model
                from ml_pipelines.seed_src.inference.inference import run_inference
                from ml_pipelines.seed_src.utils.metrics import calculate_tp_fp_fn, calculate_precision_recall_f1_score

                eval_model = load_model(weights_path)
                val_dir = val_imgs_dir
                label_dir = val_imgs_dir.parent / 'labels'

                total_tp = total_fp = total_fn = total_error = total_gt = n_images = 0

                if val_dir.exists():
                    for img_file in val_dir.iterdir():
                        if img_file.suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
                            continue
                        label_file = label_dir / f'{img_file.stem}.txt'
                        gt_boxes = []
                        if label_file.exists():
                            from PIL import Image as PILImage
                            with PILImage.open(img_file) as img:
                                w, h = img.size
                            with open(label_file) as f:
                                for line in f:
                                    parts = line.strip().split()
                                    if len(parts) < 9:
                                        continue
                                    coords = list(map(float, parts[1:]))
                                    pixel_coords = [
                                        c * w if i % 2 == 0 else c * h
                                        for i, c in enumerate(coords)
                                    ]
                                    gt_boxes.append(pixel_coords)

                        result = run_inference(str(img_file), eval_model)
                        preds = []
                        for pred in result.object_prediction_list:
                            b = pred.bbox
                            poly = [b.minx, b.miny, b.maxx, b.miny,
                                    b.maxx, b.maxy, b.minx, b.maxy]
                            preds.append({'poly': poly, 'conf': float(pred.score.value)})

                        tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.3)
                        total_tp += tp
                        total_fp += fp
                        total_fn += fn
                        total_error += abs(len(preds) - len(gt_boxes))
                        total_gt += len(gt_boxes)
                        n_images += 1

                mae = total_error / n_images if n_images > 0 else 0
                precision, recall, f1 = calculate_precision_recall_f1_score(
                    total_tp, total_fp, total_fn
                )
                metrics = {
                    'mae': round(mae, 3),
                    'precision': round(precision, 3),
                    'recall': round(recall, 3),
                    'f1': round(f1, 3),
                    'val_images': n_images,
                }
                # Sliced training image count comes from _prepare_job_dataset.
                sample_count = sliced_train_count

                print(f'Evaluation complete — MAE={metrics.get("mae")} F1={metrics.get("f1")} samples={sample_count}')

            except Exception as e:
                logger.warning(f'Post-training evaluation failed: {e}')
                metrics = {}
                sample_count = sliced_train_count
        else:
            logger.warning(f'No val images for {species}, skipping evaluation')
            metrics = {}
            sample_count = sliced_train_count

        # Persist new ModelVersion + finalise job
        # By default, the most recent model version is automatically set as active
        with transaction.atomic():
            ModelVersion.objects.filter(
                module=Module.SEEDS,
                parameters__species=species,
                is_active=True,
            ).update(is_active=False)

            # Lineage-aware naming.
            #   scratch:     <SPECIES>-NN where NN counts only completed
            #                scratch ModelVersions for this species. Manual
            #                uploads don't shift the count, so the
            #                training-page numbering stays predictable.
            #   incremental: <source.version_name>.K where K counts the
            #                source model's direct retrains. The full chain
            #                is recoverable from the name alone (and from
            #                the source_model_version FK).
            if training_mode == 'incremental' and source_model is not None:
                sibling_count = ModelVersion.objects.filter(
                    source_model_version=source_model,
                ).count()
                version_name = f'{source_model.version_name}.{sibling_count + 1}'
            else:
                scratch_count = ModelVersion.objects.filter(
                    module=Module.SEEDS,
                    parameters__species__iexact=species,
                    parameters__mode='scratch',
                ).count()
                version_name = f'{species.upper()}-{(scratch_count + 1):02d}'

            new_mv = ModelVersion.objects.create(
                module=Module.SEEDS,
                kind='detector',
                version_name=version_name,
                # Filled in after move_weights_into_place below.
                model_file_path='',
                source_model_version=source_model,
                training_duration_seconds=train_duration,
                trained_at=timezone.now(),
                is_active=True,
                metrics=metrics,
                sample_count=sample_count,
                parameters={
                    'species': species.lower(),
                    'mode': training_mode,
                    'epochs': epochs,
                },
            )

            # Ingest the YOLO run dir's standard artifacts (results.csv,
            # confusion_matrix.png, *_curve.png, ...) as ModelArtifact rows
            # so the model card shows training curves. Must happen before
            # the move + cleanup, since run_dir lives under job_dir.
            run_dir = Path(weights_path).resolve().parent.parent
            try:
                ingest_run_dir(new_mv, run_dir)
            except Exception:
                logger.exception(
                    f'Failed to ingest run artifacts from {run_dir}'
                )

            # Move weights to the canonical models/seeds/<id>/weights<ext>
            # location and update the row. Without this the path would
            # point inside job_dir, which the finally block wipes.
            weights_src = Path(weights_path).resolve()
            canonical = move_weights_into_place(
                weights_src, Module.SEEDS, new_mv.id, weights_src.suffix or '.pt'
            )
            new_mv.model_file_path = str(canonical)
            new_mv.save(update_fields=['model_file_path'])

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
    finally:
        # The per-job dir holds the sliced dataset, the YAML, and the YOLO
        # run output. Everything is disposable once canonical weights have
        # moved out. On failure before the move we lose intermediate
        # weights too, but a failed run produced no ModelVersion that
        # depended on them.
        if job_dir is not None:
            shutil.rmtree(job_dir, ignore_errors=True)


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

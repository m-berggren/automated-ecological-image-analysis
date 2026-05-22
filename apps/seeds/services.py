"""Seed species dataset bootstrap service."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

from django.core.files import File
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.analysis.models import Detection, InferenceRun, JobStatus, ModelVersion
from apps.datasets.models import ImageAsset

logger = logging.getLogger(__name__)


def _base_data() -> Path:
    from django.conf import settings

    return settings.BASE_DIR / 'data' / 'seed'


def bootstrap_species_dataset(species: str) -> Path:
    """Create the folder structure and YAML config for a new seed species.

    Creates:
        root/data/seed/<species>_model/
        root/data/seed/<species>_model/train_sliced/
        root/data/seed/<species>_model/val/images/
        root/data/seed/<species>_model/<species>.yaml

    Returns the path to the YAML file.
    """
    BASE_DATA = _base_data()
    species = species.lower()
    species_dir = BASE_DATA / f'{species}_model'

    if species_dir.exists():
        logger.info(f'Dataset folder for {species} already exists, skipping bootstrap')
        return species_dir / f'{species}.yaml'

    logger.info(f'Bootstrapping dataset folder for {species}')

    (species_dir / 'train_sliced').mkdir(parents=True, exist_ok=True)
    (species_dir / 'val' / 'images').mkdir(parents=True, exist_ok=True)

    yaml_path = species_dir / f'{species}.yaml'
    yaml_path.write_text(
        f'path: {species_dir}\n'
        f'train: train_sliced\n'
        f'val: val/images\n'
        f'\n'
        f'names:\n'
        f'  0: {species}\n'
    )

    logger.info(f'Dataset folder created at {species_dir}')
    return yaml_path


def species_dataset_exists(species: str) -> bool:
    """Check if a species dataset folder already exists."""
    return (_base_data() / f'{species.lower()}_model').exists()


def process_seeds_run(run_id: int):
    try:
        run = InferenceRun.objects.get(pk=run_id)
        run.status = JobStatus.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=['config', 'image_count', 'started_at', 'status'])

        # Read frontend config
        overlap = run.config.get('slice_overlap_ratio', 0.35)
        conf_thresh = run.config.get('confidence_threshold', 0.25)
        selected_seed = run.config.get('selected_seed')

        # Extract the model ID
        model_id = run.config.get('model_version_id')

        if not model_id:
            raise ValueError(
                f'No model version selected for seed type: {selected_seed}'
            )

        # Fetch the model path from the DB
        model_version = ModelVersion.objects.get(pk=model_id)
        model_path = model_version.model_file_path

        # Load the model
        from django.core.files import File
        from sahi.predict import get_sliced_prediction
        from seed_src.inference.inference import generate_prediction_visuals
        from seed_src.utils.helpers import load_model

        from apps.datasets.models import ImageAsset

        model = load_model(model_path)

        images = run.upload.images.all()
        for image_asset in images:
            # Check for pause/cancel
            run.refresh_from_db(fields=['status'])
            if run.status != JobStatus.RUNNING:
                break

            img_path = image_asset.file.path

            # Run SAHI, passing frontend parameters
            result = get_sliced_prediction(
                img_path,
                model,
                slice_height=768,
                slice_width=768,
                overlap_height_ratio=overlap,
                overlap_width_ratio=overlap,
                postprocess_match_threshold=conf_thresh,
            )

            # Extract just the filename
            base_filename = os.path.basename(image_asset.file.name)

            # Generate the path to the annotated prediction image
            annotated_img_path = generate_prediction_visuals(
                result,
                img_path,
                base_filename,
                'ml_pipelines/seed_src/prediction_images/',
            )

            # Save the annotated prediction image to Django's media storage
            with open(annotated_img_path, 'rb') as f:
                annotated_asset = ImageAsset.objects.create(
                    module='seeds', purpose='inference_output', upload=run.upload
                )
                annotated_asset.file.save(f'annotated_{base_filename}', File(f))

            # Link this to the original image for easy access in the UI
            image_asset.metadata['annotated_image_id'] = annotated_asset.id
            image_asset.save()

            # Save detections to DB
            for pred in result.object_prediction_list:
                poly = None

                # Extract OBB points
                if hasattr(pred, 'obb') and pred.obb is not None:
                    poly = pred.obb.points if hasattr(pred.obb, 'points') else pred.obb
                elif hasattr(pred, 'polygon') and pred.polygon is not None:
                    poly = (
                        pred.polygon.exterior
                        if hasattr(pred.polygon, 'exterior')
                        else pred.polygon
                    )
                elif hasattr(pred, 'mask') and pred.mask is not None:
                    poly = pred.mask.segmentation[0]

                # Fallback to standard HBBs if OBB fails
                if poly is None and pred.bbox is not None:
                    bbox = pred.bbox
                    poly = [
                        bbox.minx,
                        bbox.miny,
                        bbox.maxx,
                        bbox.miny,
                        bbox.maxx,
                        bbox.maxy,
                        bbox.minx,
                        bbox.maxy,
                    ]

                if poly is not None:
                    # Flatten the polygon to an 8-point list
                    if isinstance(poly[0], (list, tuple)):
                        flat_poly = [float(c) for point in poly for c in point]
                    else:
                        flat_poly = [float(c) for c in poly]

                    # Extract or calculate the area
                    area = 0.0
                    if hasattr(pred, 'area') and getattr(pred, 'area') is not None:
                        area = float(pred.area.value)
                    elif pred.bbox is not None:
                        # Fallback area calculation: width * height
                        area = float(
                            (pred.bbox.maxx - pred.bbox.minx)
                            * (pred.bbox.maxy - pred.bbox.miny)
                        )

                    # Create the detection record
                    Detection.objects.create(
                        image=image_asset,
                        inference_run=run,
                        bbox={'poly': flat_poly[:8]},
                        polygon=flat_poly[:8],
                        confidence=float(pred.score.value),
                        predicted_class=selected_seed,
                        area=area,
                    )

            run.processed_image_count += 1
            run.save(update_fields=['processed_image_count'])

        if run.status == JobStatus.RUNNING:
            run.status = JobStatus.COMPLETED
            run.completed_at = timezone.now()
            run.save(update_fields=['completed_at', 'status'])
            run.save(update_fields=['status'])

    except Exception as e:
        logger.exception('Seed pipeline failed')
        run.status = JobStatus.FAILED
        run.error_message = str(e)
        run.completed_at = timezone.now()
        run.save(update_fields=['completed_at', 'status'])
        run.save(update_fields=['status', 'error_message'])


def spawn_seeds_pipeline(run):
    thread = threading.Thread(target=process_seeds_run, args=(run.pk,))
    thread.daemon = True
    thread.start()


def generate_export_bundle(run_id: int):
    run = InferenceRun.objects.get(pk=run_id)
    images = run.upload.images.filter(purpose='inference')
    species = run.config.get('selected_seed', 'Unknown')

    # Clean up old export images if the user hits export multiple times
    ImageAsset.objects.filter(upload=run.upload, purpose='export').delete()

    results = []

    for img in images:
        final_active_boxes = 0
        export_asset = None
        detections = Detection.objects.filter(image=img)

        meta = img.metadata or {}
        calc_active = meta.get('calculated_active', 0) if img.metadata else 0
        conf = meta.get('overall_confidence', 0.0) if img.metadata else 0.0

        final_active = 0
        export_asset = None

        # Permanently draw the final status polygons onto the image (green for 'active', red for 'aborted' seeds)
        if img.file and os.path.exists(img.file.path):
            with Image.open(img.file.path) as pil_img:
                pil_img = pil_img.convert('RGB')
                draw = ImageDraw.Draw(pil_img)

                for d in detections:
                    status_val = getattr(d, 'status', 1)

                    if status_val == 2 or str(status_val).lower() == 'confirmed':
                        is_active = True
                    elif status_val == 3 or str(status_val).lower() == 'rejected':
                        is_active = False
                    else:
                        is_active = str(d.predicted_class).lower() == 'active'

                    color = '#22c55e' if is_active else '#ef4444'

                    if is_active:
                        final_active_boxes += 1

                    poly = d.polygon
                    if poly and len(poly) >= 8:
                        draw.polygon(poly[:8], outline=color, width=12)

                base_name = os.path.basename(img.file.name)
                export_name = f'export_{base_name}'

                with tempfile.NamedTemporaryFile(suffix='.jpg') as tmp:
                    pil_img.save(tmp.name, format='JPEG', quality=90)

                    export_asset = ImageAsset.objects.create(
                        module='seeds', purpose='export', upload=run.upload
                    )
                    with open(tmp.name, 'rb') as f:
                        export_asset.file.save(export_name, File(f))

        final_active = meta.get('manual_active_count', final_active_boxes)

        results.append(
            {
                'filename': os.path.basename(img.file.name),
                'species': species.capitalize(),
                'calculated_active': calc_active,
                'confidence': round(conf, 4),
                'final_active': final_active,
                'export_image_url': export_asset.file.url
                if export_asset and export_asset.file
                else None,
            }
        )

    return results

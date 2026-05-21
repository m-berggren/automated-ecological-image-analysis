import threading
import logging
from django.utils import timezone
from apps.analysis.models import JobStatus, Detection, InferenceRun, ModelVersion

logger = logging.getLogger(__name__)

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
        model_id = run.config.get('models', {}).get(selected_seed, {}).get('model_version_id')

        if not model_id:
            raise ValueError(f"No model version selected for seed type: {selected_seed}")

        # Fetch the model path from the DB
        model_version = ModelVersion.objects.get(pk=model_id)
        model_path = model_version.model_file_path

        # Load the model
        from seed_src.utils.helpers import load_model
        from sahi.predict import get_sliced_prediction

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
                postprocess_match_threshold=conf_thresh
            )

            # Save detections to DB
            for pred in result.object_prediction_list:
                poly = None

                # Extract OBB points
                if hasattr(pred, 'obb') and pred.obb is not None:
                    poly = pred.obb.points if hasattr(pred.obb, 'points') else pred.obb
                elif hasattr(pred, 'polygon') and pred.polygon is not None:
                    poly = pred.polygon.exterior if hasattr(pred.polygon, 'exterior') else pred.polygon

                # Fallback to standard HBBs if OBB fails
                if poly is None and pred.bbox is not None:
                    bbox = pred.bbox
                    poly = [bbox.minx, bbox.miny, bbox.maxx, bbox.miny, bbox.maxx, bbox.maxy, bbox.minx, bbox.maxy]

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
                        area = float((pred.bbox.maxx - pred.bbox.minx) * (pred.bbox.maxy - pred.bbox.miny))

                    # Create the detection record
                    Detection.objects.create(
                        image=image_asset,
                        inference_run=run,
                        bbox={'poly': flat_poly[:8]},
                        confidence=float(pred.score.value),
                        predicted_class=selected_seed,
                        area=area
                    )

            run.processed_image_count += 1
            run.save(update_fields=['processed_image_count'])

        if run.status == JobStatus.RUNNING:
            run.status = JobStatus.COMPLETED
            run.completed_at = timezone.now()
            run.save(update_fields=['completed_at', 'status'])
            run.save(update_fields=['status'])

    except Exception as e:
        logger.exception("Seed pipeline failed")
        run.status = JobStatus.FAILED
        run.error_message = str(e)
        run.completed_at = timezone.now()
        run.save(update_fields=['completed_at', 'status'])
        run.save(update_fields=['status', 'error_message'])

def spawn_seeds_pipeline(run):
    thread = threading.Thread(target=process_seeds_run, args=(run.pk,))
    thread.daemon = True
    thread.start()
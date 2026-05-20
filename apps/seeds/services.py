import threading
from django.conf import settings
from apps.analysis.models import JobStatus, Detection

def process_seeds_run(run_id: int):
    from apps.analysis.models import InferenceRun
    run = InferenceRun.objects.get(pk=run_id)
    run.status = JobStatus.RUNNING
    run.save(update_fields=['status'])

    # Read frontend config
    overlap = run.config.get('slice_overlap_ratio', 0.35)
    conf_thresh = run.config.get('confidence_threshold', 0.25)

    # Load YOLO Model
    from seed_src.utils.helpers import load_model
    from seed_src.inference.inference import get_sliced_prediction

    model_path = run.model_version.model_file_path
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
            bbox = [pred.bbox.minx, pred.bbox.miny, pred.bbox.maxx, pred.bbox.maxy]
            Detection.objects.create(
                image=image_asset,
                inference_run=run,
                bbox=bbox,
                confidence=float(pred.score.value),
                predicted_class=run.config.get('selected_seed')
            )

        run.processed_image_count += 1
        run.save(update_fields=['processed_image_count'])

    if run.status == JobStatus.RUNNING:
        run.status = JobStatus.COMPLETED
        run.save(update_fields=['status'])

def spawn_seeds_pipeline(run):
    thread = threading.Thread(target=process_seeds_run, args=(run.pk,))
    thread.daemon = True
    thread.start()
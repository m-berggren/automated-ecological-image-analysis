import os
import shutil
import uuid

from PIL import Image
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import InferenceRun, JobStatus, TrainingJob
from apps.datasets.models import Module
from apps.seeds.reference_seed_service import (
    bulk_calculate_run_seed_status,
    calculate_seed_status,
)
from apps.seeds.services import generate_export_bundle
from apps.seeds.training import _job_dir, _staging_root, spawn_training_job


class SeedTrainingDataUploadView(APIView):
    """POST /api/seeds/training/upload-data/ to stage training images.

    Files land flat under MEDIA_ROOT/training/seeds/staging/<staging_id>/
    {images,labels}/, keyed by a fresh server-generated staging_id per
    request. The split into train/val/test happens inside the training
    job, not here. SeedTrainingJobCreateView consumes the staging dir by
    renaming it into MEDIA_ROOT/training/<job_pk>/.

    Request body: species (required), files (required: mix of images and
    matching .txt labels). Response returns the staging_id the client
    must forward to /start/.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request) -> Response:
        species = request.data.get('species')
        files = request.FILES.getlist('files')

        if not species:
            return Response({'error': 'species is required.'}, status=400)
        if not files:
            return Response({'error': 'No files provided.'}, status=400)

        # Server-generated UUID hex: safe by construction, no validation
        # needed. The client must round-trip it to /start/.
        staging_id = uuid.uuid4().hex

        staging_dir = _staging_root() / staging_id
        img_dir = staging_dir / 'images'
        lbl_dir = staging_dir / 'labels'
        for d in (img_dir, lbl_dir):
            d.mkdir(parents=True, exist_ok=True)

        image_files = [f for f in files if not f.name.lower().endswith('.txt')]
        label_files = {
            f.name.rsplit('.', 1)[0]: f
            for f in files
            if f.name.lower().endswith('.txt')
        }

        def save_file(f, dest_dir):
            with open(dest_dir / f.name, 'wb') as out:
                for chunk in f.chunks():
                    out.write(chunk)

        for f in image_files:
            save_file(f, img_dir)
            stem = f.name.rsplit('.', 1)[0]
            if stem in label_files:
                save_file(label_files[stem], lbl_dir)

        return Response(
            {
                'staging_id': staging_id,
                'species': species,
                'uploaded_images': len(image_files),
                'labels_matched': sum(
                    1 for f in image_files if f.name.rsplit('.', 1)[0] in label_files
                ),
            }
        )


class SeedTrainingJobCreateView(APIView):
    """POST /api/seeds/training/start/ to queue a training job.

    Body:
        species, training_mode (scratch|incremental), epochs,
        source_model_id (required for incremental),
        staging_id (required) - returned by /upload-data/,
        val_ratio (default 0.1), test_ratio (default 0.0).

    The staging dir is moved into MEDIA_ROOT/training/<job_pk>/ before the
    worker starts, so the worker sees a self-contained job tree.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        species = request.data.get('species')
        training_mode = request.data.get('training_mode', 'scratch')
        epochs = int(request.data.get('epochs', 90))
        source_model_id = request.data.get('source_model_id')
        staging_id = request.data.get('staging_id')
        val_ratio = float(request.data.get('val_ratio', 0.1))
        test_ratio = float(request.data.get('test_ratio', 0.0))

        if not species:
            return Response({'error': 'species is required.'}, status=400)
        if training_mode not in ('scratch', 'incremental'):
            return Response(
                {'error': "training_mode must be 'scratch' or 'incremental'."},
                status=400,
            )
        if training_mode == 'incremental' and not source_model_id:
            return Response(
                {'error': 'source_model_id is required for incremental training.'},
                status=400,
            )
        if not staging_id:
            return Response(
                {'error': 'staging_id is required (upload files first).'},
                status=400,
            )

        # Resolve and confirm the path lives under _staging_root. Cheap
        # belt-and-braces against a client (or compromised session)
        # supplying '../' or an absolute path: even though the upload
        # endpoint generates safe ids, the value round-trips through the
        # client so we don't trust it on the way back.
        staging_root = _staging_root().resolve()
        try:
            staging_dir = (_staging_root() / staging_id).resolve()
            staging_dir.relative_to(staging_root)
        except (ValueError, OSError):
            return Response({'error': 'invalid staging_id'}, status=400)

        if not staging_dir.exists():
            return Response(
                {'error': f'staging session {staging_id} not found'},
                status=404,
            )

        job = TrainingJob.objects.create(
            module=Module.SEEDS,
            status=JobStatus.PENDING,
            initiated_by=request.user,
            total_epochs=epochs,
            config={
                'species': species.lower(),
                'training_mode': training_mode,
                'epochs': epochs,
                'source_model_id': source_model_id,
                'val_ratio': val_ratio,
                'test_ratio': test_ratio,
            },
        )

        # Move staging into the job dir so the worker reads from
        # MEDIA_ROOT/training/<job_pk>/{images,labels}/. shutil.move handles
        # cross-device too; both paths are under MEDIA_ROOT in practice.
        target_dir = _job_dir(job.pk)
        try:
            shutil.move(str(staging_dir), str(target_dir))
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = f'Failed to attach staging dir: {e}'
            job.save(update_fields=['status', 'error_message'])
            return Response(
                {'error': f'Failed to attach staging dir: {e}'},
                status=500,
            )

        spawn_training_job(job)

        return Response(
            {
                'id': job.pk,
                'status': job.status,
                'species': species,
                'training_mode': training_mode,
                'epochs': epochs,
            },
            status=201,
        )


class SeedReferenceReviewView(APIView):
    def get(self, request, run_id):
        run = InferenceRun.objects.get(id=run_id)

        images_qs = run.upload.images.filter(purpose='inference')

        response_images = []

        for img in images_qs:
            # Polygons render as SVG overlays in the frontend, so we serve
            # the original image directly.
            if img.width and img.height:
                img_width, img_height = img.width, img.height
            else:
                with Image.open(img.file.path) as im:
                    img_width, img_height = im.size

            img_detections = run.detections.filter(image=img)

            response_images.append(
                {
                    'id': img.id,
                    'image_url': request.build_absolute_uri(img.file.url),
                    'filename': os.path.basename(img.file.name),
                    'width': img_width,
                    'height': img_height,
                    'seed_range_min': img.metadata.get('seed_range_min', 0)
                    if img.metadata
                    else 0,
                    'seed_range_max': img.metadata.get('seed_range_max', 0)
                    if img.metadata
                    else 0,
                    'overall_confidence': img.metadata.get('overall_confidence', 0.0)
                    if img.metadata
                    else 0.0,
                    'manual_active_count': img.metadata.get('manual_active_count')
                    if img.metadata
                    else None,
                    'detections': [
                        {
                            'id': d.id,
                            'confidence': d.confidence,
                            # Raw pixels
                            'bbox': d.bbox,
                            'polygon': d.polygon,
                            'class': d.predicted_class,
                        }
                        for d in img_detections
                    ],
                }
            )

        return Response(
            {
                'run': {
                    'id': run.id,
                    'name': run.name,
                },
                'reference_seeds': run.reference_seeds or {},
                'images': response_images,
            }
        )


class SeedReferenceView(APIView):
    def post(self, request, run_id):
        reference_id = request.data['reference_detection_id']
        image_id = request.data['image_id']

        run = InferenceRun.objects.get(id=run_id)

        # Save reference selection for this image into the run
        refs = run.reference_seeds or {}
        refs[str(image_id)] = reference_id
        run.reference_seeds = refs
        run.save(update_fields=['reference_seeds'])

        try:
            result = calculate_seed_status(
                reference_detection_id=reference_id, image_id=image_id
            )
            return Response(result)
        except Exception as e:
            import traceback

            traceback.print_exc()  # prints full traceback to Django terminal
            return Response({'error': str(e)}, status=500)


class SeedRunBulkCalculateView(APIView):
    def post(self, request, run_id):
        try:
            results = bulk_calculate_run_seed_status(run_id)
            return Response({'status': 'success', 'results': results})
        except Exception as e:
            import traceback

            traceback.print_exc()
            return Response({'error': str(e)}, status=500)


class SeedExportView(APIView):
    def get(self, request, run_id):
        try:
            results = generate_export_bundle(run_id)
            # The re-annotated images have absolute URLs for the frontend
            for r in results:
                if r['export_image_url']:
                    r['export_image_url'] = request.build_absolute_uri(
                        r['export_image_url']
                    )
            return Response({'data': results})
        except Exception as e:
            import traceback

            traceback.print_exc()
            return Response({'error': str(e)}, status=500)


class ImageManualCountView(APIView):
    def post(self, request, image_id):
        try:
            from apps.datasets.models import ImageAsset

            img = ImageAsset.objects.get(id=image_id)
            if not isinstance(img.metadata, dict):
                img.metadata = {}

            img.metadata['manual_active_count'] = int(
                request.data.get('manual_count', 0)
            )
            img.save(update_fields=['metadata'])
            return Response({'status': 'success'})
        except Exception as e:
            import traceback

            traceback.print_exc()
            return Response({'error': str(e)}, status=500)

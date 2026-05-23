import os
import random
from pathlib import Path

from PIL import Image
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import InferenceRun, JobStatus, TrainingJob
from apps.datasets.models import ImageAsset, Module
from apps.seeds.reference_seed_service import (
    bulk_calculate_run_seed_status,
    calculate_seed_status,
)
from apps.seeds.services import bootstrap_species_dataset, generate_export_bundle
from apps.seeds.training import spawn_training_job


from django.conf import settings

def _base_data() -> Path:
    return Path(settings.BASE_DIR) / 'data' / 'seed'

class SeedTrainingDataUploadView(APIView):
    """POST /api/seeds/training/upload-data/ to upload training images."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request) -> Response:
        species = request.data.get('species')
        files = request.FILES.getlist('files')
        val_split = float(request.data.get('val_split', 0.2))

        if not species:
            return Response({'error': 'species is required.'}, status=400)
        if not files:
            return Response({'error': 'No files provided.'}, status=400)

        species_dir = _base_data() / f'{species.lower()}_model'
        train_img_dir = species_dir / 'train_sliced' / 'images'
        train_lbl_dir = species_dir / 'train_sliced' / 'labels'
        val_img_dir   = species_dir / 'val' / 'images'
        val_lbl_dir   = species_dir / 'val' / 'labels'

        print(f'Upload endpoint hit — species: {species}, files: {len(files)}')
        print(f'Saving to train_img_dir: {train_img_dir}')
        print(f'Saving to val_img_dir: {val_img_dir}')

        for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
            d.mkdir(parents=True, exist_ok=True)

        image_files = [f for f in files if not f.name.endswith('.txt')]
        label_files  = {f.name.replace('.txt', ''): f for f in files if f.name.endswith('.txt')}

        random.shuffle(image_files)
        n_val = max(1, int(len(image_files) * val_split))
        val_imgs   = image_files[:n_val]
        train_imgs = image_files[n_val:]

        def save_file(f, dest_dir):
            dest = dest_dir / f.name
            with open(dest, 'wb') as out:
                for chunk in f.chunks():
                    out.write(chunk)

        for f in train_imgs:
            save_file(f, train_img_dir)
            stem = f.name.rsplit('.', 1)[0]
            if stem in label_files:
                save_file(label_files[stem], train_lbl_dir)

        for f in val_imgs:
            save_file(f, val_img_dir)
            stem = f.name.rsplit('.', 1)[0]
            if stem in label_files:
                save_file(label_files[stem], val_lbl_dir)

        print(f'Saved {len(train_imgs)} train images, {len(val_imgs)} val images')

        return Response({
            'train_images': len(train_imgs),
            'val_images': len(val_imgs),
            'labels_matched': sum(
                1 for f in image_files
                if f.name.rsplit('.', 1)[0] in label_files
            ),
            'total': len(image_files),
        })

class SeedTrainingJobCreateView(APIView):
    """POST /api/seeds/training/start/ to bootstrap dataset folder and queue a training job."""

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        species = request.data.get('species')
        training_mode = request.data.get('training_mode', 'scratch')
        epochs = int(request.data.get('epochs', 90))
        source_model_id = request.data.get('source_model_id')

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

        # Bootstrap dataset folder for new species
        if training_mode == 'scratch':
            try:
                bootstrap_species_dataset(species)
            except Exception as e:
                return Response({'error': f'Failed to create dataset folder: {e}'}, status=500)

        job = TrainingJob.objects.create(
            module=Module.SEEDS,
            status=JobStatus.PENDING,
            initiated_by=request.user,
            config={
                'species': species.lower(),
                'training_mode': training_mode,
                'epochs': epochs,
                'source_model_id': source_model_id,
            },
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
            # Extract the annotated image ID to display the annotated image on the Review page
            annotated_id = (
                img.metadata.get('annotated_image_id') if img.metadata else None
            )
            if annotated_id:
                try:
                    display_img = ImageAsset.objects.get(id=annotated_id)
                except ImageAsset.DoesNotExist:
                    display_img = img  # Fallback to original if deleted
            else:
                display_img = img

            if display_img.width and display_img.height:
                img_width, img_height = display_img.width, display_img.height
            else:
                with Image.open(img.file.path) as im:
                    img_width, img_height = im.size

            img_detections = run.detections.filter(image=img)

            response_images.append(
                {
                    'id': img.id,
                    'image_url': request.build_absolute_uri(display_img.file.url),
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

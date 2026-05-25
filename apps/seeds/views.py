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
from ml_pipelines.seed_src.training.slice_dataset import process_image

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
        training_mode = request.data.get('training_mode', 'scratch')

        if not species:
            return Response({'error': 'species is required.'}, status=400)
        if not files:
            return Response({'error': 'No files provided.'}, status=400)

        species_dir = _base_data() / f'{species.lower()}_model'

        # Save to RAW folders (before slicing)
        raw_train_img_dir = species_dir / 'train' / 'images'
        raw_train_lbl_dir = species_dir / 'train' / 'labels'
        raw_val_img_dir   = species_dir / 'val' / 'images'
        raw_val_lbl_dir   = species_dir / 'val' / 'labels'

        # Create output dirs for sliced images
        sliced_train_img_dir = species_dir / 'train_sliced' / 'images'
        sliced_train_lbl_dir = species_dir / 'train_sliced' / 'labels'

        # Create all dirs
        for d in [raw_train_img_dir, raw_train_lbl_dir, raw_val_img_dir, raw_val_lbl_dir,
                sliced_train_img_dir, sliced_train_lbl_dir]:
            d.mkdir(parents=True, exist_ok=True)

        print(f'Upload endpoint hit — species: {species}, files: {len(files)}')
        print(f'Saving to raw_train_img_dir: {raw_train_img_dir}')
        print(f'Saving to raw_val_img_dir: {raw_val_img_dir}')

        # For incremental training, check existing images to avoid duplicates
        existing_images = set()
        if training_mode == 'incremental':
            # Check existing training images
            for f in raw_train_img_dir.glob('*.[jJ][pP][gG]*'):
                existing_images.add(f.stem)
            # Check existing val images
            for f in raw_val_img_dir.glob('*.[jJ][pP][gG]*'):
                existing_images.add(f.stem)
            print(f"Incremental mode - found {len(existing_images)} existing images")

        image_files = [f for f in files if not f.name.endswith('.txt')]
        label_files  = {f.name.replace('.txt', ''): f for f in files if f.name.endswith('.txt')}

        # Filter out images that already exist (for incremental training)
        if training_mode == 'incremental':
            new_images = []
            for f in image_files:
                stem = f.name.rsplit('.', 1)[0]
                if stem not in existing_images:
                    new_images.append(f)
                else:
                    print(f"Skipping existing image: {f.name}")
            image_files = new_images
            print(f"New images to add: {len(image_files)}")

        if not image_files:
            return Response({
                'message': 'No new images to add. All images already exist.',
                'train_images': 0,
                'val_images': 0,
                'total': 0,
            })

        random.shuffle(image_files)
        n_val = max(1, int(len(image_files) * val_split))
        val_imgs   = image_files[:n_val]
        train_imgs = image_files[n_val:]

        def save_file(f, dest_dir):
            dest = dest_dir / f.name
            with open(dest, 'wb') as out:
                for chunk in f.chunks():
                    out.write(chunk)

        # Save raw training images
        for f in train_imgs:
            save_file(f, raw_train_img_dir)
            stem = f.name.rsplit('.', 1)[0]
            if stem in label_files:
                save_file(label_files[stem], raw_train_lbl_dir)

        # Save raw validation images
        for f in val_imgs:
            save_file(f, raw_val_img_dir)
            stem = f.name.rsplit('.', 1)[0]
            if stem in label_files:
                save_file(label_files[stem], raw_val_lbl_dir)

        print(f'Saved {len(train_imgs)} train images, {len(val_imgs)} val images')

        # Run the slicer on all images
        try:
            print("Starting slicing process...")

            # Process training images to train_sliced/
            all_train_images = list(raw_train_img_dir.glob('*.[jJ][pP][gG]*'))
            print(f"Total training images to slice: {len(all_train_images)}")

            for idx, img_file in enumerate(all_train_images, 1):
                lbl_file = raw_train_lbl_dir / f"{img_file.stem}.txt"
                if lbl_file.exists():
                    print(f"  [{idx}/{len(all_train_images)}] Slicing {img_file.name}...")
                    process_image(str(img_file), str(lbl_file), str(sliced_train_img_dir), str(sliced_train_lbl_dir))
                else:
                    print(f"  [WARNING] No label file for {img_file.name}")

            # Count how many sliced files were created
            sliced_train_count = len(list(sliced_train_img_dir.glob('*.png')))
            print(f"Slicing completed successfully! Created {sliced_train_count} training slices")

        except Exception as e:
            print(f"Slicing failed: {e}")

        return Response({
            'train_images': len(train_imgs),
            'val_images': len(val_imgs),
            'total_new_images': len(image_files),
            'total_existing_images': len(existing_images) if training_mode == 'incremental' else 0,
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
            total_epochs=epochs,
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

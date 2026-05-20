from pathlib import Path
import random

from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.analysis.models import TrainingJob, JobStatus
from apps.datasets.models import Module
from apps.seeds.services import bootstrap_species_dataset
from apps.seeds.training import spawn_training_job

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
        train_img_dir = species_dir / 'train_sliced'
        train_lbl_dir = species_dir / 'train_sliced' / 'labels'
        val_img_dir   = species_dir / 'val_sliced'
        val_lbl_dir   = species_dir / 'val_sliced' / 'labels'

        for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Separate images and labels
        image_files = [f for f in files if not f.name.endswith('.txt')]
        label_files  = {f.name.replace('.txt', ''): f for f in files if f.name.endswith('.txt')}

        # Shuffle and split images
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
            return Response({'error': "training_mode must be 'scratch' or 'incremental'."}, status=400)
        if training_mode == 'incremental' and not source_model_id:
            return Response({'error': 'source_model_id is required for incremental training.'}, status=400)

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

        return Response({
            'id': job.pk,
            'status': job.status,
            'species': species,
            'training_mode': training_mode,
            'epochs': epochs,
        }, status=201)
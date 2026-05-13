import csv
from collections import Counter
from pathlib import Path

from django.db import transaction
from django.db.models import QuerySet
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    TrainingJob,
)
from apps.analysis.serializers import (
    DetectionReviewSerializer,
    TrainingJobDetailSerializer,
)
from apps.datasets.models import Module

from .serializers import (
    PollinatorDetectionSerializer,
    PollinatorTrainingCreateSerializer,
)
from .training import (
    POLLINATOR_CLASSES,
    _collect_binary_pool,
    _collect_detector_pool,
    _collect_group_pool,
    _consumed_detection_ids,
    spawn_training_job,
)

_POLLINATOR_DETECTION_QS = Detection.objects.filter(
    inference_run__module=Module.POLLINATORS
).select_related('image', 'pollinator_detection')


# One row per image, with per-class counts of reviewer-validated detections
# (accepted: confirmed or corrected; rejected and unreviewed don't count).
# Empty photos still get a row of zeros so the CSV doubles as a survey
# denominator for visit-rate / occupancy stats.
_CSV_FIELDS = [
    'session',
    'image_name',
    'camera_name',
    'datetime',
    'weather',
    'fly_count',
    'bumblebee_count',
    'butterfly_moth_count',
    'other_count',
    'total_count',
]

# DB class -> lab class. butterfly_moth is also the column-name root, so
# this drives both the count bucket and any future per-class column.
_CLASS_TO_LAB = {
    'fly': 'fly',
    'bumblebee': 'bumblebee',
    'butterfly': 'butterfly_moth',
    'other': 'other',
}

_COUNT_BUCKETS = ('fly', 'bumblebee', 'butterfly_moth', 'other')


def _camera_name(image) -> str:
    exif = image.exif or {}
    make = (exif.get('Make') or '').strip()
    model = (exif.get('Model') or '').strip()
    return f'{make} {model}'.strip()


class _Echo:
    """File-like that returns whatever is written. Used by csv.writer to
    produce one CSV row per StreamingHttpResponse chunk."""

    def write(self, value: str) -> str:
        return value


def _build_image_row(image, counts: dict[str, int], session: str) -> dict:
    return {
        'session': session,
        'image_name': Path(image.file.name).name if image.file else '',
        'camera_name': _camera_name(image),
        'datetime': image.captured_at.isoformat() if image.captured_at else '',
        'weather': image.weather or '',
        'fly_count': counts.get('fly', 0),
        'bumblebee_count': counts.get('bumblebee', 0),
        'butterfly_moth_count': counts.get('butterfly_moth', 0),
        'other_count': counts.get('other', 0),
        'total_count': sum(counts.get(b, 0) for b in _COUNT_BUCKETS),
    }


class PollinatorRunExportCSVView(APIView):
    """GET /api/pollinator/runs/<run_id>/export.csv

    Streams one row per image in the run's upload, with per-class counts of
    reviewer-validated detections (status=accepted, i.e. confirmed or
    corrected). Photos with zero validated detections still appear as
    all-zero rows so the file is a complete survey record (denominator for
    visit-rate / occupancy stats).
    """

    def get(self, request: Request, run_id: int) -> StreamingHttpResponse:
        run = get_object_or_404(
            InferenceRun.objects.select_related('upload'),
            pk=run_id,
            module=Module.POLLINATORS,
        )

        # Pre-aggregate validated detections by image_id so we can emit one
        # streamed row per image without a per-image DB hit.
        counts_by_image: dict[int, dict[str, int]] = {}
        validated = (
            Detection.objects
            .filter(
                inference_run=run,
                status=DetectionStatus.ACCEPTED,
                excluded_from_export=False,
            )
            .values_list('image_id', 'predicted_class', 'reviewer_label')
        )
        for image_id, predicted, reviewer in validated:
            effective = (reviewer or predicted or '').lower()
            bucket = _CLASS_TO_LAB.get(effective, effective)
            if bucket not in _COUNT_BUCKETS:
                continue
            counts_by_image.setdefault(image_id, {})
            counts_by_image[image_id][bucket] = (
                counts_by_image[image_id].get(bucket, 0) + 1
            )

        upload = run.upload
        if upload is None:
            images = []
        else:
            images = upload.images.order_by('captured_at', 'id').iterator(
                chunk_size=500,
            )
        session = run.name or f'Run #{run.pk}'

        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(_CSV_FIELDS)
            for img in images:
                row = _build_image_row(
                    img, counts_by_image.get(img.id, {}), session,
                )
                yield writer.writerow([row[k] for k in _CSV_FIELDS])

        filename = f'run-{run.pk}-images.csv'
        response = StreamingHttpResponse(rows(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PollinatorDetectionListView(generics.ListAPIView):
    """GET /api/pollinator/runs/<run_id>/detections/

    Lists pollinator detections for a run. Filters by module so a non-
    pollinator run id returns an empty list rather than raising on the
    missing pollinator_detection relation in the serializer.
    """

    serializer_class = PollinatorDetectionSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Detection]:
        return _POLLINATOR_DETECTION_QS.filter(
            inference_run_id=self.kwargs['run_id'],
        ).order_by('id')


class PollinatorDetectionDetailView(generics.RetrieveUpdateAPIView):
    """GET   /api/pollinator/detections/<id>/   read one pollinator detection.
    PATCH /api/pollinator/detections/<id>/   apply a review action.

    PATCH body uses the shared reviewer vocabulary (DetectionReviewSerializer);
    response is rendered in the pollinator read shape.
    """

    queryset = _POLLINATOR_DETECTION_QS
    lookup_field = 'pk'

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.request.method in ('PATCH', 'PUT'):
            return DetectionReviewSerializer
        return PollinatorDetectionSerializer

    def update(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        write = DetectionReviewSerializer(
            instance=instance,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        write.is_valid(raise_exception=True)
        write.save()
        return Response(
            PollinatorDetectionSerializer(instance, context={'request': request}).data,
        )


class PollinatorTrainingCreateView(generics.CreateAPIView):
    """POST /api/pollinator/training/

    Body: {name?, config: {track, from_model_version_id, epochs?, train_split?,
    val_split?, test_split?, stratified?, class_filter?, img_size?}}

    Eligibility is computed server-side from Detection.status (per-track rules
    in apps/pollinator/training.py) minus already-consumed detections from
    completed jobs for the same track. The UI can preview the pool size via
    GET /api/pollinator/training/pool/?track=<track>.

    Creates a TrainingJob (module='pollinators', status='pending'), spawns a
    daemon thread to run the training, returns the job in detail shape so the
    UI can immediately start polling.
    """

    serializer_class = PollinatorTrainingCreateSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        # Refuse if another pollinator training job is already in flight.
        # Concurrent training would contend for the same GPU/CPU and
        # produce noisy weights; one at a time.
        busy = TrainingJob.objects.filter(
            module=Module.POLLINATORS,
            status__in=(JobStatus.PENDING, JobStatus.RUNNING),
        ).first()
        if busy is not None:
            return Response(
                {
                    'error': (
                        f'Another pollinator training job is already running '
                        f'(#{busy.pk}, status={busy.status}). Wait for it to '
                        f'finish or cancel it before starting a new one.'
                    ),
                    'busy_job_id': busy.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )

        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)

        job = TrainingJob.objects.create(
            module=Module.POLLINATORS,
            name=write.validated_data.get('name', ''),
            config=write.validated_data['config'],
            initiated_by=request.user,
        )
        # Defer the worker spawn until commit so it sees the row.
        transaction.on_commit(lambda: spawn_training_job(job))

        return Response(
            TrainingJobDetailSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )


class PollinatorTrainingPoolView(APIView):
    """GET /api/pollinator/training/pool/?track=<track>

    Returns the per-track count of detections (or images, for the detector)
    that are eligible to train on right now: status != pending and not yet
    consumed by a successful previous training run for the same track.

    Response shape:
        {
          "track": "detector",
          "available": 42,        # unit: images for detector, detections for classifiers
          "consumed": 12,         # detections already used in past completed jobs
          "by_class": {           # absent for binary (only insect/background)
            "bumblebee": 5, "fly": 18, "butterfly": 4, "other": 15
          }
        }
    """

    def get(self, request: Request) -> Response:
        track = request.query_params.get('track')
        if track not in ('detector', 'binary', 'group'):
            return Response(
                {'error': "track must be one of 'detector', 'binary', 'group'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        consumed = len(_consumed_detection_ids(track))

        if track == 'detector':
            eligible = _collect_detector_pool(POLLINATOR_CLASSES)
            by_class = Counter(
                (d.reviewer_label or d.predicted_class) for d in eligible
            )
            return Response(
                {
                    'track': track,
                    'available': len({d.image_id for d in eligible}),
                    'consumed': consumed,
                    'by_class': dict(by_class),
                }
            )

        if track == 'binary':
            accepted, rejected = _collect_binary_pool()
            return Response(
                {
                    'track': track,
                    'available': len(accepted) + len(rejected),
                    'consumed': consumed,
                    'by_class': {
                        'insect': len(accepted),
                        'background': len(rejected),
                    },
                }
            )

        # group
        eligible = _collect_group_pool(POLLINATOR_CLASSES)
        by_class = Counter((d.reviewer_label or d.predicted_class) for d in eligible)
        return Response(
            {
                'track': track,
                'available': len(eligible),
                'consumed': consumed,
                'by_class': dict(by_class),
            }
        )

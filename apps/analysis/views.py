import logging

from django.db import transaction
from django.db.models import QuerySet
from rest_framework import generics, status
from rest_framework.response import Response

from apps.datasets.models import UploadStatus

from .models import Detection, InferenceRun, ModelVersion
from .serializers import (
    DetectionSerializer,
    InferenceRunCreateSerializer,
    InferenceRunDetailSerializer,
    InferenceRunListSerializer,
    ModelVersionSerializer,
)
from .services import spawn_inference_pipeline

logger = logging.getLogger(__name__)


class ModelVersionListView(generics.ListAPIView):
    """GET /api/analysis/models/?module=<module>

    Lists trained model versions, optionally filtered by module. Newest first.
    Returns a flat JSON array (no pagination) to match the frontend's expected shape.
    """

    serializer_class = ModelVersionSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ModelVersion]:
        qs = ModelVersion.objects.all().order_by('-created_at')
        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module=module)
        return qs


class InferenceRunListCreateView(generics.ListCreateAPIView):
    """GET  /api/analysis/runs/?module=<module>  list runs (newest first).
    POST /api/analysis/runs/                   create a new run (status=pending).

    Create snapshots image_count from the upload's image count at submission
    time. The actual pipeline does not run yet at this tier; status stays
    pending until the worker (later tier) picks it up.
    """

    pagination_class = None

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InferenceRunCreateSerializer
        return InferenceRunListSerializer

    def get_queryset(self) -> QuerySet[InferenceRun]:
        qs = InferenceRun.objects.all().order_by('-created_at')
        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module=module)
        return qs

    def create(self, request, *args, **kwargs) -> Response:
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        upload = write.validated_data['upload']
        run = InferenceRun.objects.create(
            module=write.validated_data['module'],
            name=write.validated_data.get('name', ''),
            upload=upload,
            config=write.validated_data.get('config', {}),
            initiated_by=request.user,
            image_count=upload.images.count(),
        )
        if upload.status == UploadStatus.DRAFT:
            upload.status = UploadStatus.READY
            upload.save(update_fields=['status'])
        # Spawn the run in a background thread after the transaction commits
        # so the worker can see the row. Returns immediately with status=pending.
        transaction.on_commit(lambda: spawn_inference_pipeline(run))
        return Response(
            InferenceRunDetailSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class InferenceRunDetailView(generics.RetrieveAPIView):
    """GET /api/analysis/runs/<id>/

    Returns the full run record including config and activity_log. Polled
    by the frontend's detect/review pages while the run is in progress.
    """

    queryset = InferenceRun.objects.all()
    serializer_class = InferenceRunDetailSerializer
    lookup_field = 'pk'


class DetectionListView(generics.ListAPIView):
    """GET /api/analysis/runs/<run_id>/detections/

    Lists detections for a run in id order. select_related on the image
    avoids an N+1 when the serializer reads the file name.
    """

    serializer_class = DetectionSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Detection]:
        return (
            Detection.objects
            .filter(inference_run_id=self.kwargs['run_id'])
            .select_related('image')
            .order_by('id')
        )

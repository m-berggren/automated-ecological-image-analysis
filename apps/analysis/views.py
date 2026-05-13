import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.datasets.models import UploadStatus
from apps.pollinator.services import spawn_inference_pipeline

from .models import Detection, InferenceRun, ModelVersion, TrainingJob
from .serializers import (
    REVIEWER_STATUS_MAP,
    DetectionBulkReviewSerializer,
    InferenceRunCreateSerializer,
    InferenceRunDetailSerializer,
    InferenceRunListSerializer,
    ModelVersionSerializer,
    TrainingJobDetailSerializer,
    TrainingJobListSerializer,
)

logger = logging.getLogger(__name__)


def _parse_bool(value: str) -> bool | None:
    if value is None:
        return None
    if value.lower() in ('true', '1', 'yes'):
        return True
    if value.lower() in ('false', '0', 'no'):
        return False
    return None


def _extract_checkpoint_metadata(path: Path) -> dict:
    """Pull a small set of standard metadata keys from a torch checkpoint.

    Returns {} on any failure (non-torch file, corrupt pickle, missing torch).
    Reads both our own trainer outputs (img_size, arch, epoch, model_type,
    best_val_f1) and ultralytics YOLO train_args (imgsz, epochs, batch, lr0).
    """
    try:
        import torch

        ckpt = torch.load(str(path), map_location='cpu', weights_only=False)
    except Exception:
        logger.exception(f'Could not introspect checkpoint at {path}')
        return {}

    if not isinstance(ckpt, dict):
        return {}

    out: dict = {}
    for key in ('img_size', 'arch', 'epoch', 'model_type', 'best_val_f1'):
        v = ckpt.get(key)
        if v is not None and not callable(v):
            out[key] = v

    train_args = ckpt.get('train_args')
    if isinstance(train_args, dict):
        for key in ('imgsz', 'epochs', 'batch', 'lr0', 'optimizer'):
            if key in train_args:
                out[f'yolo_{key}'] = train_args[key]

    return out


class ModelVersionListCreateView(generics.ListAPIView):
    """GET  /api/analysis/models/?module=<module> - list versions (anyone).
    POST /api/analysis/models/ - create a version from an uploaded weights
    file (staff only).

    POST is multipart/form-data with fields:
        module, kind, version_name, description, weights_file
    On success the file is written to MEDIA_ROOT/models/<module>/<version>.<ext>,
    .pth metadata is introspected into parameters, and the new ModelVersion
    is returned.
    """

    serializer_class = ModelVersionSerializer
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[ModelVersion]:
        qs = ModelVersion.objects.all().order_by('-created_at')
        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module=module)
        return qs

    def post(self, request: Request, *args, **kwargs) -> Response:
        module = (request.data.get('module') or '').strip()
        kind = (request.data.get('kind') or '').strip()
        version_name = (request.data.get('version_name') or '').strip()
        description = (request.data.get('description') or '').strip()
        upload = request.FILES.get('weights_file')

        if not module or not version_name:
            return Response(
                {'detail': 'module and version_name are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload:
            return Response(
                {'detail': 'weights_file is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ModelVersion.objects.filter(version_name=version_name).exists():
            return Response(
                {'detail': f'version_name "{version_name}" already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dest_dir = Path(settings.MEDIA_ROOT) / 'models' / module
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(upload.name).suffix or '.bin'
        dest = dest_dir / f'{version_name}{ext}'
        with dest.open('wb') as out:
            for chunk in upload.chunks():
                out.write(chunk)

        parameters = _extract_checkpoint_metadata(dest)

        mv = ModelVersion.objects.create(
            module=module,
            kind=kind,
            version_name=version_name,
            model_file_path=str(dest),
            description=description,
            parameters=parameters,
            created_by=request.user if request.user.is_authenticated else None,
        )
        logger.info(
            f'ModelVersion {mv.pk} created by {request.user}: '
            f'{module}/{version_name} ({dest.stat().st_size} bytes)'
        )
        return Response(
            ModelVersionSerializer(mv).data,
            status=status.HTTP_201_CREATED,
        )


class InferenceRunListCreateView(generics.ListCreateAPIView):
    """GET  /api/analysis/runs/?module=<module>  list runs (newest first).
    POST /api/analysis/runs/                   create a new run (status=pending).

    image_count is snapshotted from the upload at submission time so the
    progress denominator stays stable if images are added to the upload
    after the run is queued.
    """

    pagination_class = None

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.request.method == 'POST':
            return InferenceRunCreateSerializer
        return InferenceRunListSerializer

    def get_queryset(self) -> QuerySet[InferenceRun]:
        qs = InferenceRun.objects.all().order_by('-created_at')
        params = self.request.query_params

        module = params.get('module')
        if module:
            qs = qs.filter(module=module)

        run_status = params.get('status')
        if run_status:
            qs = qs.filter(status=run_status)

        upload = params.get('upload')
        if upload:
            qs = qs.filter(upload_id=upload)

        archived = _parse_bool(params.get('archived'))
        if archived is None:
            qs = qs.filter(archived=False)
        else:
            qs = qs.filter(archived=archived)

        return qs

    def create(self, request: Request, *args, **kwargs) -> Response:
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        upload = write.validated_data['upload']
        run = InferenceRun.objects.create(
            module=write.validated_data['module'],
            name=write.validated_data.get('name', ''),
            upload=upload,
            model_version=write.validated_data.get('model_version'),
            config=write.validated_data.get('config', {}),
            initiated_by=request.user,
            image_count=upload.images.count(),
        )
        if upload.status == UploadStatus.DRAFT:
            upload.status = UploadStatus.READY
            upload.save(update_fields=['status'])
        # Defer until commit so the worker thread sees the row.
        transaction.on_commit(lambda: spawn_inference_pipeline(run))
        return Response(
            InferenceRunDetailSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class InferenceRunDetailView(generics.RetrieveDestroyAPIView):
    """GET    /api/analysis/runs/<id>/  read the run (polled while running).
    DELETE /api/analysis/runs/<id>/  remove the run and everything tied to it.

    DB cascade handles Detection and PollinatorDetection (via FK on_delete).
    The on-disk run output dir (MEDIA_ROOT/runs/<id>/, holding crops,
    yolo_crops, preprocessing, results.json) is removed explicitly because
    Django's storage backend never auto-deletes ImageField files. Source
    images are left alone — they live on the Upload and can be reused by
    other runs.

    Refuses to delete an in-flight run (pending/running) to keep the
    worker from racing the delete; cancel it first.
    """

    queryset = InferenceRun.objects.all()
    serializer_class = InferenceRunDetailSerializer
    lookup_field = 'pk'

    def perform_destroy(self, instance: InferenceRun) -> None:
        from apps.analysis.models import JobStatus

        if instance.status in (JobStatus.PENDING, JobStatus.RUNNING):
            raise serializers.ValidationError(
                {
                    'error': (
                        f'Run is still {instance.status}. Cancel it before '
                        f'deleting so the background worker stops cleanly.'
                    ),
                },
            )
        # Delete the on-disk output directory if it exists. Wrap in try/
        # except so DB cleanup still runs even if the filesystem step
        # fails (e.g., perms, partial dir).
        run_dir = Path(settings.MEDIA_ROOT) / 'runs' / str(instance.pk)
        if run_dir.exists():
            import shutil

            try:
                shutil.rmtree(run_dir)
            except OSError:
                logger.exception(f'Failed to remove {run_dir}; continuing with DB delete')
        super().perform_destroy(instance)


class DetectionBulkView(APIView):
    """POST /api/analysis/detections/bulk/

    Apply the same reviewer action to many detections in one request.
    Single DB UPDATE; response carries the count actually updated.
    """

    def post(self, request: Request) -> Response:
        write = DetectionBulkReviewSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        ids = write.validated_data['ids']
        rs = write.validated_data['reviewer_status']
        update_data: dict = {
            'status': REVIEWER_STATUS_MAP[rs],
            'reviewed_by': request.user,
            'reviewed_at': timezone.now(),
            'reviewer_label': (
                write.validated_data.get('reviewer_label') or ''
                if rs == 'corrected'
                else ''
            ),
        }
        count = Detection.objects.filter(pk__in=ids).update(**update_data)
        return Response({'updated': count})


class TrainingJobListView(generics.ListAPIView):
    """GET /api/analysis/training/?module=<module>&status=<status>

    Module-agnostic. Pollinator creates jobs via POST /api/pollinator/training/;
    seeds will get its own create endpoint. Listing is shared."""

    serializer_class = TrainingJobListSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[TrainingJob]:
        qs = TrainingJob.objects.all().order_by('-started_at')
        params = self.request.query_params
        module = params.get('module')
        if module:
            qs = qs.filter(module=module)
        job_status = params.get('status')
        if job_status:
            qs = qs.filter(status=job_status)
        return qs


class TrainingJobDetailView(generics.RetrieveAPIView):
    """GET /api/analysis/training/<id>/

    Polled by the training page while a job runs. Shape is module-agnostic;
    per-module knobs live in `config`."""

    queryset = TrainingJob.objects.all()
    serializer_class = TrainingJobDetailSerializer
    lookup_field = 'pk'


def _cancel_job_row(job, detail_serializer) -> Response:
    """Shared cancel handler for InferenceRun and TrainingJob. Flips status
    to CANCELLED only when the job is still in-flight; refuses otherwise."""
    from apps.analysis.models import JobStatus

    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        return Response(
            {
                'error': (
                    f'Cannot cancel a job in status={job.status}. '
                    f'Cancellation only applies to pending or running jobs.'
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )
    job.status = JobStatus.CANCELLED
    job.error_message = 'Cancelled by user'
    if hasattr(job, 'completed_at'):
        job.completed_at = timezone.now()
    job.save(update_fields=['status', 'error_message', 'completed_at'])
    return Response(detail_serializer(job).data)


class InferenceRunCancelView(APIView):
    """POST /api/analysis/runs/<id>/cancel/

    Flips status → cancelled. The running worker's next progress tick
    re-reads the row, sees the cancelled status, and raises RunCancelled
    (which propagates cleanly through the ML pipeline). The worker then
    skips persisting Detection rows for this run."""

    def post(self, request: Request, pk: int) -> Response:
        try:
            run = InferenceRun.objects.get(pk=pk)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _cancel_job_row(run, InferenceRunDetailSerializer)


class TrainingJobCancelView(APIView):
    """POST /api/analysis/training/<id>/cancel/

    Same mechanism as InferenceRunCancelView. On the next progress tick
    the worker raises RunCancelled and skips persisting a new ModelVersion."""

    def post(self, request: Request, pk: int) -> Response:
        try:
            job = TrainingJob.objects.get(pk=pk)
        except TrainingJob.DoesNotExist:
            return Response(
                {'error': 'Training job not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _cancel_job_row(job, TrainingJobDetailSerializer)


class ModelVersionSetActiveView(APIView):
    """POST /api/analysis/models/<id>/set-active/

    Flips is_active=True on the given ModelVersion. The model's save()
    auto-demotes other active rows for the same (module, kind).
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            mv = ModelVersion.objects.get(pk=pk)
        except ModelVersion.DoesNotExist:
            return Response(
                {'error': 'Model version not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        mv.is_active = True
        mv.save()
        return Response(ModelVersionSerializer(mv).data)

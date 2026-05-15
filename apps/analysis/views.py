import logging
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
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

from .engulfment import apply_engulfment_exclusions
from .models import (
    Detection,
    InferenceRun,
    ModelArtifact,
    ModelArtifactKind,
    ModelVersion,
    TrainingJob,
)
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


# Map Ultralytics YOLO training-run filenames (basename only) to the
# corresponding ModelArtifactKind. Names that don't appear here are skipped
# unless they match one of the *_batch* prefixes used for sample tiles.
_ARTIFACT_NAME_MAP = {
    'BoxF1_curve.png': ModelArtifactKind.F1_CURVE,
    'BoxP_curve.png': ModelArtifactKind.PRECISION_CURVE,
    'BoxPR_curve.png': ModelArtifactKind.PR_CURVE,
    'BoxR_curve.png': ModelArtifactKind.RECALL_CURVE,
    'F1_curve.png': ModelArtifactKind.F1_CURVE,
    'P_curve.png': ModelArtifactKind.PRECISION_CURVE,
    'PR_curve.png': ModelArtifactKind.PR_CURVE,
    'R_curve.png': ModelArtifactKind.RECALL_CURVE,
    'confusion_matrix.png': ModelArtifactKind.CONFUSION_MATRIX,
    'confusion_matrix_normalized.png': ModelArtifactKind.CONFUSION_MATRIX,
    'labels.jpg': ModelArtifactKind.LABELS,
    'labels_correlogram.jpg': ModelArtifactKind.LABELS,
    'results.csv': ModelArtifactKind.RESULTS_CSV,
    'results.png': ModelArtifactKind.TRAINING_CURVE,
}
_SAMPLE_PREDICTION_PREFIXES = ('train_batch', 'val_batch')


def _classify_artifact(basename: str) -> tuple[str | None, str]:
    """Return (ModelArtifactKind value, caption) for a known artifact filename,
    or (None, '') if the name isn't a recognized run-folder asset.
    Caption disambiguates confusion-matrix variants and similar."""
    if basename in _ARTIFACT_NAME_MAP:
        caption = 'normalized' if basename == 'confusion_matrix_normalized.png' else ''
        return _ARTIFACT_NAME_MAP[basename], caption
    if any(basename.startswith(p) for p in _SAMPLE_PREDICTION_PREFIXES):
        return ModelArtifactKind.SAMPLE_PREDICTIONS, basename
    return None, ''


def _parse_args_yaml(file_obj: UploadedFile) -> dict:
    """Pull hyperparams out of Ultralytics args.yaml. Returns {} on any
    failure so a corrupt yaml doesn't fail the whole upload."""
    try:
        import yaml

        data = yaml.safe_load(file_obj.read())
    except Exception:
        logger.exception('Failed to parse args.yaml from upload')
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    for key in (
        'epochs',
        'imgsz',
        'batch',
        'lr0',
        'optimizer',
        'model',
        'data',
        'patience',
    ):
        if key in data:
            out[f'yolo_{key}'] = data[key]
    return out


def _parse_results_csv(file_obj: UploadedFile) -> dict:
    """Extract the final-epoch validation metrics from an Ultralytics
    results.csv. Returns the canonical metric names used by the UI:
    precision, recall, mAP50, mAP50-95. Empty on any failure."""
    try:
        import csv
        import io

        raw = file_obj.read()
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='replace')
        reader = csv.DictReader(io.StringIO(raw))
        rows = [row for row in reader if any(v.strip() for v in row.values())]
    except Exception:
        logger.exception('Failed to parse results.csv from upload')
        return {}
    if not rows:
        return {}
    final = rows[-1]
    # Ultralytics column names are like 'metrics/precision(B)' for detector
    # runs and 'metrics/precision(M)' for segmentation. Strip the suffix.
    out: dict = {}
    aliases = {
        'precision': ('metrics/precision(B)', 'metrics/precision'),
        'recall': ('metrics/recall(B)', 'metrics/recall'),
        'mAP50': ('metrics/mAP50(B)', 'metrics/mAP50'),
        'mAP50-95': ('metrics/mAP50-95(B)', 'metrics/mAP50-95'),
    }
    for nice, candidates in aliases.items():
        for col in candidates:
            if col in final and final[col].strip():
                try:
                    out[nice] = float(final[col])
                except ValueError:
                    pass
                break
    return out


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
    # Ultralytics writes epoch=-1 as a "training completed" sentinel on the
    # final checkpoint (vs. a real number on a paused/resumable run). Hide
    # it — yolo_epochs from args.yaml already tells the user the run length.
    if out.get('epoch') == -1:
        out.pop('epoch', None)

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

    # Flip back to True to restore staff-only model upload (frontend has the
    # mirror flag REQUIRE_STAFF_FOR_UPLOAD in PollinatorsModels.vue).
    REQUIRE_STAFF_FOR_UPLOAD = False

    def get_permissions(self):
        if self.request.method == 'POST' and self.REQUIRE_STAFF_FOR_UPLOAD:
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
        weights_upload = request.FILES.get('weights_file')
        # Folder mode: 'artifacts' is the list of uploaded files; 'artifact_paths'
        # is a JSON array of their webkitRelativePaths in matching order. We need
        # the parallel array because browsers strip '/' from multipart
        # filenames as a path-traversal guard, so the relative path can't ride
        # along on the file's own name.
        artifact_uploads = request.FILES.getlist('artifacts')
        artifact_paths: list[str] = []
        if artifact_uploads:
            import json as _json

            raw_paths = request.data.get('artifact_paths') or '[]'
            try:
                parsed = _json.loads(raw_paths)
                if not isinstance(parsed, list) or not all(
                    isinstance(p, str) for p in parsed
                ):
                    raise ValueError
                artifact_paths = parsed
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'artifact_paths must be a JSON array of strings'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if len(artifact_paths) != len(artifact_uploads):
                return Response(
                    {
                        'detail': (
                            f'artifact_paths length ({len(artifact_paths)}) does not '
                            f'match artifacts length ({len(artifact_uploads)})'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Reject path traversal: relative paths only, no absolute or '..' segments.
            for p in artifact_paths:
                if not p or p.startswith('/') or '..' in p.split('/'):
                    return Response(
                        {'detail': f'illegal artifact path: {p!r}'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if not module or not version_name:
            return Response(
                {'detail': 'module and version_name are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not weights_upload and not artifact_uploads:
            return Response(
                {'detail': 'weights_file or artifacts is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ModelVersion.objects.filter(version_name=version_name).exists():
            return Response(
                {'detail': f'version_name "{version_name}" already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve weights source. Single-file mode wins if both forms are
        # present; folder mode looks for weights/best.pt then weights/last.pt
        # anywhere in the tree (Ultralytics outputs nest these one level
        # deep under the run name).
        # Pair each artifact upload with its relative path so downstream code
        # can route by parent directory regardless of how the browser mangled
        # the multipart filename.
        artifact_entries: list[tuple[UploadedFile, str]] = list(
            zip(artifact_uploads, artifact_paths, strict=True)
        )

        chosen_weights = weights_upload
        chosen_weights_name: str | None = (
            weights_upload.name if weights_upload else None
        )
        if chosen_weights is None:
            best, last = None, None
            for f, rel in artifact_entries:
                tail = rel.rsplit('/', 1)[-1] if '/' in rel else rel
                parent = rel.rsplit('/', 2)[-2] if rel.count('/') >= 1 else ''
                if parent == 'weights' and tail == 'best.pt':
                    best = f
                elif parent == 'weights' and tail == 'last.pt':
                    last = f
            chosen_weights = best or last
            if chosen_weights is None:
                return Response(
                    {
                        'detail': (
                            'No weights file found in the uploaded folder. '
                            'Expected weights/best.pt or weights/last.pt.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            chosen_weights_name = chosen_weights.name

        dest_dir = Path(settings.MEDIA_ROOT) / 'models' / module
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(chosen_weights_name or '').suffix or '.bin'
        dest = dest_dir / f'{version_name}{ext}'
        with dest.open('wb') as out:
            for chunk in chosen_weights.chunks():
                out.write(chunk)

        parameters = _extract_checkpoint_metadata(dest)

        # args.yaml augments parameters with the training hyperparams used by
        # the Ultralytics trainer — useful when the checkpoint itself doesn't
        # carry them (older runs, manual exports).
        metrics: dict = {}
        for f, rel in artifact_entries:
            tail = rel.rsplit('/', 1)[-1] if '/' in rel else rel
            if tail == 'args.yaml':
                parameters.update(_parse_args_yaml(f))
                try:
                    f.seek(0)
                except Exception:
                    pass
            elif tail == 'results.csv':
                metrics.update(_parse_results_csv(f))
                try:
                    f.seek(0)
                except Exception:
                    pass

        mv = ModelVersion.objects.create(
            module=module,
            kind=kind,
            version_name=version_name,
            model_file_path=str(dest),
            description=description,
            parameters=parameters,
            metrics=metrics,
            created_by=request.user if request.user.is_authenticated else None,
        )

        ingested, skipped = 0, 0
        for f, rel in artifact_entries:
            if f is chosen_weights:
                continue
            tail = rel.rsplit('/', 1)[-1] if '/' in rel else rel
            if not tail or tail == 'args.yaml':
                continue
            kind_value, caption = _classify_artifact(tail)
            if kind_value is None:
                skipped += 1
                continue
            artifact = ModelArtifact(model_version=mv, kind=kind_value, caption=caption)
            # Store under the basename only so MEDIA_ROOT/model_artifacts/<module>/<version>/
            # stays flat regardless of how the client structured the folder.
            artifact.file.save(tail, f, save=True)
            ingested += 1

        logger.info(
            f'ModelVersion {mv.pk} created by {request.user}: '
            f'{module}/{version_name} ({dest.stat().st_size} bytes, '
            f'{ingested} artifact(s), {skipped} skipped)'
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
                logger.exception(
                    f'Failed to remove {run_dir}; continuing with DB delete'
                )
        super().perform_destroy(instance)


class DetectionExclusionView(APIView):
    """POST /api/analysis/detections/<pk>/exclude/

    Body: {"excluded": true|false}. Toggles excluded_from_export, which
    the CSV export reads to drop duplicates / unwanted detections without
    touching reviewer_status. Kept separate from the review PATCH so a
    bbox click in the Export step can't accidentally rewrite the label.
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            d = Detection.objects.get(pk=pk)
        except Detection.DoesNotExist:
            return Response(
                {'error': 'Detection not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        excluded = request.data.get('excluded')
        if not isinstance(excluded, bool):
            return Response(
                {'error': 'excluded must be a boolean'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        d.excluded_from_export = excluded
        d.save(update_fields=['excluded_from_export'])
        return Response({'id': d.pk, 'excluded_from_export': excluded})


class InferenceRunRecomputeExclusionsView(APIView):
    """POST /api/analysis/runs/<id>/recompute-exclusions/

    Re-runs engulfment auto-exclude over the run's detections. Safe to call
    on completed runs; add-only (a manually-cleared exclusion stays cleared
    only until this is invoked, then any qualifying engulfing bbox is
    re-marked). Returns the number of rows newly excluded.
    """

    def post(self, request: Request, pk: int) -> Response:
        if not InferenceRun.objects.filter(pk=pk).exists():
            return Response(
                {'error': 'Run not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        excluded = apply_engulfment_exclusions(pk)
        return Response({'excluded': excluded})


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

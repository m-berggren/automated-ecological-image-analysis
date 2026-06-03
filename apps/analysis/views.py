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

from apps.datasets.models import ImageAsset, UploadStatus, Module
from apps.pollinator.services import spawn_inference_pipeline
from apps.seeds.services import spawn_seeds_pipeline

from .engulfment import apply_engulfment_exclusions
from .artifacts import (
    classify_artifact,
    metrics_from_results_csv,
    metrics_from_results_json,
    params_from_args_yaml,
)
from .storage import model_dir, move_weights_into_place
from .models import (
    Detection,
    InferenceRun,
    JobStatus,
    ModelArtifact,
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
    ModelVersionUpdateSerializer,
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


def _parse_args_yaml(file_obj: UploadedFile) -> dict:
    """Pull hyperparams out of an uploaded Ultralytics args.yaml. Thin adapter
    over the shared parser in apps.analysis.artifacts so uploaded and
    incrementally-trained models expose identical yolo_ fields."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='replace')
    return params_from_args_yaml(raw)


def _parse_results_csv(file_obj: UploadedFile) -> dict:
    """Extract final-epoch validation metrics from an uploaded Ultralytics
    results.csv (precision, recall, mAP50, mAP50-95). Thin adapter over the
    shared parser in apps.analysis.artifacts."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='replace')
    return metrics_from_results_csv(raw)


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
    On success the file is written to
    MEDIA_ROOT/models/<module>/<model_version_id>/weights<ext>, .pth metadata
    is introspected into parameters, and the new ModelVersion is returned.
    Sibling artifacts land under .../<model_version_id>/artifacts/.
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
        # Optional dialog-driven parameters (e.g. seeds passes `species` so
        # hand-uploaded models group correctly on SeedsModels.vue). Merged
        # into `parameters` below after checkpoint introspection, so a
        # user-supplied value wins over auto-extracted metadata for the
        # same key.
        parameters_extra: dict = {}
        raw_extra = request.data.get('parameters_extra')
        if raw_extra:
            import json as _json

            try:
                parsed_extra = _json.loads(raw_extra)
                if not isinstance(parsed_extra, dict):
                    raise ValueError
                parameters_extra = {
                    str(k): v for k, v in parsed_extra.items() if v not in (None, '')
                }
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'parameters_extra must be a JSON object'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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
        # Scope the uniqueness check by the module's grouping axis so a
        # seeds "v1" doesn't collide with a pollinators "v1" (and a CAT
        # "v1" doesn't collide with a PHYCA "v1"). Seeds groups by
        # parameters.species; pollinators groups by kind. Other modules
        # fall back to per-module uniqueness.
        name_collision = ModelVersion.objects.filter(
            module=module, version_name=version_name,
        )
        if module == 'seeds':
            species_extra = (parameters_extra.get('species') or '').strip().lower()
            if species_extra:
                name_collision = name_collision.filter(
                    parameters__species__iexact=species_extra,
                )
        elif module == 'pollinators' and kind:
            name_collision = name_collision.filter(kind=kind)
        if name_collision.exists():
            return Response(
                {'detail': f'version_name "{version_name}" already exists for this type'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve weights source. Single-file mode wins if both forms are
        # present; folder mode ranks candidate weight files: best > last, a
        # weights/ subfolder preferred but not required (classifier runs save
        # best.pth at the run root), accepting both .pt and .pth.
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
            chosen_rank = 99
            for f, rel in artifact_entries:
                tail = rel.rsplit('/', 1)[-1] if '/' in rel else rel
                # Suffix match so classifier checkpoint names
                # (efficientnet_binary_best.pth, group_insectnet_best.pth) and
                # Ultralytics weights/best.pt all qualify.
                low = tail.lower()
                is_best = low.endswith('best.pt') or low.endswith('best.pth')
                is_last = low.endswith('last.pt') or low.endswith('last.pth')
                if not (is_best or is_last):
                    continue
                parent = rel.rsplit('/', 2)[-2] if rel.count('/') >= 1 else ''
                rank = (0 if parent == 'weights' else 2) + (0 if is_best else 1)
                if rank < chosen_rank:
                    chosen_rank = rank
                    chosen_weights = f
                    chosen_weights_name = tail
            if chosen_weights is None:
                return Response(
                    {
                        'detail': (
                            'No weights file found in the uploaded folder. '
                            'Expected best.pt/.pth or last.pt/.pth (ideally under weights/).'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Buffer the weights to a temp file so we can introspect the checkpoint
        # before the ModelVersion row exists. The canonical destination needs
        # the row's id; we move into place once the row is created.
        # Keep the temp file inside MEDIA_ROOT so the later shutil.move into
        # the canonical models/<module>/<id>/ location is a same-filesystem
        # rename — cross-device temp dirs would force a full copy. Ensure
        # MEDIA_ROOT exists first, since fresh deployments have no media/.
        import tempfile

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        ext = Path(chosen_weights_name or '').suffix or '.bin'
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=ext, dir=str(media_root)
        ) as tmp:
            for chunk in chosen_weights.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        try:
            parameters = _extract_checkpoint_metadata(tmp_path)

            # args.yaml augments parameters with the training hyperparams used
            # by the Ultralytics trainer — useful when the checkpoint itself
            # doesn't carry them (older runs, manual exports).
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
                elif tail.endswith('results.json'):
                    raw = f.read()
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8', errors='replace')
                    metrics.update(metrics_from_results_json(raw))
                    try:
                        f.seek(0)
                    except Exception:
                        pass

            # User-supplied extras overwrite auto-extracted keys (e.g. if
            # seeds passes species='phyca' it wins over anything in the
            # checkpoint).
            if parameters_extra:
                parameters.update(parameters_extra)

            mv = ModelVersion.objects.create(
                module=module,
                kind=kind,
                version_name=version_name,
                model_file_path='',
                description=description,
                parameters=parameters,
                metrics=metrics,
                created_by=request.user
                if request.user.is_authenticated
                else None,
            )

            try:
                dest = move_weights_into_place(tmp_path, module, mv.id, ext)
            except Exception:
                # Roll back the half-created row so we don't leak a
                # ModelVersion with no weights on disk.
                mv.delete()
                raise
            mv.model_file_path = str(dest)
            mv.save(update_fields=['model_file_path'])
        finally:
            # tmp_path is gone after a successful move; clean it up if we
            # bailed before the move succeeded.
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    logger.exception(
                        f'Failed to clean temp upload at {tmp_path}'
                    )

        ingested, skipped = 0, 0
        for f, rel in artifact_entries:
            if f is chosen_weights:
                continue
            tail = rel.rsplit('/', 1)[-1] if '/' in rel else rel
            if not tail or tail == 'args.yaml':
                continue
            kind_value, caption = classify_artifact(tail)
            if kind_value is None:
                skipped += 1
                continue
            artifact = ModelArtifact(model_version=mv, kind=kind_value, caption=caption)
            # Store under the basename only so the canonical
            # models/<module>/<id>/artifacts/ folder stays flat regardless of
            # how the client structured the upload.
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


class InferenceRunDraftView(APIView):
    """POST /api/analysis/runs/draft/

    Body: {module, name?, config}. Atomically creates a paired
    InferenceRun (status=pending) and Upload (status=draft) so the frontend
    can transmit images directly into ``media/runs/<module>/<run_id>/images/``
    via the existing /api/datasets/images/ endpoint.

    Returns {run_id, upload_id} so the upload page knows where to attach
    each file.
    """

    def post(self, request: Request) -> Response:
        from apps.datasets.models import Module, Upload, UploadStatus

        module = (request.data.get('module') or '').strip()
        if module not in Module.values:
            return Response(
                {'detail': f'module must be one of {Module.values}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = (request.data.get('name') or '').strip()
        config = request.data.get('config') or {}
        if not isinstance(config, dict):
            return Response(
                {'detail': 'config must be an object'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            upload = Upload.objects.create(
                name=name,
                module=module,
                status=UploadStatus.DRAFT,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            run = InferenceRun.objects.create(
                module=module,
                name=name,
                upload=upload,
                config=config,
                initiated_by=request.user if request.user.is_authenticated else None,
            )
        return Response(
            {
                'run_id': run.pk,
                'upload_id': upload.pk,
                'run': InferenceRunDetailSerializer(run).data,
            },
            status=status.HTTP_201_CREATED,
        )


def _busy_run_for_module(
    module: str, exclude_pk: int | None = None
) -> InferenceRun | None:
    """Return the currently-running inference run for a module, if any.

    PAUSED and PENDING don't count: a paused run isn't consuming the GPU,
    and pending means the worker hasn't claimed it yet. Only RUNNING is
    a hard mutual-exclusion signal.
    """
    qs = InferenceRun.objects.filter(module=module, status=JobStatus.RUNNING)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


class InferenceRunActiveView(APIView):
    """GET /api/analysis/runs/active/?module=<module>

    Returns the run currently RUNNING in the given module, or ``null``.
    Used by the Detect page to surface a banner and disable Start/Resume
    while another run is in flight, since only one run per module may
    occupy the GPU at a time.
    """

    def get(self, request: Request) -> Response:
        module = request.query_params.get('module', '').strip()
        if not module:
            return Response(
                {'error': 'module query param required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        active = _busy_run_for_module(module)
        if active is None:
            return Response({'active': None})
        return Response({'active': InferenceRunDetailSerializer(active).data})


class InferenceRunStartView(APIView):
    """POST /api/analysis/runs/<id>/start/

    Body: {start_at_image?, config?}. Spawns the worker for a draft run.
    Both fields are merged into the run's frozen config. Refuses to start
    a run that isn't ``pending``, that has no images attached, or when
    another run is already RUNNING in the same module (one GPU, one
    pipeline at a time).
    """

    def post(self, request: Request, pk: int) -> Response:
        from apps.datasets.models import UploadStatus

        try:
            run = InferenceRun.objects.select_related('upload').get(pk=pk)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'}, status=status.HTTP_404_NOT_FOUND
            )
        if run.status != JobStatus.PENDING:
            return Response(
                {
                    'error': (
                        f'Cannot start a run in status={run.status}; only '
                        f'pending runs can be started.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        busy = _busy_run_for_module(run.module, exclude_pk=run.pk)
        if busy is not None:
            return Response(
                {
                    'error': (
                        f'Another {run.module} run is already running '
                        f'(#{busy.pk} "{busy.name or ""}"). Pause or wait for it '
                        f'to finish before starting this one.'
                    ),
                    'blocking_run_id': busy.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )
        if run.upload is None or not run.upload.images.exists():
            return Response(
                {'error': 'Run has no uploaded images.'},
                status=status.HTTP_409_CONFLICT,
            )

        merged_config = dict(run.config or {})
        body_config = request.data.get('config')
        if isinstance(body_config, dict):
            merged_config.update(body_config)
        if 'start_at_image' in request.data:
            try:
                merged_config['start_at_image'] = max(
                    1, int(request.data['start_at_image'])
                )
            except (TypeError, ValueError):
                return Response(
                    {'error': 'start_at_image must be an integer >= 1'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        run.config = merged_config
        run.image_count = run.upload.images.count()
        run.save(update_fields=['config', 'image_count'])

        if run.upload.status == UploadStatus.DRAFT:
            run.upload.status = UploadStatus.READY
            run.upload.save(update_fields=['status'])

        if run.module == Module.SEEDS:
            from apps.seeds.services import spawn_seeds_pipeline
            transaction.on_commit(lambda: spawn_seeds_pipeline(run))
        else:
            from apps.pollinator.services import spawn_inference_pipeline
            transaction.on_commit(lambda: spawn_inference_pipeline(run))

        return Response(InferenceRunDetailSerializer(run).data)


class InferenceRunPauseView(APIView):
    """POST /api/analysis/runs/<id>/pause/

    Flips status to PAUSED. The running worker's next between-image check
    sees this and raises RunPaused, exiting cleanly. processed_image_count
    is left intact so a subsequent resume picks up right after the last
    persisted image.
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            run = InferenceRun.objects.get(pk=pk)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'}, status=status.HTTP_404_NOT_FOUND
            )
        if run.status != JobStatus.RUNNING:
            return Response(
                {
                    'error': (
                        f'Only running jobs can be paused; this one is {run.status}.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        run.status = JobStatus.PAUSED
        run.save(update_fields=['status'])
        return Response(InferenceRunDetailSerializer(run).data)


class InferenceRunResumeView(APIView):
    """POST /api/analysis/runs/<id>/resume/

    Re-spawns the worker for a paused run. The pipeline reads
    ``processed_image_count`` and resumes at the next image. Optional
    ``start_at_image`` in the body bumps the floor higher (useful if the
    operator wants to skip ahead past the original pause point).
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            run = InferenceRun.objects.get(pk=pk)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'}, status=status.HTTP_404_NOT_FOUND
            )
        if run.status != JobStatus.PAUSED:
            return Response(
                {
                    'error': (
                        f'Only paused jobs can be resumed; this one is {run.status}.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        busy = _busy_run_for_module(run.module, exclude_pk=run.pk)
        if busy is not None:
            return Response(
                {
                    'error': (
                        f'Another {run.module} run is already running '
                        f'(#{busy.pk} "{busy.name or ""}"). Pause or wait for it '
                        f'to finish before resuming this one.'
                    ),
                    'blocking_run_id': busy.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )
        if 'start_at_image' in request.data:
            try:
                merged = dict(run.config or {})
                merged['start_at_image'] = max(1, int(request.data['start_at_image']))
                run.config = merged
            except (TypeError, ValueError):
                return Response(
                    {'error': 'start_at_image must be an integer >= 1'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        run.status = JobStatus.PENDING
        run.save(update_fields=['status', 'config'])
        if run.module == Module.SEEDS:
            from apps.seeds.services import spawn_seeds_pipeline
            transaction.on_commit(lambda: spawn_seeds_pipeline(run))
        else:
            from apps.pollinator.services import spawn_inference_pipeline
            transaction.on_commit(lambda: spawn_inference_pipeline(run))
        return Response(InferenceRunDetailSerializer(run).data)


class InferenceRunAbortView(APIView):
    """POST /api/analysis/runs/<id>/abort/

    Tear down a draft run that the user walked away from before clicking
    Start. Deletes the run, the paired Upload (cascading the uploaded
    ImageAssets), and any on-disk files written under
    ``media/runs/<module>/<run_id>/``.

    Only valid on a run that hasn't begun: status == pending and
    started_at is null. Refuses anything else so an in-flight worker
    can't be rug-pulled. CSRF-exempt by being a token-authed POST; safe
    to send via ``navigator.sendBeacon`` from a beforeunload handler.
    """

    def post(self, request: Request, pk: int) -> Response:
        from apps.datasets.models import Upload

        try:
            run = InferenceRun.objects.select_related('upload').get(pk=pk)
        except InferenceRun.DoesNotExist:
            # Already gone — treat as success so a duplicate beacon doesn't
            # surface as an error in the UI.
            return Response(status=status.HTTP_204_NO_CONTENT)

        if run.status != JobStatus.PENDING or run.started_at is not None:
            return Response(
                {
                    'error': (
                        f'Cannot abort: run is {run.status} (started_at='
                        f'{run.started_at}). Use cancel/pause for in-flight runs.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        upload: Upload | None = run.upload
        run_dir = Path(settings.MEDIA_ROOT) / 'runs' / run.module / str(run.pk)

        # PROTECT on InferenceRun.upload means we delete the run first, then
        # the upload (which cascades ImageAsset + their files via the
        # FileField storage backend).
        run.delete()
        if upload is not None:
            for img in upload.images.all():
                if img.file:
                    try:
                        img.file.delete(save=False)
                    except Exception:
                        logger.exception(
                            f'Failed to remove image file for ImageAsset {img.pk}'
                        )
            upload.delete()

        if run_dir.exists():
            import shutil

            try:
                shutil.rmtree(run_dir)
            except OSError:
                logger.exception(f'Failed to remove {run_dir}; continuing')

        return Response(status=status.HTTP_204_NO_CONTENT)


class InferenceRunListCreateView(generics.ListCreateAPIView):
    """GET  /api/analysis/runs/?module=<module>  list runs (newest first).
    POST /api/analysis/runs/                   create a new run (status=pending).

    The legacy POST creates a run bound to an existing Upload (used by
    'Re-run with same config'). New uploads should use /draft/ instead so
    the Upload + Run are paired 1:1 and images land under
    media/runs/<module>/<run_id>/images/.
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
        if run.module == Module.SEEDS:
            from apps.seeds.services import spawn_seeds_pipeline
            transaction.on_commit(lambda: spawn_seeds_pipeline(run))
        else:
            from apps.pollinator.services import spawn_inference_pipeline
            transaction.on_commit(lambda: spawn_inference_pipeline(run))
        return Response(
            InferenceRunDetailSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class InferenceRunDetailView(generics.RetrieveDestroyAPIView):
    """GET    /api/analysis/runs/<id>/  read the run (polled while running).
    DELETE /api/analysis/runs/<id>/  remove the run and everything tied to it.

    DB cascade handles Detection and PollinatorDetection (via FK on_delete).
    The on-disk run dir (MEDIA_ROOT/runs/<module>/<id>/, holding the
    source images and per-detection crops) is removed explicitly because
    Django's storage backend never auto-deletes ImageField files.

    Refuses to delete an in-flight run (pending/running/paused) to keep the
    worker from racing the delete; cancel it first.
    """

    queryset = InferenceRun.objects.all()
    serializer_class = InferenceRunDetailSerializer
    lookup_field = 'pk'

    def perform_destroy(self, instance: InferenceRun) -> None:
        if instance.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED):
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
        run_dir = (
            Path(settings.MEDIA_ROOT) / 'runs' / instance.module / str(instance.pk)
        )
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
        d.export_exclusion_user_set = True
        d.save(update_fields=['excluded_from_export', 'export_exclusion_user_set'])
        return Response({'id': d.pk, 'excluded_from_export': excluded})


class ImageIncludeTrainingView(APIView):
    """POST /api/analysis/images/<pk>/include-training/

    Body: {"included": true|false}. Toggles ImageAsset.include_in_training,
    the reviewer flag opting an image into YOLO detector training. The
    training-set builder includes only images where this is True.
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            img = ImageAsset.objects.get(pk=pk)
        except ImageAsset.DoesNotExist:
            return Response(
                {'error': 'Image not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        included = request.data.get('included')
        if not isinstance(included, bool):
            return Response(
                {'error': 'included must be a boolean'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        img.include_in_training = included
        img.save(update_fields=['include_in_training'])
        return Response({'id': img.pk, 'include_in_training': included})


class DetectionExcludeTrainingView(APIView):
    """POST /api/analysis/detections/<pk>/exclude-training/

    Body: {"excluded": true|false}. Toggles Detection.exclude_from_training,
    the reviewer flag marking a crop as unfit for binary/group classifier
    training. Set by un-ticking the crop in the training pool drawer; the
    classifier pool builders skip crops where this is True. Distinct from
    excluded_from_export (CSV only) and ImageAsset.include_in_training
    (image-level, detector training).
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
        d.exclude_from_training = excluded
        d.save(update_fields=['exclude_from_training'])
        return Response({'id': d.pk, 'exclude_from_training': excluded})


class InferenceRunReviewSettingsView(APIView):
    """POST /api/analysis/runs/<id>/review-settings/

    Merges a partial dict into the run's review_settings JSON. Accepts any
    subset of: auto_select (bool), yolo_threshold (0..1), group_threshold
    (0..1), dedup_iou_threshold (0..1). These are per-run reviewer/export
    preferences; when a key is absent the frontend resolves the default from
    the run's config confidence values, so review sliders start where the run
    was processed.
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            run = InferenceRun.objects.get(pk=pk)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = request.data
        merged = dict(run.review_settings or {})
        if 'auto_select' in data:
            v = data['auto_select']
            if not isinstance(v, bool):
                return Response(
                    {'error': 'auto_select must be a boolean'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            merged['auto_select'] = v
        for key in ('yolo_threshold', 'group_threshold', 'dedup_iou_threshold'):
            if key in data:
                v = data[key]
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    return Response(
                        {'error': f'{key} must be a number'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                merged[key] = max(0.0, min(1.0, float(v)))
        run.review_settings = merged
        run.save(update_fields=['review_settings'])
        return Response({'id': run.pk, 'review_settings': run.review_settings})


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
            # Manual review overrides any prior auto-accept (Export colour cue).
            'auto_accepted': False,
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
    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED):
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


class ModelVersionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET    /api/analysis/models/<pk>/   read one model version.
    PATCH  /api/analysis/models/<pk>/   rename (version_name / description).
    DELETE /api/analysis/models/<pk>/   remove the version + its weights.

    Refuses to delete a model that any InferenceRun depends on (FK is
    PROTECTed) or that is referenced from a pollinator run's config JSON
    (no FK, but the run still expects those weights to exist). Removes
    the on-disk weights file and cascades ModelArtifact rows + their
    files via Django's storage backend.
    """

    queryset = ModelVersion.objects.all()
    serializer_class = ModelVersionSerializer
    lookup_field = 'pk'

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return ModelVersionUpdateSerializer
        return ModelVersionSerializer

    # Mirrors the upload gate in ModelVersionListCreateView. Set both to
    # True to restore staff-only model management.
    REQUIRE_STAFF_FOR_DELETE = False

    def get_permissions(self):
        if self.request.method == 'DELETE' and self.REQUIRE_STAFF_FOR_DELETE:
            return [IsAdminUser()]
        return super().get_permissions()

    def perform_destroy(self, instance: ModelVersion) -> None:
        from apps.datasets.models import Module

        # Direct FK reference (seeds runs use this).
        protected_runs = list(
            InferenceRun.objects.filter(model_version=instance).values_list(
                'pk',
                flat=True,
            )[:5]
        )
        # Pollinator runs stash model ids inside config JSON instead.
        pollinator_run_ids = []
        if instance.module == Module.POLLINATORS:
            kind_to_key = {
                'detector': 'yolo',
                'binary_classifier': 'binary_classifier',
                'group_classifier': 'group_classifier',
            }
            key = kind_to_key.get(instance.kind)
            if key is not None:
                for run_id, config in InferenceRun.objects.filter(
                    module=Module.POLLINATORS,
                ).values_list('pk', 'config'):
                    if not isinstance(config, dict):
                        continue
                    section = config.get(key)
                    if (
                        isinstance(section, dict)
                        and section.get('model_version_id') == instance.pk
                    ):
                        pollinator_run_ids.append(run_id)
                        if len(pollinator_run_ids) >= 5:
                            break
        blocking = sorted(set(protected_runs) | set(pollinator_run_ids))
        if blocking:
            raise serializers.ValidationError(
                {
                    'error': (
                        f'Model is used by {len(blocking)} run(s) '
                        f'(e.g. {blocking[:5]}). Delete those runs first.'
                    ),
                },
            )

        weights_file = (
            Path(instance.model_file_path) if instance.model_file_path else None
        )
        # Canonical per-model dir under MEDIA_ROOT/models/<module>/<id>/.
        # Captured before destroy so it survives the cascade.
        per_model_dir = model_dir(instance.module, instance.id)

        # Delete artifact files explicitly; FK cascade removes the rows but
        # not the underlying storage objects.
        for artifact in instance.artifacts.all():
            if artifact.file:
                try:
                    artifact.file.delete(save=False)
                except Exception:
                    logger.exception(
                        f'Failed to delete artifact file for ModelArtifact '
                        f'{artifact.pk}; continuing with DB delete'
                    )

        super().perform_destroy(instance)

        if weights_file and weights_file.exists():
            try:
                weights_file.unlink()
            except OSError:
                logger.exception(f'Failed to remove weights file at {weights_file}')

        # The canonical layout puts weights + artifacts under per_model_dir.
        # Once both are gone, the dir (and its now-empty artifacts/ child)
        # are orphans — remove them. rmdir-style walk only succeeds when the
        # tree is empty, so legacy rows with files elsewhere are left alone.
        if per_model_dir.exists():
            artifacts_dir = per_model_dir / 'artifacts'
            for d in (artifacts_dir, per_model_dir):
                try:
                    d.rmdir()
                except OSError:
                    pass


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

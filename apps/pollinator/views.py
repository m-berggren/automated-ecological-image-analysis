import csv
import io
import logging
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.http import FileResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.analysis.models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    ModelVersion,
    TrainingJob,
)
from apps.analysis.serializers import (
    DetectionReviewSerializer,
    TrainingJobDetailSerializer,
)
from apps.datasets.models import Module

from .exif import camera_id, shutter_speed_label
from .serializers import (
    PollinatorDetectionSerializer,
    PollinatorTrainingCreateSerializer,
)
from .training import (
    PER_TRACK_DEFAULTS,
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
    'camera_id',
    'datetime',
    'shutter_speed',
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


class _Echo:
    """File-like that returns whatever is written. Used by csv.writer to
    produce one CSV row per StreamingHttpResponse chunk."""

    def write(self, value: str) -> str:
        return value


def _build_image_row(image, counts: dict[str, int], session: str) -> dict:
    return {
        'session': session,
        'image_name': Path(image.file.name).name if image.file else '',
        'camera_id': camera_id(image.exif or {}),
        'datetime': image.captured_at.isoformat() if image.captured_at else '',
        'shutter_speed': shutter_speed_label(image.exif or {}),
        'fly_count': counts.get('fly', 0),
        'bumblebee_count': counts.get('bumblebee', 0),
        'butterfly_moth_count': counts.get('butterfly_moth', 0),
        'other_count': counts.get('other', 0),
        'total_count': sum(counts.get(b, 0) for b in _COUNT_BUCKETS),
    }


def _run_filename_base(run) -> str:
    """Filesystem-safe base name for a run's exports, from the run name.
    Falls back to run-<pk> if the name is empty or all punctuation."""
    base = re.sub(r'[^\w.-]+', '_', run.name or '').strip('_')
    return base or f'run-{run.pk}'


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

        mode = request.query_params.get('mode') or 'per_image'

        if mode == 'per_detection':
            return self._export_per_detection(run)

        return self._export_per_image(run)

    def _export_per_image(self, run):
        # Pre-aggregate validated detections by image_id so we can emit one
        # streamed row per image without a per-image DB hit.
        counts_by_image: dict[int, dict[str, int]] = {}
        validated = Detection.objects.filter(
            inference_run=run,
            status=DetectionStatus.ACCEPTED,
            excluded_from_export=False,
        ).values_list('image_id', 'predicted_class', 'reviewer_label')
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
                    img,
                    counts_by_image.get(img.id, {}),
                    session,
                )
                yield writer.writerow([row[k] for k in _CSV_FIELDS])

        filename = f'{_run_filename_base(run)}_images.csv'
        response = StreamingHttpResponse(rows(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _export_per_detection(self, run):
        detections = (
            Detection.objects.filter(
                inference_run=run,
                status=DetectionStatus.ACCEPTED,
                excluded_from_export=False,
            )
            .select_related('image', 'pollinator_detection')
            .order_by('image__captured_at', 'image_id', 'id')
            .iterator(chunk_size=500)
        )

        fields = [
            # Image Specific
            'session',
            'image_name',
            'camera_id',
            'datetime',
            'shutter_speed',
            # Detection specific
            'detection_id',
            'yolo_confidence',
            'group_classifier_confidence',
            'yolo_class',
            'group_classifier_class',
            'final_class',
        ]

        session = run.name or f'Run #{run.pk}'
        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(fields)

            for d in detections:
                pd = getattr(d, 'pollinator_detection', None)
                img = d.image

                final_class = (
                    d.reviewer_label
                    or d.predicted_class
                    or (pd.yolo_class if pd else None)
                    or (pd.insectnet_class if pd else None)
                )

                yield writer.writerow(
                    [
                        # image
                        session,
                        Path(img.file.name).name if img and img.file else '',
                        camera_id(img.exif or {}) if img else '',
                        img.captured_at.isoformat() if img and img.captured_at else '',
                        shutter_speed_label(img.exif or {}) if img else '',
                        # detection
                        d.id,
                        pd.yolo_confidence if pd else None,
                        pd.insectnet_confidence if pd else None,
                        pd.yolo_class if pd else None,
                        pd.insectnet_class if pd else None,
                        final_class,
                    ]
                )

        filename = f'{_run_filename_base(run)}_detections.csv'
        response = StreamingHttpResponse(rows(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# Class set used for folder routing in the per-class crop ZIP. Membership
# check only; the bbox overlay color is always red so the export matches
# the review page's red outline.
_CLASS_SET = {'fly', 'bumblebee', 'butterfly', 'other'}
_BBOX_RED = (239, 68, 68)
_ROI_COLOR = (59, 130, 246)


def _draw_dashed_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    width: int,
    dash: int,
    gap: int,
) -> None:
    x1, y1, x2, y2 = box
    step = max(1, dash + gap)

    def segs(start: int, end: int):
        p = start
        while p < end:
            yield p, min(p + dash, end)
            p += step

    for a, b in segs(x1, x2):
        draw.line([(a, y1), (b, y1)], fill=color, width=width)
        draw.line([(a, y2), (b, y2)], fill=color, width=width)
    for a, b in segs(y1, y2):
        draw.line([(x1, a), (x1, b)], fill=color, width=width)
        draw.line([(x2, a), (x2, b)], fill=color, width=width)


def _effective_class(d: Detection) -> str:
    return (d.reviewer_label or d.predicted_class or '').lower()


def _normalize_roi_bbox(roi: object) -> tuple[float, float, float, float] | None:
    """Coerce either ROI shape to an (x, y, w, h) tuple, or None.

    New runs store [x, y, w, h]; runs created before that store the drawer's
    raw {x, y, width, height} object. Mirrors the frontend's normalizeRoiBbox
    so old runs still get their ROI burned into exports.
    """
    if isinstance(roi, (list, tuple)) and len(roi) == 4:
        return tuple(roi)  # type: ignore[return-value]
    if isinstance(roi, dict):
        keys = ('x', 'y', 'width', 'height')
        if all(isinstance(roi.get(k), (int, float)) for k in keys):
            return tuple(roi[k] for k in keys)  # type: ignore[return-value]
    return None


def _safe_filename(name: str) -> str:
    """Strip path separators / control chars from a filename so the ZIP
    arcname can't escape its target folder. Falls back to the name's
    basename when present."""
    base = Path(name).name or 'file'
    return ''.join(c for c in base if c.isprintable() and c not in ('/', '\\'))


class PollinatorRunExportCropsView(APIView):
    """GET /api/pollinator/runs/<run_id>/export-crops.zip

    ZIP of accepted, not-excluded crop images for the run. Folder per
    class: fly/, bumblebee/, butterfly/, other/. Detections without a
    persisted crop file are skipped silently (the run completed before
    crops were written, or PIL failed to render that one).
    """

    def get(self, request: Request, run_id: int) -> FileResponse:
        run = get_object_or_404(
            InferenceRun.objects.all(),
            pk=run_id,
            module=Module.POLLINATORS,
        )
        qs = Detection.objects.filter(
            inference_run=run,
            status=DetectionStatus.ACCEPTED,
            excluded_from_export=False,
        ).select_related('image')

        # SpooledTemporaryFile keeps small ZIPs in memory and spills to disk
        # past the threshold. STORED (no recompression) since JPEGs don't
        # benefit from DEFLATE.
        buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            for d in qs.iterator(chunk_size=200):
                if not d.crop:
                    continue
                cls = _effective_class(d) or 'other'
                folder = cls if cls in _CLASS_SET else 'other'
                arcname = f'{folder}/det_{d.pk}.jpg'
                try:
                    with d.crop.open('rb') as fp:
                        zf.writestr(arcname, fp.read())
                except Exception:
                    logger.exception(
                        f'Skipped crop for detection {d.pk} in run {run.pk} '
                        f'export-crops.zip'
                    )
        buf.seek(0)
        response = FileResponse(buf, content_type='application/zip')
        response['Content-Disposition'] = (
            f'attachment; filename="run-{run.pk}-crops.zip"'
        )
        return response


class PollinatorRunExportAnnotatedView(APIView):
    """GET /api/pollinator/runs/<run_id>/export-annotated.zip

    ZIP of source images for the run with detection bboxes drawn on top.
    Bboxes are red to match the red outline used in the review page so the
    export and the review screen visually agree. Only kept detections are
    drawn: excluded-from-export, rejected, unsure, and unreviewed
    detections are skipped entirely so the exported image reflects exactly
    what would land in the dataset.
    """

    def get(self, request: Request, run_id: int) -> FileResponse:
        run = get_object_or_404(
            InferenceRun.objects.all(),
            pk=run_id,
            module=Module.POLLINATORS,
        )

        # Group accepted detections (kept and excluded) by image so we open
        # each source image once.
        per_image: dict[int, list[Detection]] = {}
        for d in (
            Detection.objects.filter(
                inference_run=run,
                status=DetectionStatus.ACCEPTED,
            )
            .select_related('image')
            .iterator(chunk_size=500)
        ):
            per_image.setdefault(d.image_id, []).append(d)

        try:
            font = ImageFont.truetype(
                '/usr/share/fonts/liberation/LiberationSans-Bold.ttf',
                size=32,
            )
        except OSError:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

        buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            seen_arcnames: set[str] = set()
            for image_id, dets in per_image.items():
                first = dets[0]
                src = first.image
                if not (src and src.file):
                    continue
                try:
                    with src.file.open('rb') as fp:
                        img = Image.open(fp)
                        img.load()
                    img = img.convert('RGB')
                except Exception:
                    logger.exception(
                        f'Skipped image {image_id} in run {run.pk} export-annotated.zip'
                    )
                    continue

                draw = ImageDraw.Draw(img)
                stroke = max(2, int(max(img.width, img.height) * 0.003))
                for d in dets:
                    if d.excluded_from_export:
                        continue
                    bb = d.bbox or {}
                    try:
                        x1, y1 = int(bb['x1']), int(bb['y1'])
                        x2, y2 = int(bb['x2']), int(bb['y2'])
                    except (KeyError, TypeError, ValueError):
                        continue
                    draw.rectangle((x1, y1, x2, y2), outline=_BBOX_RED, width=stroke)
                    cls = _effective_class(d)
                    if font is not None and cls:
                        tx, ty = x1 + 2, max(0, y1 - 36)
                        draw.text((tx, ty), cls, fill=_BBOX_RED, font=font)

                roi = ((run.config or {}).get('preprocessing') or {}).get('roi_bbox')
                roi = _normalize_roi_bbox(roi)
                if roi is not None:
                    try:
                        rx, ry, rw, rh = (int(v) for v in roi)
                    except (TypeError, ValueError):
                        rx = ry = rw = rh = 0
                    if rw > 0 and rh > 0:
                        roi_stroke = max(2, int(max(img.width, img.height) * 0.0022))
                        dash = roi_stroke * 4
                        gap = max(1, int(roi_stroke * 2.5))
                        _draw_dashed_rect(
                            draw,
                            (rx, ry, rx + rw, ry + rh),
                            _ROI_COLOR,
                            roi_stroke,
                            dash,
                            gap,
                        )
                        if font is not None:
                            draw.text(
                                (rx + 6, ry + 6), 'ROI', fill=_ROI_COLOR, font=font
                            )

                arcname = _safe_filename(src.file.name)
                if not arcname:
                    arcname = f'image_{image_id}.jpg'
                base_arcname = arcname
                # Disambiguate collisions (same basename, different uploads).
                suffix = 1
                while arcname in seen_arcnames:
                    stem = Path(base_arcname).stem
                    ext = Path(base_arcname).suffix or '.jpg'
                    arcname = f'{stem}_{suffix}{ext}'
                    suffix += 1
                seen_arcnames.add(arcname)

                out = io.BytesIO()
                img.save(out, 'JPEG', quality=88)
                zf.writestr(arcname, out.getvalue())

        buf.seek(0)
        response = FileResponse(buf, content_type='application/zip')
        response['Content-Disposition'] = (
            f'attachment; filename="run-{run.pk}-annotated.zip"'
        )
        return response


class _DetectionPagination(PageNumberPagination):
    """1000 detections per page by default, capped at 5000. The review UI
    requests larger pages (page_size) to cut a 15k-detection run from ~16
    round-trips down to a handful; 1000 stays the default for any other
    caller. The frontend keeps requesting `next` until exhausted."""

    page_size = 1000
    page_size_query_param = 'page_size'
    max_page_size = 5000


# Map the frontend's reviewer-status vocabulary (and the review page's "Show"
# filter values) onto Detection.status / reviewer_label predicates. Single
# source of truth so the list view and the summary endpoint agree on what each
# label means. Mirrors BaseDetectionReadSerializer.get_reviewer_status.
_HAS_LABEL = ~Q(reviewer_label='') & Q(reviewer_label__isnull=False)
_REVIEWER_STATUS_Q: dict[str, Q] = {
    'unreviewed': Q(status=DetectionStatus.PENDING),
    'pending': Q(status=DetectionStatus.PENDING),
    'confirmed': Q(status=DetectionStatus.ACCEPTED) & ~_HAS_LABEL,
    'corrected': Q(status=DetectionStatus.ACCEPTED) & _HAS_LABEL,
    'rejected': Q(status=DetectionStatus.REJECTED),
    'unsure': Q(status=DetectionStatus.UNSURE),
    'reviewed': Q(status__in=[DetectionStatus.ACCEPTED, DetectionStatus.REJECTED]),
}


def _apply_detection_filters(qs: QuerySet[Detection], params) -> QuerySet[Detection]:
    """Opt-in server-side narrowing shared by the list and summary endpoints.
    No params -> unchanged queryset (the review page still loads the full run
    and filters client-side so its sliders stay instant). An unknown `status`
    fails loud rather than silently returning everything."""
    status_param = params.get('status')
    if status_param:
        try:
            qs = qs.filter(_REVIEWER_STATUS_Q[status_param])
        except KeyError:
            raise serializers.ValidationError(
                {
                    'status': f'unknown value {status_param!r}; '
                    f'expected one of {sorted(_REVIEWER_STATUS_Q)}'
                }
            )
    predicted_class = params.get('predicted_class')
    if predicted_class:
        qs = qs.filter(predicted_class=predicted_class)
    min_confidence = params.get('min_confidence')
    if min_confidence:
        try:
            qs = qs.filter(confidence__gte=float(min_confidence))
        except ValueError:
            raise serializers.ValidationError(
                {'min_confidence': f'not a number: {min_confidence!r}'}
            )
    return qs


class PollinatorDetectionListView(generics.ListAPIView):
    """GET /api/pollinator/runs/<run_id>/detections/?page=&page_size=
        &status=&predicted_class=&min_confidence=

    Lists pollinator detections for a run. Paginated so the review UI can
    stream batches instead of waiting on one huge response. Filters by module
    so a non-pollinator run id returns an empty list rather than raising on the
    missing pollinator_detection relation in the serializer.

    The status/predicted_class/min_confidence params are an optional
    accelerator: when a caller already knows it only needs one slice (e.g. a
    single class), it can fetch just that instead of the whole run. They are
    not required, and the review page leaves them off so its in-memory sliders
    and grouping stay instant.
    """

    serializer_class = PollinatorDetectionSerializer
    pagination_class = _DetectionPagination

    def get_queryset(self) -> QuerySet[Detection]:
        qs = _POLLINATOR_DETECTION_QS.filter(inference_run_id=self.kwargs['run_id'])
        return _apply_detection_filters(qs, self.request.query_params).order_by('id')


class PollinatorDetectionSummaryView(APIView):
    """GET /api/pollinator/runs/<run_id>/detections/summary/
        [?status=&predicted_class=&min_confidence=]

    Lightweight counts for the run: total plus a breakdown by reviewer status
    and by predicted class. Lets the UI show totals and filter-chip counts
    without shipping every detection. Honors the same opt-in filters as the
    list endpoint so a narrowed count matches a narrowed list.

    Note: the review grid's *group* counts (Needs review / per-class /
    Background) come from client-side detector logic and won't match
    by_predicted_class one-for-one; these are raw DB counts.
    """

    def get(self, request: Request, run_id: int) -> Response:
        qs = _apply_detection_filters(
            _POLLINATOR_DETECTION_QS.filter(inference_run_id=run_id),
            request.query_params,
        )
        accepted = qs.filter(status=DetectionStatus.ACCEPTED)
        corrected = accepted.filter(_HAS_LABEL).count()
        accepted_total = accepted.count()
        by_status = {
            'unreviewed': qs.filter(status=DetectionStatus.PENDING).count(),
            'confirmed': accepted_total - corrected,
            'corrected': corrected,
            'rejected': qs.filter(status=DetectionStatus.REJECTED).count(),
            'unsure': qs.filter(status=DetectionStatus.UNSURE).count(),
        }
        by_predicted_class = {
            row['predicted_class']: row['n']
            for row in qs.values('predicted_class').annotate(n=Count('id'))
        }
        return Response(
            {
                'total': qs.count(),
                'by_status': by_status,
                'by_predicted_class': by_predicted_class,
            }
        )


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


class PollinatorDetectorDatasetUploadView(APIView):
    """POST /api/pollinator/training/detector-dataset/

    Multipart body: file=<zip>, from_model_version_id=<id>.

    Validates and stages a user-supplied YOLO dataset zip
    ({images/, labels/, data.yaml}) against the target model's class list,
    remapping the uploader's class indices onto that ordering. On success
    returns a token the training submit passes back as
    config.uploaded_detector_token; nothing is staged on failure.
    """

    def post(self, request: Request, *args, **kwargs) -> Response:
        from .detector_upload import DetectorUploadError, validate_and_stage

        upload = request.FILES.get('file')
        if upload is None:
            return Response(
                {'ok': False, 'errors': ['no file provided (multipart field "file")']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from_id = request.data.get('from_model_version_id')
        try:
            source = ModelVersion.objects.get(pk=int(from_id))
        except (ModelVersion.DoesNotExist, TypeError, ValueError):
            return Response(
                {
                    'ok': False,
                    'errors': [f'from_model_version_id={from_id!r} does not exist'],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if source.module != Module.POLLINATORS or source.kind != 'detector':
            return Response(
                {'ok': False, 'errors': ['source model must be a pollinator detector']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_classes = (source.parameters or {}).get(
            'class_filter'
        ) or POLLINATOR_CLASSES
        try:
            report = validate_and_stage(upload, target_classes)
        except DetectorUploadError as exc:
            return Response(
                {'ok': False, 'errors': [str(exc)]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            report,
            status=status.HTTP_200_OK if report['ok'] else status.HTTP_400_BAD_REQUEST,
        )


def _crop_url(request: Request, detection: Detection) -> str | None:
    crop = detection.crop
    if not crop:
        return None
    try:
        return request.build_absolute_uri(crop.url)
    except ValueError:
        return None


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
          "new_since_active": 7,  # subset of `available` reviewed after the
                                  # active model finished training. 0 if no
                                  # active version exists (everything is "new").
          "by_class": {           # absent for binary (only insect/background)
            "bumblebee": 5, "fly": 18, "butterfly": 4, "other": 15
          },
          "samples": [...]        # all eligible items; shape differs by track
                                  # (per-image for detector, per-detection-with-
                                  # crop_url otherwise). The client paginates.
        }
    """

    def get(self, request: Request) -> Response:
        track = request.query_params.get('track')
        if track not in ('detector', 'binary', 'group'):
            return Response(
                {'error': "track must be one of 'detector', 'binary', 'group'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Scope the pool to the model the run will fine-tune from. Defaults to
        # the active version, but the form can pass an explicit
        # from_model_version_id so the displayed pool matches the chosen base.
        active_model = _active_model(track)
        lineage_source = active_model
        from_id = request.query_params.get('from_model_version_id')
        if from_id:
            try:
                lineage_source = ModelVersion.objects.get(
                    pk=int(from_id),
                    module=Module.POLLINATORS,
                    kind=PER_TRACK_DEFAULTS[track]['kind'],
                )
            except (ModelVersion.DoesNotExist, ValueError, TypeError):
                return Response(
                    {'error': f'invalid from_model_version_id: {from_id!r}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        consumed = len(_consumed_detection_ids(lineage_source))
        # "new since active" stays relative to the active model regardless of
        # the chosen base, so the badge keeps a stable meaning.
        active_trained_at = active_model.trained_at if active_model else None

        if track == 'detector':
            eligible = _collect_detector_pool(POLLINATOR_CLASSES, lineage_source)
            by_class = Counter(
                (d.reviewer_label or d.predicted_class) for d in eligible
            )
            new_image_ids = {
                d.image_id
                for d in eligible
                if active_trained_at is None
                or (d.reviewed_at and d.reviewed_at > active_trained_at)
            }
            # Group eligible detections per image so the drawer can show
            # one row per image with its detection count + class roster.
            per_image: dict[int, dict] = {}
            for d in eligible:
                entry = per_image.get(d.image_id)
                if entry is None:
                    entry = {
                        'image_id': d.image_id,
                        'image_filename': Path(d.image.file.name).name,
                        'detection_count': 0,
                        'classes': set(),
                    }
                    per_image[d.image_id] = entry
                entry['detection_count'] += 1
                entry['classes'].add(d.reviewer_label or d.predicted_class)
            samples = [
                {
                    'id': e['image_id'],
                    'image_filename': e['image_filename'],
                    'detection_count': e['detection_count'],
                    'classes': sorted(e['classes']),
                }
                for e in per_image.values()
            ]
            return Response(
                {
                    'track': track,
                    'available': len(per_image),
                    'consumed': consumed,
                    'new_since_active': len(new_image_ids),
                    'by_class': dict(by_class),
                    'samples': samples,
                }
            )

        if track == 'binary':
            # include_excluded so user-deselected crops still render (greyed) in
            # the drawer; counts below are computed on the trainable subset only.
            accepted, rejected = _collect_binary_pool(
                lineage_source, include_excluded=True
            )
            trainable_accepted = [d for d in accepted if not d.exclude_from_training]
            trainable_rejected = [d for d in rejected if not d.exclude_from_training]
            new_count = sum(
                1
                for d in (*trainable_accepted, *trainable_rejected)
                if active_trained_at is None
                or (d.reviewed_at and d.reviewed_at > active_trained_at)
            )
            labelled = [(d, 'insect') for d in accepted] + [
                (d, 'background') for d in rejected
            ]
            samples = [
                {
                    'id': d.pk,
                    'class': cls,
                    'crop_url': _crop_url(request, d),
                    'exclude_from_training': d.exclude_from_training,
                }
                for d, cls in labelled
            ]
            return Response(
                {
                    'track': track,
                    'available': len(trainable_accepted) + len(trainable_rejected),
                    'consumed': consumed,
                    'new_since_active': new_count,
                    'by_class': {
                        'insect': len(trainable_accepted),
                        'background': len(trainable_rejected),
                    },
                    'samples': samples,
                }
            )

        # group
        eligible = _collect_group_pool(
            POLLINATOR_CLASSES, lineage_source, include_excluded=True
        )
        trainable = [d for d in eligible if not d.exclude_from_training]
        by_class = Counter((d.reviewer_label or d.predicted_class) for d in trainable)
        new_count = sum(
            1
            for d in trainable
            if active_trained_at is None
            or (d.reviewed_at and d.reviewed_at > active_trained_at)
        )
        samples = [
            {
                'id': d.pk,
                'class': d.reviewer_label or d.predicted_class,
                'crop_url': _crop_url(request, d),
                'exclude_from_training': d.exclude_from_training,
            }
            for d in eligible
        ]
        return Response(
            {
                'track': track,
                'available': len(trainable),
                'consumed': consumed,
                'new_since_active': new_count,
                'by_class': dict(by_class),
                'samples': samples,
            }
        )


def _active_model(track: str):
    """The currently active ModelVersion for this track's kind, or None.
    Used by the pool endpoint as the lineage source for consumption scoping
    and to bucket reviewed-since-active detections."""
    kind = PER_TRACK_DEFAULTS[track]['kind']
    return ModelVersion.objects.filter(
        module=Module.POLLINATORS, kind=kind, is_active=True
    ).first()


def _resolve_thresholds(run: InferenceRun) -> tuple[float, float]:
    """Effective (yolo, group) confidence thresholds for a run's auto-select.

    Mirrors the frontend's effectiveReviewSettings(): a per-run override in
    review_settings wins, otherwise fall back to the confidences the run was
    created with in config, otherwise 0.5.
    """
    rs = run.review_settings or {}
    cfg = run.config or {}

    def _pick(setting_key: str, *cfg_path: str) -> float:
        if setting_key in rs and isinstance(rs[setting_key], (int, float)):
            return float(rs[setting_key])
        node: object = cfg
        for key in cfg_path:
            node = node.get(key) if isinstance(node, dict) else None
        return float(node) if isinstance(node, (int, float)) else 0.5

    yolo = _pick('yolo_threshold', 'yolo', 'confidence')
    group = _pick('group_threshold', 'group_classifier', 'confidence')
    return yolo, group


class PollinatorRunAutoSelectView(APIView):
    """POST /api/pollinator/runs/<id>/auto-select/

    Drives the "Suggest exports" toggle. Body: {"enabled": bool}.

    Idempotent full recompute:
      1. Persist auto_select in the run's review_settings.
      2. Revert every prior auto-accepted detection back to unreviewed.
      3. When enabled, confirm every still-unreviewed detection whose YOLO
         and group-classifier confidences both clear the run's thresholds,
         flagging them auto_accepted=True.

    Manual confirmations/corrections/rejections are never touched: they carry
    auto_accepted=False, so step 2 leaves them alone. Re-running after a
    threshold change re-derives the set from scratch.
    """

    def post(self, request: Request, run_id: int) -> Response:
        try:
            run = InferenceRun.objects.get(pk=run_id)
        except InferenceRun.DoesNotExist:
            return Response(
                {'error': 'Run not found'}, status=status.HTTP_404_NOT_FOUND
            )
        if run.module != Module.POLLINATORS:
            return Response(
                {'error': 'auto-select is only valid for pollinator runs'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enabled = request.data.get('enabled')
        if not isinstance(enabled, bool):
            return Response(
                {'error': 'enabled must be a boolean'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run.review_settings = {**(run.review_settings or {}), 'auto_select': enabled}
        run.save(update_fields=['review_settings'])

        with transaction.atomic():
            Detection.objects.filter(inference_run=run, auto_accepted=True).update(
                status=DetectionStatus.PENDING,
                auto_accepted=False,
                reviewer_label='',
                reviewed_by=None,
                reviewed_at=None,
            )

            accepted = 0
            if enabled:
                yolo, group = _resolve_thresholds(run)
                accepted = Detection.objects.filter(
                    inference_run=run,
                    status=DetectionStatus.PENDING,
                    pollinator_detection__yolo_confidence__gte=yolo,
                    pollinator_detection__insectnet_confidence__gte=group,
                ).update(
                    status=DetectionStatus.ACCEPTED,
                    auto_accepted=True,
                    reviewer_label='',
                    reviewed_by=request.user,
                    reviewed_at=timezone.now(),
                )

        return Response({'enabled': enabled, 'auto_accepted': accepted})

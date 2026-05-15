import csv
import io
import logging
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from django.db import transaction
from django.db.models import QuerySet
from django.http import FileResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
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

        mode = request.query_params.get("mode") or "per_image"

        if mode == "per_detection":
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

        filename = f'run-{run.pk}-images.csv'
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
            .select_related("image", "pollinator_detection")
            .order_by("image__captured_at", "image_id", "id")
            .iterator(chunk_size=500)
        )

        fields = [
            # Image Specific
            "session",
            "image_name",
            "camera_name",
            "datetime",
            "weather",
            # Detection specific
            "detection_id",
            "final_class",
            "yolo_class",
            "yolo_confidence",
            "insectnet_class",
            "insectnet_confidence",
            "binary_confidence",
            "final_confidence",
        ]

        session = run.name or f"Run #{run.pk}"
        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(fields)

            for d in detections:
                pd = getattr(d, "pollinator_detection", None)
                img = d.image

                final_class = (
                    d.reviewer_label
                    or d.predicted_class
                    or (pd.yolo_class if pd else None)
                    or (pd.insectnet_class if pd else None)
                )


                yield writer.writerow([
                    # image
                    session,
                    Path(img.file.name).name if img and img.file else '',
                    _camera_name(img) if img else '',
                    img.captured_at.isoformat() if img and img.captured_at else '',
                    img.weather or '' if img else '',
                    # detection
                    d.id,
                    final_class,
                    pd.yolo_class if pd else None,
                    pd.yolo_confidence if pd else None,
                    pd.insectnet_class if pd else None,
                    pd.insectnet_confidence if pd else None,
                    pd.binary_confidence if pd else None,
                    d.confidence,
                ])

        filename = f"run-{run.pk}-detections.csv"
        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# Class -> RGB color for bbox overlays. Mirrors the frontend palette in
# PollinatorsExport.vue / PollinatorsReview.vue.
_CLASS_RGB = {
    'fly': (107, 155, 210),
    'bumblebee': (230, 169, 70),
    'butterfly': (200, 123, 186),
    'other': (154, 163, 171),
}
_EXCLUDED_RGB = (239, 68, 68)


def _effective_class(d: Detection) -> str:
    return (d.reviewer_label or d.predicted_class or '').lower()


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
                folder = cls if cls in _CLASS_RGB else 'other'
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
    Kept (accepted, not excluded) bboxes get the class color and a label.
    Excluded bboxes get a red strike-through so QA can see what dropped
    out. Rejected/unsure/unreviewed detections are not drawn at all.
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
                    bb = d.bbox or {}
                    try:
                        x1, y1 = int(bb['x1']), int(bb['y1'])
                        x2, y2 = int(bb['x2']), int(bb['y2'])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if d.excluded_from_export:
                        # Red rectangle plus an X across it so the bbox
                        # reads as "removed" even on a small thumbnail.
                        draw.rectangle(
                            (x1, y1, x2, y2), outline=_EXCLUDED_RGB, width=stroke
                        )
                        draw.line((x1, y1, x2, y2), fill=_EXCLUDED_RGB, width=stroke)
                        draw.line((x1, y2, x2, y1), fill=_EXCLUDED_RGB, width=stroke)
                    else:
                        cls = _effective_class(d)
                        color = _CLASS_RGB.get(cls, _CLASS_RGB['other'])
                        draw.rectangle((x1, y1, x2, y2), outline=color, width=stroke)
                        if font is not None and cls:
                            label = cls
                            tx, ty = x1 + 2, max(0, y1 - 14)
                            draw.text((tx, ty), label, fill=color, font=font)

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
    """1000 detections per page by default, capped at 5000. Big enough that
    the Review/Export pages can paint the first batch fast, small enough
    that a 12k-image upload doesn't try to ship a single multi-MB JSON.
    The frontend keeps requesting `next` until exhausted."""

    page_size = 1000
    page_size_query_param = 'page_size'
    max_page_size = 5000


class PollinatorDetectionListView(generics.ListAPIView):
    """GET /api/pollinator/runs/<run_id>/detections/?page=&page_size=

    Lists pollinator detections for a run. Paginated (1000 per page by
    default) so the review UI can stream batches instead of waiting on a
    single huge response. Filters by module so a non-pollinator run id
    returns an empty list rather than raising on the missing
    pollinator_detection relation in the serializer.
    """

    serializer_class = PollinatorDetectionSerializer
    pagination_class = _DetectionPagination

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

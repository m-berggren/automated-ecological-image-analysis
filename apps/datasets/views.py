import os
import tempfile

from django.db.models import Count, QuerySet
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from seed_src.utils.label_extractor import LabelExtractor

from apps.datasets.models import Upload

from .models import ImageAsset, Module, Upload
from .serializers import (
    ImageAssetSerializer,
    ImageUploadSerializer,
    UploadCreateSerializer,
    UploadSerializer,
)

_DEFAULT_META: dict = {
    'width': None,
    'height': None,
    'captured_at': None,
    'flash_fired': None,
    'exif': {},
    'weather': 'unknown',
    'laplacian_var': None,
    'shutter_speed': '',
    'excluded': False,
    'exclusion_reason': '',
}


def _extract_metadata(module: str, file, upload_id=None) -> dict:
    """Module-aware metadata extraction. Pollinator uploads run the
    camera-trap EXIF/weather/fog pipeline; other modules get defaults
    until they grow their own extractor."""

    meta = dict(_DEFAULT_META)

    if module == Module.SEEDS and upload_id:
        upload = Upload.objects.select_related('inference_runs').get(pk=upload_id)
        run = upload.inference_runs.first()
        expected_species = run.config.get('selected_seed') if run else None

        if expected_species:
            extractor = LabelExtractor(gpu=False)
            extracted_text = extractor.extract_text(file)

            # Simple validation logic
            if (
                expected_species.lower() not in file.name.lower()
                and expected_species.lower() not in extracted_text.lower()
            ):
                raise ValidationError(
                    f'Image does not appear to contain {expected_species}.'
                )

    if module == Module.POLLINATORS:
        from apps.pollinator.exif import extract_image_metadata

        try:
            return extract_image_metadata(file)
        except Exception:
            return meta
    return meta


class ImageUploadView(APIView):
    """POST /api/datasets/images/; upload one image (multipart).

    Body fields (form-data):
        file    : the image file (required)
        module  : one of seeds/pollinators/pollen/flowers (required)
        purpose : 'training' or 'inference' (default: inference)
        upload  : optional Upload id; the resulting ImageAsset is linked back

    Per-module post-upload processing (EXIF, weather, exclusion flags) is
    dispatched in _extract_metadata.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request) -> Response:
        upload = ImageUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)

        file = upload.validated_data['file']
        module = upload.validated_data['module']
        upload_instance = upload.validated_data.get('upload')

        if module == Module.SEEDS and upload_instance:
            run = upload_instance.inference_runs.first()
            expected_species = run.config.get('selected_seed') if run else None

            if expected_species:
                expected_lower = expected_species.lower()

                # Check filename to validate species
                if expected_lower not in file.name.lower():
                    from seed_src.utils.label_extractor import LabelExtractor

                    # Fallback for species validation via OCR on the handwritten label
                    extractor = LabelExtractor(gpu=False)
                    ext = os.path.splitext(file.name)[1]

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=ext
                    ) as temp_file:
                        for chunk in file.chunks():
                            temp_file.write(chunk)
                        temp_path = temp_file.name

                    try:
                        extracted_text = extractor.extract_from_image(temp_path)
                        if expected_lower not in extracted_text.lower():
                            raise ValidationError(
                                f"Validation failed: '{expected_species}' not found in filename or image label."
                            )
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        # Rewind the file pointer
                        file.seek(0)

        meta = _extract_metadata(module, file)

        image = ImageAsset.objects.create(
            module=module,
            purpose=upload.validated_data['purpose'],
            file=file,
            upload=upload.validated_data.get('upload'),
            uploaded_by=request.user,
            captured_at=meta['captured_at'],
            flash_fired=meta['flash_fired'],
            exif=meta['exif'],
            weather=meta['weather'],
            excluded=meta['excluded'],
            exclusion_reason=meta['exclusion_reason'],
            metadata={
                'width': meta['width'],
                'height': meta['height'],
                'laplacian_var': meta['laplacian_var'],
                'shutter_speed': meta['shutter_speed'],
            },
        )

        return Response(
            ImageAssetSerializer(image, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class UploadListCreateView(generics.ListCreateAPIView):
    """GET  /api/datasets/uploads/?module=<module>  list upload batches (newest first).
    POST /api/datasets/uploads/                    create a new batch (body: {name, module}).

    image_count is annotated in the queryset for list (no N+1) and computed
    fresh for the POST response.
    """

    pagination_class = None

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UploadCreateSerializer
        return UploadSerializer

    def get_queryset(self) -> QuerySet[Upload]:
        qs = Upload.objects.annotate(
            image_count_annotated=Count('images'),
        ).order_by('-created_at')
        module = self.request.query_params.get('module')
        if module:
            qs = qs.filter(module=module)
        return qs

    def create(self, request, *args, **kwargs) -> Response:
        write = self.get_serializer(data=request.data)
        write.is_valid(raise_exception=True)
        upload = write.save(uploaded_by=request.user)
        return Response(
            UploadSerializer(upload).data,
            status=status.HTTP_201_CREATED,
        )


class UploadDetailView(generics.RetrieveUpdateAPIView):
    """GET   /api/datasets/uploads/<id>/  read one upload.
    PATCH /api/datasets/uploads/<id>/  edit fields (currently only `name`).

    Used by the Runs page's inline rename. Other fields on the serializer
    are read-only so the only thing this exposes for writing is `name`.
    """

    queryset = Upload.objects.all()
    serializer_class = UploadSerializer
    lookup_field = 'pk'

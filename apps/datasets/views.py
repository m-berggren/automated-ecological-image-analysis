from django.db.models import Count, QuerySet
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImageAsset, Module, Upload
from .serializers import (
    ImageAssetSerializer,
    ImageUploadSerializer,
    UploadCreateSerializer,
    UploadSerializer,
)


_DEFAULT_META: dict = {
    'width': None, 'height': None,
    'captured_at': None, 'flash_fired': None, 'exif': {},
    'weather': 'unknown', 'laplacian_var': None,
    'shutter_speed': '', 'excluded': False, 'exclusion_reason': '',
}


def _extract_metadata(module: str, file) -> dict:
    """Module-aware metadata extraction. Pollinator uploads run the
    camera-trap EXIF/weather/fog pipeline; other modules get defaults
    until they grow their own extractor."""
    if module == Module.POLLINATORS:
        from apps.pollinator.exif import extract_image_metadata
        try:
            return extract_image_metadata(file)
        except Exception:
            return dict(_DEFAULT_META)
    return dict(_DEFAULT_META)


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

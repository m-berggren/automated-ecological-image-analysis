from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ImageAsset, Upload
from .serializers import (
    ImageAssetSerializer,
    ImageUploadSerializer,
    UploadCreateSerializer,
    UploadSerializer,
    UploadUpdateSerializer,
)
from .services import extract_image_metadata


class ImageUploadView(APIView):
    """POST /api/datasets/images/ — upload one image (multipart).

    Body fields (form-data):
        file    — the image file (required)
        module  — one of seeds/pollinators/pollen/flowers (required)
        purpose — 'training' or 'inference' (default: inference)
        upload  — optional Upload id to attach the image to

    Automatically extracts EXIF metadata, derives weather from shutter
    speed, computes image sharpness (Laplacian variance), and flags
    flash/foggy images as excluded.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request) -> Response:
        upload = ImageUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)

        file = upload.validated_data['file']

        try:
            meta = extract_image_metadata(file)
        except Exception:
            meta = {
                'width': None, 'height': None,
                'captured_at': None, 'flash_fired': None, 'exif': {},
                'weather': 'unknown', 'laplacian_var': None,
                'shutter_speed': '', 'excluded': False, 'exclusion_reason': '',
            }

        image = ImageAsset.objects.create(
            module=upload.validated_data['module'],
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


class UploadListCreateView(APIView):
    """GET/POST /api/datasets/uploads/ — list or create draft uploads."""

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        qs = Upload.objects.all().order_by('-created_at')
        module = request.query_params.get('module')
        upload_status = request.query_params.get('status')
        if module:
            qs = qs.filter(module=module)
        if upload_status:
            qs = qs.filter(status=upload_status)
        return Response(UploadSerializer(qs, many=True).data)

    def post(self, request) -> Response:
        ser = UploadCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        upload = Upload.objects.create(
            module=ser.validated_data['module'],
            name=ser.validated_data.get('name', ''),
            created_by=request.user,
        )
        return Response(
            UploadSerializer(upload).data,
            status=status.HTTP_201_CREATED,
        )


class UploadDetailView(APIView):
    """GET/PATCH /api/datasets/uploads/<id>/ — read or update an upload."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int) -> Response:
        upload = get_object_or_404(Upload, pk=pk)
        return Response(UploadSerializer(upload).data)

    def patch(self, request, pk: int) -> Response:
        upload = get_object_or_404(Upload, pk=pk)
        ser = UploadUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        for field, value in ser.validated_data.items():
            setattr(upload, field, value)
        upload.save()
        return Response(UploadSerializer(upload).data)

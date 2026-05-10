from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.datasets.models import Upload, UploadStatus

from .models import InferenceRun, ModelVersion
from .serializers import (
    InferenceRunCreateSerializer,
    InferenceRunSerializer,
    ModelVersionSerializer,
)


class InferenceRunListCreateView(APIView):
    """GET/POST /api/analysis/runs/ — list runs (filterable) or queue a new one.

    Filters (GET):
        module    — seeds/pollinators/...
        status    — pending/running/completed/failed
        archived  — true/false (defaults to false)
        upload    — Upload id

    POST body:
        module, upload, name?, config?, model_version?

    Side effects: marks the Upload as READY (no longer a draft) and
    creates the Run in PENDING status. Worker pickup is not yet wired
    up — Run will sit in PENDING until a job runner is added.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        qs = InferenceRun.objects.all().order_by('-created_at')
        archived_param = request.query_params.get('archived')
        if archived_param is None:
            qs = qs.filter(archived=False)
        elif archived_param.lower() == 'true':
            qs = qs.filter(archived=True)
        for field in ('module', 'status', 'upload'):
            value = request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return Response(InferenceRunSerializer(qs, many=True).data)

    def post(self, request) -> Response:
        ser = InferenceRunCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        upload: Upload = ser.validated_data['upload']
        if upload.module != ser.validated_data['module']:
            return Response(
                {'detail': 'Upload module does not match run module.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            run = InferenceRun.objects.create(
                module=ser.validated_data['module'],
                name=ser.validated_data.get('name', ''),
                notes=ser.validated_data.get('notes', ''),
                upload=upload,
                config=ser.validated_data.get('config', {}),
                model_version=ser.validated_data.get('model_version'),
                initiated_by=request.user,
            )
            if upload.status == UploadStatus.DRAFT:
                upload.status = UploadStatus.READY
                upload.save(update_fields=['status'])

        return Response(
            InferenceRunSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class InferenceRunDetailView(APIView):
    """GET /api/analysis/runs/<id>/ — run state + counts (poll target)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int) -> Response:
        run = get_object_or_404(InferenceRun, pk=pk)
        return Response(InferenceRunSerializer(run).data)


class ModelVersionListView(APIView):
    """GET /api/analysis/models/ — list trained model versions.

    Filters: module, kind, is_active.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        qs = ModelVersion.objects.all().order_by('-created_at')
        for field in ('module', 'kind'):
            value = request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return Response(ModelVersionSerializer(qs, many=True).data)

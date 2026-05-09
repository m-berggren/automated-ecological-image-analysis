from django.db.models import QuerySet
from rest_framework import generics

from .models import ModelVersion
from .serializers import ModelVersionSerializer


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

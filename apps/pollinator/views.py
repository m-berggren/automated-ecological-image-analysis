from django.db.models import QuerySet
from rest_framework import generics, serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.analysis.models import Detection
from apps.analysis.serializers import DetectionReviewSerializer
from apps.datasets.models import Module

from .serializers import PollinatorDetectionSerializer


_POLLINATOR_DETECTION_QS = (
    Detection.objects
    .filter(inference_run__module=Module.POLLINATORS)
    .select_related('image', 'pollinator_detection')
)


class PollinatorDetectionListView(generics.ListAPIView):
    """GET /api/pollinator/runs/<run_id>/detections/

    Lists pollinator detections for a run. Filters by module so a non-
    pollinator run id returns an empty list rather than raising on the
    missing pollinator_detection relation in the serializer.
    """

    serializer_class = PollinatorDetectionSerializer
    pagination_class = None

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

from rest_framework import serializers

from apps.analysis.models import Detection
from apps.analysis.serializers import BaseDetectionReadSerializer


class PollinatorDetectionSerializer(BaseDetectionReadSerializer):
    """Read shape for pollinator detections.

    Flattens analysis.Detection (base) plus the 1:1 PollinatorDetection
    extras (yolo_*, insectnet_*, source, ...) for the pollinator review UI.
    The pollinator endpoints filter to module='pollinators', so every
    detection reaching this serializer must have a pollinator_detection row.
    """

    yolo_class = serializers.CharField(
        source='pollinator_detection.yolo_class', read_only=True,
    )
    yolo_confidence = serializers.FloatField(
        source='pollinator_detection.yolo_confidence',
        read_only=True, allow_null=True,
    )
    insectnet_class = serializers.CharField(
        source='pollinator_detection.insectnet_class', read_only=True,
    )
    insectnet_confidence = serializers.FloatField(
        source='pollinator_detection.insectnet_confidence',
        read_only=True, allow_null=True,
    )
    binary_confidence = serializers.FloatField(
        source='pollinator_detection.binary_confidence',
        read_only=True, allow_null=True,
    )
    class_probs = serializers.JSONField(
        source='pollinator_detection.class_probs', read_only=True,
    )
    source = serializers.CharField(
        source='pollinator_detection.source', read_only=True,
    )
    merge_iou = serializers.FloatField(
        source='pollinator_detection.merge_iou',
        read_only=True, allow_null=True,
    )

    class Meta(BaseDetectionReadSerializer.Meta):
        model = Detection
        fields = BaseDetectionReadSerializer.Meta.fields + (
            'yolo_class',
            'yolo_confidence',
            'insectnet_class',
            'insectnet_confidence',
            'binary_confidence',
            'class_probs',
            'source',
            'merge_iou',
        )

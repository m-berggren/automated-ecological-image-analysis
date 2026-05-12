from rest_framework import serializers

from apps.analysis.models import Detection, ModelVersion, TrainingJob
from apps.analysis.serializers import BaseDetectionReadSerializer
from apps.datasets.models import Module

from .training import PER_TRACK_DEFAULTS, POLLINATOR_CLASSES


class PollinatorDetectionSerializer(BaseDetectionReadSerializer):
    """Read shape for pollinator detections.

    Flattens analysis.Detection (base) plus the 1:1 PollinatorDetection
    extras (yolo_*, insectnet_*, source, ...) for the pollinator review UI.
    The pollinator endpoints filter to module='pollinators', so every
    detection reaching this serializer must have a pollinator_detection row.
    """

    yolo_class = serializers.CharField(
        source='pollinator_detection.yolo_class',
        read_only=True,
    )
    yolo_confidence = serializers.FloatField(
        source='pollinator_detection.yolo_confidence',
        read_only=True,
        allow_null=True,
    )
    insectnet_class = serializers.CharField(
        source='pollinator_detection.insectnet_class',
        read_only=True,
    )
    insectnet_confidence = serializers.FloatField(
        source='pollinator_detection.insectnet_confidence',
        read_only=True,
        allow_null=True,
    )
    binary_confidence = serializers.FloatField(
        source='pollinator_detection.binary_confidence',
        read_only=True,
        allow_null=True,
    )
    class_probs = serializers.JSONField(
        source='pollinator_detection.class_probs',
        read_only=True,
    )
    source = serializers.CharField(
        source='pollinator_detection.source',
        read_only=True,
    )
    merge_iou = serializers.FloatField(
        source='pollinator_detection.merge_iou',
        read_only=True,
        allow_null=True,
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


# ──────────────────────────────────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────────────────────────────────


class PollinatorTrainingCreateSerializer(serializers.ModelSerializer):
    """Write serializer for POST /api/pollinator/training/.

    Validates the pollinator-specific config shape (track, from_model_version_id,
    splits, class_filter, optional img_size). Deeper semantic validation
    (e.g. enough flagged detections to train) runs in the worker.
    """

    class Meta:
        model = TrainingJob
        fields = ('name', 'config')

    def validate_config(self, value: dict) -> dict:
        track = value.get('track')
        if track not in PER_TRACK_DEFAULTS:
            raise serializers.ValidationError(
                f'track must be one of {list(PER_TRACK_DEFAULTS.keys())}'
            )

        from_id = value.get('from_model_version_id')
        if not from_id:
            raise serializers.ValidationError('from_model_version_id is required')
        try:
            source = ModelVersion.objects.get(pk=int(from_id))
        except (ModelVersion.DoesNotExist, TypeError, ValueError):
            raise serializers.ValidationError(
                f'from_model_version_id={from_id} does not exist'
            )
        if source.module != Module.POLLINATORS:
            raise serializers.ValidationError(
                f'source model is module={source.module}, expected pollinators'
            )
        expected_kind = PER_TRACK_DEFAULTS[track]['kind']
        if source.kind != expected_kind:
            raise serializers.ValidationError(
                f"source model kind '{source.kind}' does not match "
                f"track '{track}' (expected '{expected_kind}')"
            )

        train = int(value.get('train_split', 80))
        val = int(value.get('val_split', 10))
        test = int(value.get('test_split', 10))
        if train + val + test != 100:
            raise serializers.ValidationError(
                'train_split + val_split + test_split must equal 100'
            )

        class_filter = value.get('class_filter')
        if class_filter is not None:
            if not isinstance(class_filter, list) or not class_filter:
                raise serializers.ValidationError(
                    'class_filter must be a non-empty list'
                )
            bad = [c for c in class_filter if c not in POLLINATOR_CLASSES]
            if bad:
                raise serializers.ValidationError(
                    f'unknown classes in class_filter: {bad}'
                )

        if track == 'detector':
            img_size = value.get('img_size')
            if img_size is not None:
                if not isinstance(img_size, int) or img_size <= 0 or img_size % 32:
                    raise serializers.ValidationError(
                        'img_size must be a positive multiple of 32'
                    )

        epochs = value.get('epochs')
        if epochs is not None and (not isinstance(epochs, int) or epochs <= 0):
            raise serializers.ValidationError('epochs must be a positive integer')

        return value

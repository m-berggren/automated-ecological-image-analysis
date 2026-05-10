from rest_framework import serializers

from apps.datasets.models import Module, Upload

from .models import InferenceRun, JobStatus, ModelKind, ModelVersion


class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelVersion
        fields = (
            'id', 'module', 'kind', 'version_name', 'model_file_path',
            'metrics', 'parameters', 'is_active', 'created_at',
        )
        read_only_fields = fields


class InferenceRunSerializer(serializers.ModelSerializer):
    detection_count = serializers.SerializerMethodField()
    image_count = serializers.SerializerMethodField()

    class Meta:
        model = InferenceRun
        fields = (
            'id', 'module', 'name', 'status', 'archived',
            'upload', 'model_version', 'config',
            'created_at', 'started_at', 'completed_at',
            'detection_count', 'image_count',
        )
        read_only_fields = (
            'id', 'status', 'created_at', 'started_at', 'completed_at',
            'detection_count', 'image_count',
        )

    def get_detection_count(self, obj: InferenceRun) -> int:
        return obj.detections.count()

    def get_image_count(self, obj: InferenceRun) -> int:
        if obj.upload_id:
            return obj.upload.images.count()
        return obj.images.count()


class InferenceRunCreateSerializer(serializers.Serializer):
    """Create a Run against an existing Upload with a frozen config.

    The config schema is intentionally loose JSON. Pollinator example:
        {
            "detectors": {
                "yolo": {"model_version_id": 12, "confidence": 0.4},
                "preprocessing": {"enabled": true}
            },
            "classifier": {"model_version_id": 7}
        }
    """

    module = serializers.ChoiceField(choices=Module.choices)
    upload = serializers.PrimaryKeyRelatedField(queryset=Upload.objects.all())
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    config = serializers.JSONField(required=False)
    model_version = serializers.PrimaryKeyRelatedField(
        queryset=ModelVersion.objects.all(),
        required=False,
        allow_null=True,
    )

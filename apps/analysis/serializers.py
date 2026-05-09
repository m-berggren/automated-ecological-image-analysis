from rest_framework import serializers

from apps.datasets.models import Upload

from .models import InferenceRun, ModelVersion


class ModelVersionSerializer(serializers.ModelSerializer):
    """Read serializer for trained model versions.

    Exposes the fields the frontend's run-config and models pages consume.
    Training-job-derived fields (samples, training_duration, charts) are
    deliberately omitted at this tier; they will join in once the
    TrainingJob link is wired.
    """

    class Meta:
        model = ModelVersion
        fields = (
            'id',
            'module',
            'kind',
            'version_name',
            'is_active',
            'metrics',
            'parameters',
            'created_at',
        )
        read_only_fields = ('id', 'created_at')


class InferenceRunCreateSerializer(serializers.ModelSerializer):
    """Write serializer for POST /api/analysis/runs/.

    Accepts the same payload shape the frontend posts: module, upload (FK),
    name, and the nested config blob. The config is stored as-is for
    reproducibility; per-field validation lives in the worker.
    """

    upload = serializers.PrimaryKeyRelatedField(
        queryset=Upload.objects.all(),
    )

    class Meta:
        model = InferenceRun
        fields = ('module', 'upload', 'name', 'config')


class InferenceRunListSerializer(serializers.ModelSerializer):
    """Read serializer for GET /api/analysis/runs/?module=...

    Lightweight: no config, no activity_log, no detections_by_source.
    Use the detail serializer when those are needed.
    """

    class Meta:
        model = InferenceRun
        fields = (
            'id',
            'module',
            'name',
            'upload',
            'status',
            'image_count',
            'processed_image_count',
            'detection_count',
            'failed_image_count',
            'detections_by_class',
            'created_at',
            'started_at',
            'completed_at',
            'error_message',
        )


class InferenceRunDetailSerializer(serializers.ModelSerializer):
    """Read serializer for GET /api/analysis/runs/<id>/.

    Includes every field the frontend's detail/review pages consume,
    including the frozen config and the worker activity log.
    """

    class Meta:
        model = InferenceRun
        fields = (
            'id',
            'module',
            'name',
            'upload',
            'status',
            'config',
            'image_count',
            'processed_image_count',
            'detection_count',
            'failed_image_count',
            'detections_by_class',
            'detections_by_source',
            'activity_log',
            'error_message',
            'created_at',
            'started_at',
            'completed_at',
        )

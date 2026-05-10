from pathlib import Path

from django.utils import timezone
from rest_framework import serializers

from apps.datasets.models import Upload

from .models import Detection, DetectionStatus, InferenceRun, ModelVersion  # noqa: F401


REVIEWER_STATUS_MAP = {
    'unreviewed': DetectionStatus.PENDING,
    'confirmed': DetectionStatus.ACCEPTED,
    'corrected': DetectionStatus.ACCEPTED,
    'rejected': DetectionStatus.REJECTED,
    'unsure': DetectionStatus.UNSURE,
}
REVIEWER_STATUS_CHOICES = list(REVIEWER_STATUS_MAP.keys())


class ModelVersionSerializer(serializers.ModelSerializer):
    """Read serializer for trained model versions."""

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

    Pollinator runs send model selection inside config (yolo + classifier
    ids); single-model modules like seeds may send the optional model_version
    FK instead. The serializer accepts either shape.

    Validates that upload.module matches the requested module so a
    pollinator run can't accidentally consume a seeds upload.
    """

    upload = serializers.PrimaryKeyRelatedField(
        queryset=Upload.objects.all(),
    )
    model_version = serializers.PrimaryKeyRelatedField(
        queryset=ModelVersion.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = InferenceRun
        fields = ('module', 'upload', 'name', 'config', 'model_version')

    def validate(self, attrs: dict) -> dict:
        upload = attrs.get('upload')
        module = attrs.get('module')
        if upload and module and upload.module != module:
            raise serializers.ValidationError(
                {
                    'upload': (
                        f'Upload module ({upload.module}) does not match run '
                        f'module ({module}).'
                    ),
                }
            )
        return attrs


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
            'model_version',
            'status',
            'archived',
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
            'model_version',
            'status',
            'archived',
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


class BaseDetectionReadSerializer(serializers.ModelSerializer):
    """Module-agnostic read shape for analysis.Detection.

    Per-module read serializers (e.g. PollinatorDetectionSerializer in
    apps.pollinator) subclass this to add their module-specific extras
    pulled from a 1:1 side table.
    """

    reviewer_status = serializers.SerializerMethodField()
    source_image_filename = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = (
            'id',
            'bbox',
            'confidence',
            'predicted_class',
            'reviewer_status',
            'reviewer_label',
            'source_image_filename',
        )

    def get_reviewer_status(self, obj: Detection) -> str:
        if obj.status == DetectionStatus.REJECTED:
            return 'rejected'
        if obj.status == DetectionStatus.ACCEPTED:
            return 'corrected' if obj.reviewer_label else 'confirmed'
        if obj.status == DetectionStatus.UNSURE:
            return 'unsure'
        return 'unreviewed'

    def get_source_image_filename(self, obj: Detection) -> str:
        if obj.image and obj.image.file:
            return Path(obj.image.file.name).name
        return ''


class DetectionReviewSerializer(serializers.Serializer):
    """Write serializer for PATCH /api/analysis/detections/<id>/.

    Translates the frontend's reviewer_status vocabulary back to the DB's
    Detection.status enum + reviewer_label. Stamps reviewed_by/reviewed_at.
    """

    reviewer_status = serializers.ChoiceField(choices=REVIEWER_STATUS_CHOICES)
    reviewer_label = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    flagged_for_training = serializers.BooleanField(required=False)

    def update(self, instance: Detection, validated_data: dict) -> Detection:
        rs = validated_data['reviewer_status']
        instance.status = REVIEWER_STATUS_MAP[rs]
        if rs == 'corrected':
            instance.reviewer_label = validated_data.get('reviewer_label') or ''
        else:
            instance.reviewer_label = ''
        update_fields = ['status', 'reviewer_label', 'reviewed_by', 'reviewed_at']
        if 'flagged_for_training' in validated_data:
            instance.flagged_for_training = validated_data['flagged_for_training']
            update_fields.append('flagged_for_training')
        instance.reviewed_by = self.context['request'].user
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=update_fields)
        return instance


class DetectionBulkReviewSerializer(serializers.Serializer):
    """Write serializer for POST /api/analysis/detections/bulk/.

    Apply the same reviewer action to a list of detections in one request.
    """

    ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
    reviewer_status = serializers.ChoiceField(choices=REVIEWER_STATUS_CHOICES)
    reviewer_label = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    flagged_for_training = serializers.BooleanField(required=False)

from pathlib import Path

from django.utils import timezone
from rest_framework import serializers

from apps.datasets.models import Upload

from .models import (  # noqa: F401
    Detection,
    DetectionStatus,
    InferenceRun,
    ModelArtifact,
    ModelVersion,
    TrainingJob,
)


REVIEWER_STATUS_MAP = {
    'unreviewed': DetectionStatus.PENDING,
    'confirmed': DetectionStatus.ACCEPTED,
    'corrected': DetectionStatus.ACCEPTED,
    'rejected': DetectionStatus.REJECTED,
    'unsure': DetectionStatus.UNSURE,
}
REVIEWER_STATUS_CHOICES = list(REVIEWER_STATUS_MAP.keys())


class ModelArtifactSerializer(serializers.ModelSerializer):
    """Read serializer for files attached to a ModelVersion (curves, sample
    tiles, results.csv, etc.). The `url` is built from the FileField storage
    backend so the frontend can render images and download links directly."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = ModelArtifact
        fields = ('id', 'kind', 'caption', 'url', 'created_at')
        read_only_fields = fields

    def get_url(self, obj: ModelArtifact) -> str | None:
        if not obj.file:
            return None
        request = self.context.get('request')
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ModelVersionSerializer(serializers.ModelSerializer):
    """Read serializer for trained model versions."""

    artifacts = ModelArtifactSerializer(many=True, read_only=True)

    class Meta:
        model = ModelVersion
        fields = (
            'id',
            'module',
            'kind',
            'version_name',
            'is_active',
            'description',
            'metrics',
            'parameters',
            'sample_count',
            'training_duration_seconds',
            'trained_at',
            'source_model_version',
            'created_at',
            'artifacts',
        )
        read_only_fields = ('id', 'created_at')


class ModelVersionUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for renaming a model version (PATCH). Only the
    user-editable label fields are writable; metrics/weights are immutable."""

    class Meta:
        model = ModelVersion
        fields = ('version_name', 'description')

    def validate_version_name(self, value: str) -> str:
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('version_name cannot be empty')
        qs = ModelVersion.objects.filter(version_name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'version_name "{value}" already exists')
        return value


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
            'review_settings',
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
    source_image_url = serializers.SerializerMethodField()
    source_image_id = serializers.IntegerField(source='image_id', read_only=True)
    exclude_from_training = serializers.SerializerMethodField()
    crop_url = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = (
            'id',
            'bbox',
            'confidence',
            'predicted_class',
            'reviewer_status',
            'reviewer_label',
            'auto_accepted',
            'excluded_from_export',
            'source_image_filename',
            'source_image_url',
            'source_image_id',
            'exclude_from_training',
            'crop_url',
        )

    def get_reviewer_status(self, obj: Detection) -> str:
        if obj.status == DetectionStatus.REJECTED:
            return 'rejected'
        if obj.status == DetectionStatus.ACCEPTED:
            return 'corrected' if obj.reviewer_label else 'confirmed'
        if obj.status == DetectionStatus.UNSURE:
            return 'unsure'
        return 'unreviewed'

    def get_exclude_from_training(self, obj: Detection) -> bool:
        return bool(obj.image and obj.image.exclude_from_training)

    def get_source_image_filename(self, obj: Detection) -> str:
        if obj.image and obj.image.file:
            return Path(obj.image.file.name).name
        return ''

    def get_source_image_url(self, obj: Detection) -> str | None:
        if not (obj.image and obj.image.file):
            return None
        return self._abs_url(obj.image.file.url)

    def get_crop_url(self, obj: Detection) -> str | None:
        if not obj.crop:
            return None
        return self._abs_url(obj.crop.url)

    def _abs_url(self, url: str) -> str:
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url


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

    def update(self, instance: Detection, validated_data: dict) -> Detection:
        rs = validated_data['reviewer_status']
        instance.status = REVIEWER_STATUS_MAP[rs]
        if rs == 'corrected':
            instance.reviewer_label = validated_data.get('reviewer_label') or ''
        else:
            instance.reviewer_label = ''
        instance.reviewed_by = self.context['request'].user
        instance.reviewed_at = timezone.now()
        # A manual reviewer action always overrides a prior auto-accept, so
        # this row is no longer "machine-picked" for the Export colour cue.
        instance.auto_accepted = False
        instance.save(
            update_fields=[
                'status',
                'reviewer_label',
                'reviewed_by',
                'reviewed_at',
                'auto_accepted',
            ],
        )
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


class TrainingJobListSerializer(serializers.ModelSerializer):
    """Read serializer for GET /api/analysis/training/?module=...

    Lightweight (no activity_log). Includes config so the UI can map each
    job back to its track (e.g. pollinator's detector/binary/group),
    metrics so the history can show a result column without an extra
    detail round-trip, and the initiator's username."""

    initiated_by = serializers.SerializerMethodField()
    sample_count = serializers.SerializerMethodField()

    class Meta:
        model = TrainingJob
        fields = (
            'id',
            'module',
            'name',
            'status',
            'config',
            'resulting_model',
            'image_count',
            'sample_count',
            'current_epoch',
            'total_epochs',
            'metrics',
            'initiated_by',
            'started_at',
            'completed_at',
            'error_message',
        )

    def get_initiated_by(self, obj: TrainingJob) -> str:
        user = obj.initiated_by
        if not user:
            return ''
        return user.get_username() or ''

    def get_sample_count(self, obj: TrainingJob) -> int:
        # Reviewed detections consumed by the job (crops for classifiers,
        # boxes for the detector) — the same figure as the resulting
        # ModelVersion.sample_count. image_count counts unique images, which
        # undercounts when an image carries several detections.
        return obj.training_detections.count()


class TrainingJobDetailSerializer(serializers.ModelSerializer):
    """Read serializer for GET /api/analysis/training/<id>/.

    Module-agnostic shape; per-module config knobs live inside `config` JSON.
    """

    class Meta:
        model = TrainingJob
        fields = (
            'id',
            'module',
            'name',
            'status',
            'config',
            'resulting_model',
            'image_count',
            'current_epoch',
            'total_epochs',
            'metrics',
            'activity_log',
            'error_message',
            'started_at',
            'completed_at',
        )

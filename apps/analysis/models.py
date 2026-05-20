from django.conf import settings
from django.db import models

from apps.datasets.models import Module


class ModelKind(models.TextChoices):
    """Role of a model version inside its module's pipeline.

    For pollinators: 'detector' = YOLO, 'binary_classifier' = EfficientNet
    insect/background gate, 'group_classifier' = InsectNet bumblebee/fly/
    butterfly/other classifier. For seeds: detector only.
    """

    DETECTOR = 'detector', 'Detector'
    BINARY_CLASSIFIER = 'binary_classifier', 'Binary classifier'
    GROUP_CLASSIFIER = 'group_classifier', 'Group classifier'


class ModelVersion(models.Model):
    """A trained model artifact for a given module.

    At most one ModelVersion per (module, kind) may have is_active=True;
    this is enforced in save().
    """

    module = models.CharField(max_length=20, choices=Module.choices)
    kind = models.CharField(max_length=20, choices=ModelKind.choices, blank=True)
    version_name = models.CharField(max_length=100, unique=True)
    model_file_path = models.CharField(
        max_length=512,
        help_text="Local path, 'file://...', 's3://bucket/key', or 'gs://bucket/key'.",
    )

    description = models.TextField(
        blank=True,
        help_text='Operator notes: dataset, training environment, anything '
        'worth remembering about this version.',
    )

    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text='Final metrics from the training run (val/test scores, '
        'per-class breakdowns, confusion-matrix counts).',
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text='Hyperparameters and training config (model-specific shape).',
    )

    source_model_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='derived_versions',
        help_text='If this model was trained as an incremental fine-tune, the '
        'ModelVersion whose weights were the starting point.',
    )
    sample_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Number of training samples (crops or labeled images) used.',
    )
    training_duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Wall-clock training duration in seconds.',
    )
    trained_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the underlying weights were trained. Distinct from '
        'created_at, which is when this row was registered.',
    )

    is_active = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_model_versions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['module', 'is_active']),
            models.Index(fields=['module', 'kind']),
        ]

    def save(self, *args, **kwargs) -> None:
        if self.is_active:
            ModelVersion.objects.filter(
                module=self.module,
                kind=self.kind,
                is_active=True,
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.module}:{self.version_name}'


class ModelArtifactKind(models.TextChoices):
    """Type of supplementary file attached to a ModelVersion."""

    TRAINING_CURVE = 'training_curve', 'Training curve'
    CONFUSION_MATRIX = 'confusion_matrix', 'Confusion matrix'
    PR_CURVE = 'pr_curve', 'Precision-Recall curve'
    F1_CURVE = 'f1_curve', 'F1-Confidence curve'
    PRECISION_CURVE = 'precision_curve', 'Precision-Confidence curve'
    RECALL_CURVE = 'recall_curve', 'Recall-Confidence curve'
    SAMPLE_PREDICTIONS = 'sample_predictions', 'Sample predictions'
    LABELS = 'labels', 'Label distribution'
    RESULTS_CSV = 'results_csv', 'Per-epoch metrics CSV'
    OTHER = 'other', 'Other'


def model_artifact_path(instance: 'ModelArtifact', filename: str) -> str:
    return f'model_artifacts/{instance.model_version.module}/{instance.model_version.version_name}/{filename}'


class ModelArtifact(models.Model):
    """Supplementary file attached to a ModelVersion: training-loss curve,
    confusion-matrix plot, sample prediction images, per-epoch CSV, etc.

    One ModelVersion can have many artifacts. Files are served from
    MEDIA_ROOT (or whichever backend DEFAULT_FILE_STORAGE points at).
    """

    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.CASCADE,
        related_name='artifacts',
    )
    kind = models.CharField(
        max_length=30,
        choices=ModelArtifactKind.choices,
        default=ModelArtifactKind.OTHER,
    )
    file = models.FileField(upload_to=model_artifact_path)
    caption = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['model_version', 'kind', 'created_at']
        indexes = [
            models.Index(fields=['model_version', 'kind']),
        ]

    def __str__(self) -> str:
        return f'{self.model_version.version_name} | {self.kind}'


class JobStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    PAUSED = 'paused', 'Paused'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class TrainingJob(models.Model):
    """A single training job for one module/track.

    Module-agnostic shape: per-module hyperparameters live in `config`
    JSON (e.g. pollinator's track/from_model_version_id/epochs); progress
    columns mirror InferenceRun so the polling UI pattern transfers.
    """

    module = models.CharField(max_length=20, choices=Module.choices)
    name = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )

    # Frozen config posted by the frontend (track, from_model_version_id,
    # epochs, splits, class_filter, ...). Stored as-is for reproducibility
    # and so the worker reads the same dict the user submitted.
    config = models.JSONField(default=dict, blank=True)

    resulting_model = models.OneToOneField(
        ModelVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_job',
    )
    # Set on successful completion to the exact Detection rows that fed
    # this run. Future runs of the same track exclude rows that are already
    # in any completed job's M2M — that's the consumption guard against
    # retraining on the same data twice.
    training_detections = models.ManyToManyField(
        'analysis.Detection',
        related_name='training_jobs',
        blank=True,
    )

    # Progress fields. All maintained by the worker.
    image_count = models.IntegerField(default=0)
    current_epoch = models.IntegerField(default=0)
    total_epochs = models.IntegerField(default=0)
    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text='Live metrics for the running job (loss, val_f1/macro_f1, ...)',
    )
    activity_log = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {time, message, level} entries appended by the worker',
    )
    error_message = models.TextField(blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_training_jobs',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['module', '-started_at']),
            models.Index(fields=['module', 'status']),
        ]

    def __str__(self) -> str:
        return f'TrainingJob<{self.module} #{self.pk} {self.status}>'


class InferenceRun(models.Model):
    """A single inference run over an Upload's images."""

    module = models.CharField(max_length=20, choices=Module.choices)
    name = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    upload = models.ForeignKey(
        'datasets.Upload',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inference_runs',
    )
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inference_runs',
        help_text='Single-model FK for modules like seeds. Pollinator runs '
        'use config.{yolo,binary_classifier,group_classifier}.model_version_id '
        'inside the JSON config instead and leave this null.',
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    archived = models.BooleanField(default=False)

    # Frozen run config posted by the frontend (yolo/classifier ids,
    # thresholds, preprocessing knobs). Stored as-is for reproducibility.
    config = models.JSONField(default=dict, blank=True)

    # Image set snapshot. The worker may populate `images` for retraining
    # provenance; otherwise we derive from `upload.images` at runtime.
    images = models.ManyToManyField(
        'datasets.ImageAsset',
        related_name='inference_runs',
        blank=True,
    )

    # Progress fields. All maintained by the worker; defaults cover the
    # pre-run state.
    image_count = models.IntegerField(default=0)
    processed_image_count = models.IntegerField(default=0)
    detection_count = models.IntegerField(default=0)
    failed_image_count = models.IntegerField(default=0)
    detections_by_class = models.JSONField(default=dict, blank=True)
    detections_by_source = models.JSONField(default=dict, blank=True)
    activity_log = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {time, message, level} entries appended by the worker',
    )
    error_message = models.TextField(blank=True)

    # Per-run reviewer/export preferences, distinct from the frozen `config`.
    # Shape: {auto_select: bool, yolo_threshold: float, group_threshold: float}.
    # Any missing key falls back (on the frontend) to the run's config
    # confidence values, so a fresh run's review sliders start at whatever
    # it was processed with rather than a hard-coded default.
    review_settings = models.JSONField(default=dict, blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_inference_runs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['module', '-created_at']),
            models.Index(fields=['module', 'status']),
            models.Index(fields=['module', 'archived']),
        ]

    def __str__(self) -> str:
        return f'InferenceRun<{self.module} #{self.pk} {self.status}>'


class DetectionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'
    UNSURE = 'unsure', 'Unsure'


class Detection(models.Model):
    """A single bounding box predicted by an inference run.

    Module-agnostic. predicted_class, confidence, and bbox are the
    canonical output. Module-specific extras (e.g. dual-detector
    yolo_*/insectnet_* for pollinators, morphology for seeds) live on
    1:1 side tables in the per-module app.

    Allowed predicted_class values per module:
    - seeds: species code (e.g. 'PEH', 'PHYCA') or 'inactive'
    - pollinators: 'bumblebee' / 'fly' / 'butterfly' / 'other'
    """

    inference_run = models.ForeignKey(
        InferenceRun,
        on_delete=models.CASCADE,
        related_name='detections',
    )
    image = models.ForeignKey(
        'datasets.ImageAsset',
        on_delete=models.CASCADE,
        related_name='detections',
    )

    bbox = models.JSONField(
        help_text=(
            'Source-image pixel coords: {x1, y1, x2, y2, w, h}. Written by '
            'the ML pipeline in ml-pipelines/pollinator/workflows.'
        ),
    )
    confidence = models.FloatField()
    predicted_class = models.CharField(max_length=50)
    area = models.FloatField(
        help_text='Pixel area of bbox; persisted to drive the seeds volume filter',
    )
    crop = models.ImageField(
        upload_to='runs/crops/',
        null=True,
        blank=True,
        help_text='Cropped bbox image, written after inference for review and training.',
    )

    status = models.CharField(
        max_length=20,
        choices=DetectionStatus.choices,
        default=DetectionStatus.PENDING,
    )
    reviewer_label = models.CharField(
        max_length=50,
        blank=True,
        help_text='Class assigned by a reviewer when correcting the prediction',
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_detections',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    excluded_from_export = models.BooleanField(
        default=False,
        help_text=(
            'When True, this detection is hidden from the CSV export counts '
            'even if it was accepted by the reviewer. Used by the Export '
            'step to drop duplicates (same insect detected twice).'
        ),
    )
    export_exclusion_user_set = models.BooleanField(
        default=False,
        help_text=(
            'True once a reviewer has explicitly toggled excluded_from_export '
            'from the Export page. Engulfment auto-exclude skips these rows '
            'so a manual include/exclude decision is sticky across re-runs.'
        ),
    )

    class Meta:
        indexes = [
            models.Index(fields=['inference_run', 'status']),
            models.Index(fields=['image', 'predicted_class']),
            models.Index(fields=['area']),
        ]

    def __str__(self) -> str:
        return f'Detection<{self.predicted_class} {self.confidence:.2f}>'

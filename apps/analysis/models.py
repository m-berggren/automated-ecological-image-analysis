from django.conf import settings
from django.db import models

from apps.datasets.models import Module


class ModelKind(models.TextChoices):
    """Role of a model version inside its module's pipeline.

    For pollinators: 'detector' = YOLO, 'classifier' = InsectNet binary+group.
    For seeds: detector only.
    """

    DETECTOR = 'detector', 'Detector'
    CLASSIFIER = 'classifier', 'Classifier'


class ModelVersion(models.Model):
    """A trained model artifact for a given module.

    At most one ModelVersion per (module, kind) may have is_active=True;
    this is enforced in save().
    """

    module = models.CharField(max_length=20, choices=Module.choices)
    kind = models.CharField(max_length=20, choices=ModelKind.choices, blank=True)
    version_name = models.CharField(max_length=100, unique=True)
    model_file_path = models.CharField(max_length=255)

    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {precision, recall, f1, mae, rmse, confusion_matrix}',
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text='Hyperparameters and training config (model-specific shape)',
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


class JobStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class TrainingJob(models.Model):
    module = models.CharField(max_length=20, choices=Module.choices)
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    resulting_model = models.OneToOneField(
        ModelVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_job',
    )
    training_images = models.ManyToManyField(
        'datasets.ImageAsset',
        related_name='training_jobs',
        blank=True,
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_training_jobs',
    )
    progress_log = models.TextField(blank=True)

    def __str__(self) -> str:
        return f'TrainingJob<{self.module} #{self.pk} {self.status}>'


class InferenceRun(models.Model):
    """A single inference run over an Upload's images.

    The run is created with status=pending. The frontend polls this row
    while the worker (later tier) flips status to running -> completed/failed
    and updates the progress fields.
    """

    module = models.CharField(max_length=20, choices=Module.choices)
    name = models.CharField(max_length=200, blank=True)
    upload = models.ForeignKey(
        'datasets.Upload',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inference_runs',
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )

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
        default=list, blank=True,
        help_text='List of {time, message, level} entries appended by the worker',
    )
    error_message = models.TextField(blank=True)

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
        ]

    def __str__(self) -> str:
        return f'InferenceRun<{self.module} #{self.pk} {self.status}>'


class DetectionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'
    UNSURE = 'unsure', 'Unsure'


class DetectionScope(models.TextChoices):
    ROI = 'roi', 'Inside ROI (near marked flower)'
    OUTSIDE_ROI = 'outside_roi', 'Outside ROI'
    UNKNOWN = 'unknown', 'Unknown'


class DetectionSource(models.TextChoices):
    """Which detector(s) produced a pollinator detection.

    YOLO and the InsectNet preprocessing+classifier branches run as peer
    detectors. When both find the same physical insect, source=both.
    """

    YOLO = 'yolo', 'YOLO only'
    PREPROCESSING = 'preprocessing', 'Preprocessing only'
    BOTH = 'both', 'Both detectors'


class Detection(models.Model):
    """A single bounding box predicted by an inference run.

    Allowed predicted_class values per module:
    - seeds: 'seed' / 'inactive'
    - pollinators: 'bumblebee' / 'fly' / 'butterfly' / 'other'

    Pollinator runs additionally populate yolo_class, yolo_confidence,
    insectnet_class, insectnet_confidence, and source so the review UI
    can flag YOLO/InsectNet disagreements. Seeds runs leave those fields
    null and use predicted_class+confidence only.
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

    bbox = models.JSONField(help_text='{x, y, w, h, rotation}')
    confidence = models.FloatField()
    predicted_class = models.CharField(max_length=50)
    area = models.FloatField(
        help_text='Pixel area of bbox; persisted to drive the seeds volume filter',
    )

    # Pollinator dual-detector fields. Both null for seeds detections.
    yolo_class = models.CharField(max_length=50, blank=True)
    yolo_confidence = models.FloatField(null=True, blank=True)
    insectnet_class = models.CharField(max_length=50, blank=True)
    insectnet_confidence = models.FloatField(null=True, blank=True)
    binary_confidence = models.FloatField(
        null=True, blank=True,
        help_text='InsectNet binary insect/background confidence',
    )
    class_probs = models.JSONField(
        default=dict, blank=True,
        help_text='Per-class probability dict from the group classifier',
    )
    source = models.CharField(
        max_length=20,
        choices=DetectionSource.choices,
        blank=True,
    )
    merge_iou = models.FloatField(
        null=True, blank=True,
        help_text='IoU between YOLO and preprocessing bboxes when source=both',
    )

    # Legacy InsectNet taxonomy (older notebook flow). Kept nullable so the
    # frontend can still render scientific names if a future run populates
    # them, but the current pipeline does not.
    scientific_name = models.CharField(max_length=200, blank=True)
    common_name = models.CharField(max_length=200, blank=True)
    order = models.CharField(max_length=100, blank=True)
    family = models.CharField(max_length=100, blank=True)
    energy_score = models.FloatField(
        null=True, blank=True,
        help_text='InsectNet OOD energy score; lower = more confident',
    )
    confirmed = models.BooleanField(
        null=True, blank=True,
        help_text='InsectNet in-distribution flag (True = confident ID)',
    )
    near_marker = models.BooleanField(
        null=True, blank=True,
        help_text='Detection overlaps with the marked-flower ROI zone',
    )
    detection_scope = models.CharField(
        max_length=20,
        choices=DetectionScope.choices,
        default=DetectionScope.UNKNOWN,
    )

    status = models.CharField(
        max_length=20,
        choices=DetectionStatus.choices,
        default=DetectionStatus.PENDING,
    )
    reviewer_label = models.CharField(
        max_length=50, blank=True,
        help_text='Class assigned by a reviewer when correcting the prediction',
    )
    flagged_for_training = models.BooleanField(default=False)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_detections',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['inference_run', 'status']),
            models.Index(fields=['image', 'predicted_class']),
            models.Index(fields=['flagged_for_training']),
            models.Index(fields=['area']),
            models.Index(fields=['inference_run', 'source']),
        ]

    def __str__(self) -> str:
        return f'Detection<{self.predicted_class} {self.confidence:.2f}>'

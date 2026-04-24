from django.conf import settings
from django.db import models

from apps.datasets.models import Module


class ModelVersion(models.Model):
    """A trained model artifact for a given module.

    At most one ModelVersion per module may have is_active=True; this is
    enforced in save().
    """

    module = models.CharField(max_length=20, choices=Module.choices)
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
        ]

    def save(self, *args, **kwargs):
        if self.is_active:
            ModelVersion.objects.filter(
                module=self.module,
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
    module = models.CharField(max_length=20, choices=Module.choices)
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.PROTECT,
        related_name='inference_runs',
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )

    images = models.ManyToManyField(
        'datasets.ImageAsset',
        related_name='inference_runs',
    )

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_inference_runs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

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


class Detection(models.Model):
    """A single bounding box predicted by an inference run.

    Allowed predicted_class values per module:
    - seeds: 'seed' / 'inactive'
    - pollinators: 'bumblebee' / 'fly' / 'butterfly' / 'other'

    Pollinator-specific taxonomy fields (scientific_name through
    detection_scope) are populated by the InsectNet classification
    pipeline. They are nullable so seed detections are unaffected.
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

    # InsectNet taxonomy — populated by the pollinator pipeline
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
        ]

    def __str__(self) -> str:
        return f'Detection<{self.predicted_class} {self.confidence:.2f}>'

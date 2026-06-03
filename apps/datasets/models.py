from django.conf import settings
from django.db import models


class Module(models.TextChoices):
    SEEDS = 'seeds', 'Seeds'
    POLLINATORS = 'pollinators', 'Pollinators'


class ImagePurpose(models.TextChoices):
    TRAINING = 'training', 'Training'
    INFERENCE = 'inference', 'Inference'


class ExclusionReason(models.TextChoices):
    """Only the values emitted by apps/pollinator/exif._determine_exclusion
    live here. Add new entries if/when the EXIF gate learns to detect more
    rejection categories (snow, fog, no-flowers, ...)."""

    FLASH_FIRED = 'flash_fired', 'Flash fired'
    OUT_OF_FOCUS = 'out_of_focus', 'Out of focus'


class UploadStatus(models.TextChoices):
    """An upload starts as DRAFT while files are being added; the first
    inference run that consumes it flips it to READY."""

    DRAFT = 'draft', 'Draft'
    READY = 'ready', 'Ready'


class Upload(models.Model):
    """A batch of images uploaded together for a single inference run.

    The frontend creates one Upload row (status=DRAFT), then posts each
    file separately to /api/datasets/images/ with `upload=<id>` in the
    form data. Status flips to READY when an InferenceRun consumes it.
    """

    name = models.CharField(max_length=200, blank=True)
    module = models.CharField(max_length=20, choices=Module.choices)
    status = models.CharField(
        max_length=10,
        choices=UploadStatus.choices,
        default=UploadStatus.DRAFT,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploads',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['module', '-created_at']),
            models.Index(fields=['module', 'status']),
        ]

    def __str__(self) -> str:
        return f'{self.module}: {self.name or f"Upload #{self.pk}"}'


def image_upload_path(instance: 'ImageAsset', filename: str) -> str:
    """Source images live under the run they were uploaded for.

    Uploads are created paired 1:1 with an InferenceRun in the new flow
    (PollinatorsUpload posts /api/analysis/runs/draft/ before transmitting
    files), so we can name the on-disk folder by run id. The upload still
    holds the FK because that's the column ImageAsset.upload points at.
    """
    run = instance.upload.inference_runs.first() if instance.upload_id else None
    run_id = run.pk if run is not None else 'orphan'
    return f'runs/{instance.module}/{run_id}/images/{filename}'


class ImageAsset(models.Model):
    module = models.CharField(max_length=20, choices=Module.choices)
    file = models.FileField(upload_to=image_upload_path)
    purpose = models.CharField(max_length=20, choices=ImagePurpose.choices)

    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    upload = models.ForeignKey(
        Upload,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='images',
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_images',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    captured_at = models.DateTimeField(null=True, blank=True)
    flash_fired = models.BooleanField(null=True, blank=True)
    exif = models.JSONField(default=dict, blank=True)

    notes = models.TextField(blank=True)

    excluded = models.BooleanField(default=False)
    exclusion_reason = models.CharField(
        max_length=30,
        choices=ExclusionReason.choices,
        blank=True,
    )

    metadata = models.JSONField(default=dict, blank=True)

    # Reviewer flag: opt this image into YOLO detector training. Off by
    # default — the detector trains only on images the reviewer explicitly
    # includes. Distinct from `excluded` (general dataset exclusion); the
    # training-set builder includes only images where this is True.
    include_in_training = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['module', 'purpose']),
            models.Index(fields=['module', 'excluded']),
            models.Index(fields=['captured_at']),
        ]

    def __str__(self) -> str:
        return f'{self.module}/{self.file.name}'

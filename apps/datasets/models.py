from django.conf import settings
from django.db import models


class Module(models.TextChoices):
    SEEDS = 'seeds', 'Seeds'
    POLLINATORS = 'pollinators', 'Pollinators'
    POLLEN = 'pollen', 'Pollen'
    FLOWERS = 'flowers', 'Flowers'


class ImagePurpose(models.TextChoices):
    TRAINING = 'training', 'Training'
    INFERENCE = 'inference', 'Inference'


class Weather(models.TextChoices):
    SUNNY = 'sunny', 'Sunny'
    CLOUDY = 'cloudy', 'Cloudy'
    UNKNOWN = 'unknown', 'Unknown'


class ExclusionReason(models.TextChoices):
    FLASH_FIRED = 'flash_fired', 'Flash fired'
    OUT_OF_FOCUS = 'out_of_focus', 'Out of focus'
    NO_FLOWERS = 'no_flowers', 'No visible flowers'
    DRIED_FLOWERS = 'dried_flowers', 'Dried flowers'
    SNOW = 'snow', 'Snow'
    NIGHT = 'night', 'Night'
    FOG = 'fog', 'Fog'
    OTHER = 'other', 'Other'


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
    return f'images/{instance.module}/{filename}'


class ImageAsset(models.Model):
    module = models.CharField(max_length=20, choices=Module.choices)
    file = models.FileField(upload_to=image_upload_path)
    purpose = models.CharField(max_length=20, choices=ImagePurpose.choices)

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

    site = models.CharField(max_length=100, blank=True)
    plot = models.CharField(max_length=100, blank=True)

    weather = models.CharField(
        max_length=20,
        choices=Weather.choices,
        default=Weather.UNKNOWN,
    )
    notes = models.TextField(blank=True)

    excluded = models.BooleanField(default=False)
    exclusion_reason = models.CharField(
        max_length=30,
        choices=ExclusionReason.choices,
        blank=True,
    )

    total_open_flowers = models.IntegerField(null=True, blank=True)
    total_pollinators = models.IntegerField(null=True, blank=True)
    pollinator_types_present = models.JSONField(default=list, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['module', 'purpose']),
            models.Index(fields=['module', 'excluded']),
            models.Index(fields=['captured_at']),
        ]

    def __str__(self) -> str:
        return f'{self.module}/{self.file.name}'


class AnnotationSource(models.TextChoices):
    CVAT_IMPORT = 'cvat_import', 'CVAT import'
    PROMOTED = 'promoted_from_detection', 'Promoted from detection'
    MANUAL = 'manual', 'Manual'


class Annotation(models.Model):
    """Human ground-truth bounding box.

    Allowed class_label values per module:
    - seeds: 'seed' / 'inactive' / 'unsure' (unsure is transient — must
      be resolved to seed/inactive or deleted before training).
    - pollinators: 'bumblebee' / 'fly' / 'butterfly' / 'other'.
    """

    image = models.ForeignKey(
        ImageAsset,
        on_delete=models.CASCADE,
        related_name='annotations',
    )
    class_label = models.CharField(max_length=50)
    bbox = models.JSONField(help_text='{x, y, w, h, rotation}')

    source = models.CharField(
        max_length=30,
        choices=AnnotationSource.choices,
        default=AnnotationSource.MANUAL,
    )
    promoted_from = models.ForeignKey(
        'analysis.Detection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promoted_annotations',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='annotations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['image', 'class_label']),
        ]

    def __str__(self) -> str:
        return f'{self.image_id}:{self.class_label}'


class FlowerMarker(models.Model):
    """Per-marker observations on pollinator field images.

    A field image typically has one or more colored marker clips placed
    on focal flowers. Researchers want to know, per marker:
      - how many open vs closed flowers are on it
      - whether a pollinator is visiting (and which type)
    """

    image = models.ForeignKey(
        ImageAsset,
        on_delete=models.CASCADE,
        related_name='markers',
    )
    color = models.CharField(max_length=20, help_text='e.g. "green"')
    position = models.JSONField(help_text='{x, y} or {x, y, w, h}')

    open_flowers = models.IntegerField(null=True, blank=True)
    closed_flowers = models.IntegerField(null=True, blank=True)
    pollinator_visiting = models.BooleanField(null=True, blank=True)
    visiting_types = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g. ['bumblebee', 'fly']",
    )

    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_markers',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['image', 'color']),
        ]

    def __str__(self) -> str:
        return f'{self.image_id}:{self.color}'

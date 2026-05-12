from django.db import models


class DetectionSource(models.TextChoices):
    """Which detector(s) produced a pollinator detection.

    YOLO and the InsectNet preprocessing+classifier branches run as peer
    detectors. When both find the same physical insect, source=both.
    """

    YOLO = 'yolo', 'YOLO only'
    PREPROCESSING = 'preprocessing', 'Preprocessing only'
    BOTH = 'both', 'Both detectors'


class PollinatorDetection(models.Model):
    """Pollinator-only detection metadata, 1:1 with analysis.Detection.

    Created alongside a Detection when the pollinator pipeline runs.
    Seeds and other modules don't have one of these.
    """

    detection = models.OneToOneField(
        'analysis.Detection',
        on_delete=models.CASCADE,
        related_name='pollinator_detection',
        primary_key=True,
    )

    yolo_class = models.CharField(max_length=50, blank=True)
    yolo_confidence = models.FloatField(null=True, blank=True)
    insectnet_class = models.CharField(max_length=50, blank=True)
    insectnet_confidence = models.FloatField(null=True, blank=True)
    binary_confidence = models.FloatField(
        null=True,
        blank=True,
        help_text='InsectNet binary insect/background confidence',
    )
    class_probs = models.JSONField(
        default=dict,
        blank=True,
        help_text='Per-class probability dict from the group classifier',
    )
    source = models.CharField(
        max_length=20,
        choices=DetectionSource.choices,
        blank=True,
    )
    merge_iou = models.FloatField(
        null=True,
        blank=True,
        help_text='IoU between YOLO and preprocessing bboxes when source=both',
    )

    class Meta:
        indexes = [
            models.Index(fields=['source']),
        ]

    def __str__(self) -> str:
        return f'PollinatorDetection<{self.detection_id} {self.source or "?"}>'

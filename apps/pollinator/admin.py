from django.contrib import admin

from .models import PollinatorDetection


@admin.register(PollinatorDetection)
class PollinatorDetectionAdmin(admin.ModelAdmin):
    list_display = (
        'detection',
        'yolo_class',
        'yolo_confidence',
        'insectnet_class',
        'insectnet_confidence',
        'source',
    )
    list_filter = ('source',)
    search_fields = ('yolo_class', 'insectnet_class')

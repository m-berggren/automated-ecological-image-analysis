from django.contrib import admin

from .models import Annotation, FlowerMarker, ImageAsset


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'module',
        'purpose',
        'file',
        'captured_at',
        'weather',
        'excluded',
        'uploaded_at',
    )
    list_filter = ('module', 'purpose', 'weather', 'excluded')
    search_fields = ('file', 'site', 'plot', 'notes')
    readonly_fields = ('uploaded_at',)


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ('id', 'image', 'class_label', 'source', 'created_at')
    list_filter = ('class_label', 'source')
    search_fields = ('class_label',)
    readonly_fields = ('created_at',)


@admin.register(FlowerMarker)
class FlowerMarkerAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'image',
        'color',
        'open_flowers',
        'closed_flowers',
        'pollinator_visiting',
    )
    list_filter = ('color', 'pollinator_visiting')

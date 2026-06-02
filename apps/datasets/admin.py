from django.contrib import admin

from .models import ImageAsset


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'module',
        'purpose',
        'file',
        'captured_at',
        'excluded',
        'uploaded_at',
    )
    list_filter = ('module', 'purpose', 'excluded')
    search_fields = ('file', 'notes')
    readonly_fields = ('uploaded_at',)

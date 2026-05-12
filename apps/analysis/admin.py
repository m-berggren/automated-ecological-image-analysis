from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html

from .models import (
    Detection,
    InferenceRun,
    ModelArtifact,
    ModelVersion,
    TrainingJob,
)


class ModelArtifactInline(admin.TabularInline):
    """Inline upload for charts, confusion matrices, sample predictions, etc.
    attached to a ModelVersion. Set `extra=2` so the form shows a couple of
    empty slots for new uploads each time the page is opened."""

    model = ModelArtifact
    extra = 2
    fields = ('kind', 'file', 'caption', 'preview')
    readonly_fields = ('preview',)

    def preview(self, obj: ModelArtifact) -> str:
        if not obj or not obj.file:
            return ''
        url = obj.file.url
        # Image preview for image files; download link for everything else.
        if obj.file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            return format_html('<img src="{}" style="max-height:80px"/>', url)
        return format_html('<a href="{}">download</a>', url)


class ModelVersionAdminForm(forms.ModelForm):
    """Adds a one-shot file-upload field for the weights. On save the file is
    written under MEDIA_ROOT/models/<module>/ and model_file_path is set to
    the resulting path. Leave empty to keep the existing model_file_path."""

    weights_file = forms.FileField(
        required=False,
        help_text='Upload the .pt/.pth file. On save, the file is stored '
        'under MEDIA_ROOT/models/<module>/ and overrides model_file_path. '
        'Leave empty to keep the existing path (e.g. an s3:// URI).',
    )

    class Meta:
        model = ModelVersion
        fields = '__all__'


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    form = ModelVersionAdminForm
    inlines = [ModelArtifactInline]
    list_display = (
        'id',
        'module',
        'kind',
        'version_name',
        'is_active',
        'sample_count',
        'trained_at',
        'created_at',
    )
    list_filter = ('module', 'kind', 'is_active')
    search_fields = ('version_name', 'description')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('source_model_version',)

    fieldsets = (
        (
            'Identification',
            {
                'fields': ('module', 'kind', 'version_name', 'is_active'),
            },
        ),
        (
            'Weights',
            {
                'fields': ('weights_file', 'model_file_path'),
                'description': 'Upload a file via the picker (preferred) or '
                'paste an existing path / URI (e.g. s3://bucket/key) directly.',
            },
        ),
        (
            'Provenance',
            {
                'fields': (
                    'description',
                    'source_model_version',
                    'created_by',
                    'trained_at',
                ),
            },
        ),
        (
            'Training metadata',
            {
                'fields': (
                    'sample_count',
                    'training_duration_seconds',
                    'metrics',
                    'parameters',
                ),
            },
        ),
        (
            'Timestamps',
            {
                'fields': ('created_at',),
            },
        ),
    )

    def save_model(
        self,
        request: HttpRequest,
        obj: ModelVersion,
        form: forms.ModelForm,
        change: bool,
    ) -> None:
        upload = form.cleaned_data.get('weights_file')
        if upload:
            dest_dir = Path(settings.MEDIA_ROOT) / 'models' / obj.module
            dest_dir.mkdir(parents=True, exist_ok=True)
            ext = Path(upload.name).suffix or '.bin'
            dest = dest_dir / f'{obj.version_name}{ext}'
            with dest.open('wb') as out:
                for chunk in upload.chunks():
                    out.write(chunk)
            obj.model_file_path = str(dest)
        if not obj.created_by_id and request.user.is_authenticated:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ModelArtifact)
class ModelArtifactAdmin(admin.ModelAdmin):
    list_display = ('id', 'model_version', 'kind', 'caption', 'created_at')
    list_filter = ('kind',)
    search_fields = ('model_version__version_name', 'caption')
    autocomplete_fields = ('model_version',)
    # Hide from the main admin sidebar — managed via the ModelVersion inline.
    # Keep it registered so deep links / search still work.

    def get_model_perms(self, request: HttpRequest) -> dict:
        return {}


@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'status', 'started_at', 'completed_at')
    list_filter = ('module', 'status')
    readonly_fields = ('started_at',)
    filter_horizontal = ('training_detections',)


@admin.register(InferenceRun)
class InferenceRunAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'module',
        'name',
        'status',
        'archived',
        'image_count',
        'processed_image_count',
        'detection_count',
        'created_at',
        'completed_at',
    )
    list_filter = ('module', 'status', 'archived')
    readonly_fields = ('created_at', 'started_at', 'completed_at')
    filter_horizontal = ('images',)


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'inference_run',
        'image',
        'predicted_class',
        'confidence',
        'area',
        'status',
    )
    list_filter = ('predicted_class', 'status')
    search_fields = ('predicted_class',)

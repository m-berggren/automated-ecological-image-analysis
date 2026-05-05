from django.contrib import admin

from .models import Detection, InferenceRun, ModelVersion, TrainingJob


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'kind', 'version_name', 'is_active', 'created_at')
    list_filter = ('module', 'kind', 'is_active')
    search_fields = ('version_name',)
    readonly_fields = ('created_at',)


@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'status', 'started_at', 'completed_at')
    list_filter = ('module', 'status')
    readonly_fields = ('started_at',)
    filter_horizontal = ('training_images',)


@admin.register(InferenceRun)
class InferenceRunAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'module',
        'model_version',
        'status',
        'created_at',
        'completed_at',
    )
    list_filter = ('module', 'status')
    readonly_fields = ('created_at',)
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
        'flagged_for_training',
    )
    list_filter = ('predicted_class', 'status', 'flagged_for_training')
    search_fields = ('predicted_class',)

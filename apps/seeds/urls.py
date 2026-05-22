from django.urls import path

from .views import (
    ImageManualCountView,
    SeedExportView,
    SeedReferenceReviewView,
    SeedReferenceView,
    SeedRunBulkCalculateView,
    SeedTrainingDataUploadView,
    SeedTrainingJobCreateView,
)

urlpatterns = [
    path('training/start/', SeedTrainingJobCreateView.as_view()),
    path('training/upload-data/', SeedTrainingDataUploadView.as_view()),
    path('runs/<int:run_id>/reference-review/', SeedReferenceReviewView.as_view()),
    path('runs/<int:run_id>/reference-seed/', SeedReferenceView.as_view()),
    path('runs/<int:run_id>/calculate/', SeedRunBulkCalculateView.as_view()),
    path('runs/<int:run_id>/export/', SeedExportView.as_view()),
    path('images/<int:image_id>/manual-count/', ImageManualCountView.as_view()),
]

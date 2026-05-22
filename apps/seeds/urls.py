from django.urls import path
from .views import SeedTrainingJobCreateView, SeedTrainingDataUploadView
from .views import SeedReferenceReviewView, SeedReferenceView, SeedRunBulkCalculateView

urlpatterns = [
    path('training/start/', SeedTrainingJobCreateView.as_view()),
    path('training/upload-data/', SeedTrainingDataUploadView.as_view()),

    path('runs/<int:run_id>/reference-review/', SeedReferenceReviewView.as_view()),
    path('runs/<int:run_id>/reference-seed/', SeedReferenceView.as_view()),

    path('runs/<int:run_id>/calculate/', SeedRunBulkCalculateView.as_view()),
]
from django.urls import path
from .views import SeedTrainingJobCreateView, SeedTrainingDataUploadView

urlpatterns = [
    path('training/start/', SeedTrainingJobCreateView.as_view()),
    path('training/upload-data/', SeedTrainingDataUploadView.as_view()),
]
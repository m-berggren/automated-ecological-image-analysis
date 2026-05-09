from django.urls import path

from .views import (
    DetectionListView,
    InferenceRunDetailView,
    InferenceRunListCreateView,
    ModelVersionListView,
)

urlpatterns = [
    path('models/',                          ModelVersionListView.as_view(),      name='model-version-list'),
    path('runs/',                            InferenceRunListCreateView.as_view(), name='run-list-create'),
    path('runs/<int:pk>/',                   InferenceRunDetailView.as_view(),    name='run-detail'),
    path('runs/<int:run_id>/detections/',    DetectionListView.as_view(),         name='run-detections'),
]

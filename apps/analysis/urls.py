from django.urls import path

from .views import (
    DetectionBulkView,
    DetectionDetailView,
    DetectionListView,
    InferenceRunDetailView,
    InferenceRunListCreateView,
    ModelVersionListView,
    ModelVersionSetActiveView,
)

urlpatterns = [
    path('models/', ModelVersionListView.as_view(), name='model-version-list'),
    path(
        'models/<int:pk>/set-active/',
        ModelVersionSetActiveView.as_view(),
        name='model-version-set-active',
    ),
    path('runs/', InferenceRunListCreateView.as_view(), name='run-list-create'),
    path('runs/<int:pk>/', InferenceRunDetailView.as_view(), name='run-detail'),
    path(
        'runs/<int:run_id>/detections/',
        DetectionListView.as_view(),
        name='run-detections',
    ),
    path('detections/bulk/', DetectionBulkView.as_view(), name='detection-bulk'),
    path(
        'detections/<int:pk>/', DetectionDetailView.as_view(), name='detection-detail'
    ),
]

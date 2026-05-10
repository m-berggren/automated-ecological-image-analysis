from django.urls import path

from .views import (
    DetectionBulkView,
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
    path('detections/bulk/', DetectionBulkView.as_view(), name='detection-bulk'),
]

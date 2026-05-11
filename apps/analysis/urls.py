from django.urls import path

from .views import (
    DetectionBulkView,
    InferenceRunCancelView,
    InferenceRunDetailView,
    InferenceRunListCreateView,
    ModelVersionListView,
    ModelVersionSetActiveView,
    TrainingJobCancelView,
    TrainingJobDetailView,
    TrainingJobListView,
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
        'runs/<int:pk>/cancel/',
        InferenceRunCancelView.as_view(),
        name='run-cancel',
    ),
    path('detections/bulk/', DetectionBulkView.as_view(), name='detection-bulk'),
    path('training/', TrainingJobListView.as_view(), name='training-list'),
    path(
        'training/<int:pk>/',
        TrainingJobDetailView.as_view(),
        name='training-detail',
    ),
    path(
        'training/<int:pk>/cancel/',
        TrainingJobCancelView.as_view(),
        name='training-cancel',
    ),
]

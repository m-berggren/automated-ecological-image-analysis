from django.urls import path

from .views import (
    DetectionBulkView,
    DetectionExclusionView,
    InferenceRunCancelView,
    InferenceRunDetailView,
    InferenceRunDraftView,
    InferenceRunListCreateView,
    InferenceRunPauseView,
    InferenceRunRecomputeExclusionsView,
    InferenceRunResumeView,
    InferenceRunStartView,
    ModelVersionDetailView,
    ModelVersionListCreateView,
    ModelVersionSetActiveView,
    TrainingJobCancelView,
    TrainingJobDetailView,
    TrainingJobListView,
)

urlpatterns = [
    path(
        'models/',
        ModelVersionListCreateView.as_view(),
        name='model-version-list-create',
    ),
    path(
        'models/<int:pk>/',
        ModelVersionDetailView.as_view(),
        name='model-version-detail',
    ),
    path(
        'models/<int:pk>/set-active/',
        ModelVersionSetActiveView.as_view(),
        name='model-version-set-active',
    ),
    path('runs/', InferenceRunListCreateView.as_view(), name='run-list-create'),
    path('runs/draft/', InferenceRunDraftView.as_view(), name='run-draft'),
    path('runs/<int:pk>/', InferenceRunDetailView.as_view(), name='run-detail'),
    path('runs/<int:pk>/start/', InferenceRunStartView.as_view(), name='run-start'),
    path('runs/<int:pk>/pause/', InferenceRunPauseView.as_view(), name='run-pause'),
    path(
        'runs/<int:pk>/resume/',
        InferenceRunResumeView.as_view(),
        name='run-resume',
    ),
    path(
        'runs/<int:pk>/cancel/',
        InferenceRunCancelView.as_view(),
        name='run-cancel',
    ),
    path(
        'runs/<int:pk>/recompute-exclusions/',
        InferenceRunRecomputeExclusionsView.as_view(),
        name='run-recompute-exclusions',
    ),
    path('detections/bulk/', DetectionBulkView.as_view(), name='detection-bulk'),
    path(
        'detections/<int:pk>/exclude/',
        DetectionExclusionView.as_view(),
        name='detection-exclude',
    ),
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

from django.urls import path

from .views import PollinatorDetectionDetailView, PollinatorDetectionListView

urlpatterns = [
    path(
        'runs/<int:run_id>/detections/',
        PollinatorDetectionListView.as_view(),
        name='pollinator-run-detections',
    ),
    path(
        'detections/<int:pk>/',
        PollinatorDetectionDetailView.as_view(),
        name='pollinator-detection-detail',
    ),
]

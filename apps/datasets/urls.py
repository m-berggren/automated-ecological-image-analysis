from django.urls import path

from .views import (
    ImageUploadView,
    UploadDetailView,
    UploadListCreateView,
)

urlpatterns = [
    path('images/', ImageUploadView.as_view(), name='image-upload'),
    path('uploads/', UploadListCreateView.as_view(), name='upload-list-create'),
    path('uploads/<int:pk>/', UploadDetailView.as_view(), name='upload-detail'),
]

from django.urls import path

from .views import ImageUploadView

urlpatterns = [
    path('images/', ImageUploadView.as_view(), name='image-upload'),
]

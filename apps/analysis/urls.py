from django.urls import path

from .views import ModelVersionListView

urlpatterns = [
    path('models/', ModelVersionListView.as_view(), name='model-version-list'),
]

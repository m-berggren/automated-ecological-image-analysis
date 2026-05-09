from django.urls import path

from .views import (
    InferenceRunDetailView,
    InferenceRunListCreateView,
    ModelVersionListView,
)

urlpatterns = [
    path('models/',         ModelVersionListView.as_view(),      name='model-version-list'),
    path('runs/',           InferenceRunListCreateView.as_view(), name='run-list-create'),
    path('runs/<int:pk>/',  InferenceRunDetailView.as_view(),    name='run-detail'),
]

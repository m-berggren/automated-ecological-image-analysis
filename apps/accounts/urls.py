from django.urls import path
from .views import login, register

urlpatterns = [
    path('login/', login),
    path('register/', register),
]
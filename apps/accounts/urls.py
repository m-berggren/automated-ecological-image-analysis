from django.urls import path
from .views import login, register, me, logout

urlpatterns = [
    path('login/', login),
    path('register/', register),
    path("me/", me),
    path("logout/", logout),
]
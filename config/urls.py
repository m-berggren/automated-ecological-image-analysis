from django.contrib import admin
from django.urls import path, re_path, include
from django.views.generic import TemplateView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    re_path(
        r'^(?!api/|admin/|static/|media/).*$',
        TemplateView.as_view(template_name='base.html'),
    ),
]

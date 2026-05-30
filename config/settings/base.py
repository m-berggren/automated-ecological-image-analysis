"""
Django settings for config project — base layer.

All environment-specific values are read from os.environ with sensible
defaults. Override in development.py / production.py or via real env vars.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# The pollinator ML package lives next to the Django project; make it
# importable so apps.analysis can call pollinator.inference at runtime.
sys.path.insert(0, str(BASE_DIR / 'ml_pipelines'))

# ---------------------------------------------------------------------------
# Configurable values — override via env vars or per-environment settings
# ---------------------------------------------------------------------------

JWT_ACCESS_LIFETIME_MINUTES = int(os.environ.get('JWT_ACCESS_LIFETIME_MINUTES', 720))
JWT_REFRESH_LIFETIME_DAYS = int(os.environ.get('JWT_REFRESH_LIFETIME_DAYS', 7))
JWT_ROTATE_REFRESH = os.environ.get('JWT_ROTATE_REFRESH', 'true').lower() == 'true'

CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL', 'true').lower() == 'true'

# Image quality — used by EXIF extraction to auto-populate weather and excluded fields.
# SUNNY_SHUTTER_THRESHOLD: EXIF ExposureTime denominator above this → sunny, else cloudy.
# Wingscapes TLCAM PRO has fixed f/2.8 aperture, so shutter speed reflects ambient light.
SUNNY_SHUTTER_THRESHOLD = int(os.environ.get('SUNNY_SHUTTER_THRESHOLD', 150))
# FOGGY_LAPLACIAN_THRESHOLD: Laplacian variance below this → fog/blur → excluded.
FOGGY_LAPLACIAN_THRESHOLD = float(os.environ.get('FOGGY_LAPLACIAN_THRESHOLD', 50))
# AUTO_EXCLUDE_FLASH: automatically exclude images where flash fired.
AUTO_EXCLUDE_FLASH = os.environ.get('AUTO_EXCLUDE_FLASH', 'true').lower() == 'true'
# AUTO_EXCLUDE_FOGGY: automatically exclude images below foggy threshold.
AUTO_EXCLUDE_FOGGY = os.environ.get('AUTO_EXCLUDE_FOGGY', 'true').lower() == 'true'

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.accounts',
    'apps.analysis',
    'apps.datasets',
    'apps.pollinator',
    'apps.seeds',
    'rest_framework',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
    },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Europe/Stockholm'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=JWT_ACCESS_LIFETIME_MINUTES),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=JWT_REFRESH_LIFETIME_DAYS),
    'ROTATE_REFRESH_TOKENS': JWT_ROTATE_REFRESH,
    'BLACKLIST_AFTER_ROTATION': False,
    'TOKEN_OBTAIN_SERIALIZER': 'apps.accounts.serializers.CustomTokenObtainPairSerializer',
}

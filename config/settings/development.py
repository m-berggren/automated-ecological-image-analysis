from .base import *

SECRET_KEY = 'django-insecure-+67dq%b(wpuk!y(t-lhps7fb)g__4&wn*1)ix18+7$@%3+^-b*'

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'db.sqlite3',
    }
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

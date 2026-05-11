"""Settings for running Bruno integration tests against a throwaway SQLite.

Identical to development.py except both the database and media live in
separate locations that scripts/bruno.sh wipes before each run. Keeps dev
work isolated from test fixtures.

Usage:
    DJANGO_SETTINGS_MODULE=config.settings.bruno python manage.py migrate
    DJANGO_SETTINGS_MODULE=config.settings.bruno python manage.py runserver 8001
"""

from .development import *  # noqa: F401,F403

DATABASES['default']['NAME'] = BASE_DIR / 'data' / 'db_bruno.sqlite3'
MEDIA_ROOT = BASE_DIR / 'media_bruno'

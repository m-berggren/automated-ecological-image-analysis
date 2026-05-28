#!/usr/bin/env bash
# Backend container entrypoint: prepare the runtime dirs, apply migrations,
# gather static files for nginx, then hand off to gunicorn. The db is already
# healthy here (compose `depends_on: condition: service_healthy`).
set -euo pipefail

# These are volume mount points; ensure they exist before Django touches them.
mkdir -p media staticfiles static .cache

echo '==> Applying database migrations'
python manage.py migrate --noinput

echo '==> Collecting static files'
python manage.py collectstatic --noinput

echo '==> Starting gunicorn'
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}"

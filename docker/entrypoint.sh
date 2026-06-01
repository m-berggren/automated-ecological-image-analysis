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

# Opt-in: populate a fresh DB with the real demo dataset. Idempotent, so it is
# safe to leave on; it no-ops once the demo runs exist.
if [ "${IMPORT_DEMO:-false}" = 'true' ]; then
    echo '==> Importing demo data'
    python manage.py import_demo || echo 'import_demo skipped (bundle missing?); continuing'
fi

echo '==> Starting gunicorn'
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}"

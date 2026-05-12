#!/usr/bin/env bash
# Run the Bruno integration tests against a fresh, throwaway SQLite DB.
# Each invocation wipes data/db_bruno.sqlite3 + media_bruno/, migrates from
# scratch, seeds a superuser + three active ModelVersions, starts Django on
# :8001 in the background, runs the Bruno collection, and tears everything
# down on exit.
#
# Usage:  bash scripts/bruno.sh

set -euo pipefail

cd "$(dirname "$0")/.."

export DJANGO_SETTINGS_MODULE=config.settings.bruno

# ── 1. Wipe previous state ────────────────────────────────────────────────
rm -rf data/db_bruno.sqlite3 media_bruno

# ── 1b. Fixture image for the "Upload image" Bruno test ───────────────────
# A 100x100 red JPG generated via Pillow (already a project dep).
mkdir -p tests/integration/bruno/fixtures
.venv/bin/python -c "from PIL import Image; Image.new('RGB',(100,100),'red').save('tests/integration/bruno/fixtures/test_image.jpg')"

# ── 2. Schema ─────────────────────────────────────────────────────────────
.venv/bin/python manage.py migrate --noinput

# ── 3. Seed: user + three active pollinator ModelVersions ─────────────────
# IDs 1/2/3 match the static yolo/binary/group IDs in environments/bruno.bru.
.venv/bin/python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
from apps.analysis.models import (
    Detection, DetectionStatus, InferenceRun, JobStatus, ModelKind, ModelVersion,
)
from apps.datasets.models import ImageAsset, Module, Upload
from apps.pollinator.models import DetectionSource, PollinatorDetection

User = get_user_model()
user = User.objects.create_superuser('mbx', email='mb@gmail.com', password='mb')

for pk, kind in [
    (1, ModelKind.DETECTOR),
    (2, ModelKind.BINARY_CLASSIFIER),
    (3, ModelKind.GROUP_CLASSIFIER),
]:
    ModelVersion.objects.create(
        pk=pk,
        module=Module.POLLINATORS,
        kind=kind,
        version_name=f'bruno-{kind}',
        model_file_path=f'/tmp/bruno-{kind}.pt',
        is_active=True,
    )

# Bootstrap a completed run with one Detection so the Pollinator review
# endpoints have a row to fetch. The image file path is recorded in the DB
# but doesn't need to exist on disk for these read endpoints.
upload = Upload.objects.create(module=Module.POLLINATORS, name='bruno-seed', uploaded_by=user)
image = ImageAsset.objects.create(
    module=Module.POLLINATORS,
    purpose='inference',
    file='images/pollinators/bruno-seed.jpg',
    upload=upload,
    uploaded_by=user,
)
run = InferenceRun.objects.create(
    module=Module.POLLINATORS,
    name='bruno-seed run',
    upload=upload,
    status=JobStatus.COMPLETED,
    image_count=1,
    processed_image_count=1,
    detection_count=1,
    initiated_by=user,
    config={
        'yolo': {'model_version_id': 1},
        'binary_classifier': {'model_version_id': 2},
        'group_classifier': {'model_version_id': 3},
    },
)
detection = Detection.objects.create(
    pk=1,
    inference_run=run,
    image=image,
    bbox={'x': 0, 'y': 0, 'w': 50, 'h': 50},
    confidence=0.8,
    predicted_class='fly',
    area=2500.0,
    status=DetectionStatus.PENDING,
)
PollinatorDetection.objects.create(
    detection=detection,
    yolo_class='fly',
    yolo_confidence=0.8,
    insectnet_class='fly',
    insectnet_confidence=0.75,
    binary_confidence=0.9,
    source=DetectionSource.YOLO,
)
PY

# ── 4. Run Django in the background, clean up on exit ─────────────────────
.venv/bin/python manage.py runserver 127.0.0.1:8001 --noreload \
    >/tmp/bruno-server.log 2>&1 &
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT

# Wait for the server to start accepting connections.
for _ in $(seq 1 20); do
    sleep 0.25
    if curl -fs http://127.0.0.1:8001/admin/login/ >/dev/null 2>&1; then
        break
    fi
done

# ── 5. Run Bruno against the throwaway env ────────────────────────────────
# Use the global `bru` CLI if installed; otherwise fall back to npx (which
# downloads the package on first use). Install globally for speed:
#   npm install -g @usebruno/cli
cd tests/integration/bruno
if command -v bru >/dev/null 2>&1; then
    bru run --env bruno
else
    npx -y @usebruno/cli@latest run --env bruno
fi

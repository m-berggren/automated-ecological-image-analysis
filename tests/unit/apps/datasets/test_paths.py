"""Unit tests for image_upload_path in apps.datasets.models.

Uses stand-ins for the ImageAsset instance and its related manager so the path
logic (run-scoped folder, 'orphan' fallback) is tested without a database.
"""

from types import SimpleNamespace

from apps.datasets.models import image_upload_path


def test_path_uses_first_inference_run_id():
    upload = SimpleNamespace(
        inference_runs=SimpleNamespace(first=lambda: SimpleNamespace(pk=5))
    )
    instance = SimpleNamespace(upload_id=1, upload=upload, module='seeds')
    assert image_upload_path(instance, 'x.jpg') == 'runs/seeds/5/images/x.jpg'


def test_path_orphan_when_no_upload():
    instance = SimpleNamespace(upload_id=None, module='pollinators')
    assert (
        image_upload_path(instance, 'x.jpg') == 'runs/pollinators/orphan/images/x.jpg'
    )


def test_path_orphan_when_upload_has_no_runs():
    upload = SimpleNamespace(inference_runs=SimpleNamespace(first=lambda: None))
    instance = SimpleNamespace(upload_id=1, upload=upload, module='pollinators')
    assert (
        image_upload_path(instance, 'x.jpg') == 'runs/pollinators/orphan/images/x.jpg'
    )

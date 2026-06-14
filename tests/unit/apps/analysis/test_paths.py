"""Unit tests for the upload_to path builders in apps.analysis.models.

Pure string builders; exercised with lightweight stand-ins for the model
instances so no database is needed.
"""

from types import SimpleNamespace

from apps.analysis.models import detection_crop_path, model_artifact_path


def test_detection_crop_path():
    instance = SimpleNamespace(inference_run=SimpleNamespace(module='pollinators', pk=7))
    assert (
        detection_crop_path(instance, 'WSCT0001_01.jpg')
        == 'runs/pollinators/7/crops/WSCT0001_01.jpg'
    )


def test_model_artifact_path():
    instance = SimpleNamespace(model_version=SimpleNamespace(module='seeds', id=3))
    assert (
        model_artifact_path(instance, 'curve.png')
        == 'models/seeds/3/artifacts/curve.png'
    )

"""Database-backed test for artifacts.ingest_run_dir."""

import pytest

from apps.analysis.artifacts import ingest_run_dir
from apps.analysis.models import ModelArtifact, ModelKind, ModelVersion
from apps.datasets.models import Module

pytestmark = pytest.mark.django_db


def test_ingests_known_artifacts_and_parses_metrics(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    mv = ModelVersion.objects.create(
        module=Module.POLLINATORS,
        kind=ModelKind.DETECTOR,
        version_name='v',
        model_file_path='file://x',
    )
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    (run_dir / 'results.csv').write_text('epoch,metrics/precision(B)\n1,0.8\n')
    (run_dir / 'args.yaml').write_text('epochs: 20\nimgsz: 640\n')
    (run_dir / 'F1_curve.png').write_bytes(b'\x89PNG-fake')
    (run_dir / 'ignored.txt').write_text('x')  # unknown -> skipped

    count, metrics, params = ingest_run_dir(mv, run_dir)

    # results.csv + F1_curve.png are known artifacts; args.yaml/ignored.txt aren't.
    assert count == 2
    assert metrics.get('precision') == 0.8
    assert params.get('yolo_epochs') == 20
    assert ModelArtifact.objects.filter(model_version=mv).count() == count


def test_missing_dir_returns_zeros(tmp_path):
    assert ingest_run_dir(None, tmp_path / 'nope') == (0, {}, {})

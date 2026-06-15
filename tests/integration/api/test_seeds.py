"""Integration tests for the seeds endpoints: reference-seed selection,
bulk calculate, and manual count.

Export bundle and training-start (staging dir + worker spawn) are IO/e2e and
left out of this suite.
"""

import pytest

from apps.analysis.models import Detection, InferenceRun
from apps.datasets.models import ImageAsset, Module

pytestmark = pytest.mark.django_db

SQUARE_BIG = [0, 0, 10, 0, 10, 10, 0, 10]  # area 100 -> active
SQUARE_SMALL = [0, 0, 2, 0, 2, 2, 0, 2]  # area 4 -> aborted


def _run():
    return InferenceRun.objects.create(module=Module.SEEDS)


def _image():
    return ImageAsset.objects.create(
        module=Module.SEEDS, file='x.jpg', purpose='inference'
    )


def _det(run, img, poly):
    return Detection.objects.create(
        inference_run=run,
        image=img,
        bbox={'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1, 'w': 1, 'h': 1},
        confidence=0.9,
        area=1.0,
        predicted_class='seed',
        polygon=poly,
    )


class TestReferenceSeed:
    def test_sets_reference_and_classifies(self, auth_client):
        run, img = _run(), _image()
        ref = _det(run, img, SQUARE_BIG)
        small = _det(run, img, SQUARE_SMALL)
        resp = auth_client.post(
            f'/api/seeds/runs/{run.pk}/reference-seed/',
            {'reference_detection_id': ref.id, 'image_id': img.id},
            format='json',
        )
        assert resp.status_code == 200
        ref.refresh_from_db()
        small.refresh_from_db()
        assert ref.seed_status == 'active'
        assert small.seed_status == 'aborted'
        run.refresh_from_db()
        assert run.reference_seeds[str(img.id)] == ref.id


class TestBulkCalculate:
    def test_calculate_returns_results(self, auth_client):
        run, img = _run(), _image()
        ref = _det(run, img, SQUARE_BIG)
        run.reference_seeds = {str(img.id): ref.id}
        run.save(update_fields=['reference_seeds'])
        resp = auth_client.post(f'/api/seeds/runs/{run.pk}/calculate/')
        assert resp.status_code == 200
        assert resp.data['status'] == 'success'
        assert str(img.id) in resp.data['results']


class TestManualCount:
    def test_set_manual_count(self, auth_client):
        img = _image()
        resp = auth_client.post(
            f'/api/seeds/images/{img.pk}/manual-count/',
            {'manual_count': 5},
            format='json',
        )
        assert resp.status_code == 200
        img.refresh_from_db()
        assert img.metadata['manual_active_count'] == 5

"""Integration tests for the pollinator detection endpoints:
list, summary, detail, and auto-select.

Detections that reach the read serializer need their 1:1 PollinatorDetection
side row; the summary counts query Detection directly and don't.
"""

import pytest

from apps.analysis.models import Detection, DetectionStatus, InferenceRun
from apps.datasets.models import ImageAsset, Module
from apps.pollinator.models import PollinatorDetection

pytestmark = pytest.mark.django_db


def _run(module=Module.POLLINATORS):
    return InferenceRun.objects.create(module=module)


def _image():
    return ImageAsset.objects.create(
        module=Module.POLLINATORS, file='x.jpg', purpose='inference'
    )


def _det(run, img, status=DetectionStatus.ACCEPTED, predicted_class='fly', side=True):
    d = Detection.objects.create(
        inference_run=run,
        image=img,
        bbox={'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1, 'w': 1, 'h': 1},
        confidence=0.9,
        area=1.0,
        predicted_class=predicted_class,
        status=status,
    )
    if side:
        PollinatorDetection.objects.create(
            detection=d, source='yolo', yolo_class=predicted_class, yolo_confidence=0.9
        )
    return d


class TestSummary:
    def test_status_counts(self, auth_client):
        run, img = _run(), _image()
        _det(run, img, DetectionStatus.ACCEPTED, side=False)
        _det(run, img, DetectionStatus.ACCEPTED, side=False)
        _det(run, img, DetectionStatus.PENDING, side=False)
        resp = auth_client.get(f'/api/pollinator/runs/{run.pk}/detections/summary/')
        assert resp.status_code == 200
        assert resp.data['total'] == 3
        assert resp.data['by_status']['unreviewed'] == 1
        assert resp.data['by_status']['confirmed'] == 2


class TestList:
    def test_lists_run_detections(self, auth_client):
        run, img = _run(), _image()
        _det(run, img)
        resp = auth_client.get(f'/api/pollinator/runs/{run.pk}/detections/')
        assert resp.status_code == 200
        assert resp.data['count'] == 1


class TestDetail:
    def test_get_one(self, auth_client):
        run, img = _run(), _image()
        d = _det(run, img)
        assert auth_client.get(f'/api/pollinator/detections/{d.pk}/').status_code == 200

    def test_patch_review_confirms(self, auth_client):
        run, img = _run(), _image()
        d = _det(run, img, status=DetectionStatus.PENDING)
        resp = auth_client.patch(
            f'/api/pollinator/detections/{d.pk}/',
            {'reviewer_status': 'confirmed'},
            format='json',
        )
        assert resp.status_code == 200
        d.refresh_from_db()
        assert d.status == DetectionStatus.ACCEPTED


class TestAutoSelect:
    def _url(self, run_pk):
        return f'/api/pollinator/runs/{run_pk}/auto-select/'

    def test_enable_persists_setting(self, auth_client):
        run = _run()
        resp = auth_client.post(self._url(run.pk), {'enabled': True}, format='json')
        assert resp.status_code == 200
        run.refresh_from_db()
        assert run.review_settings.get('auto_select') is True

    def test_non_bool_rejected(self, auth_client):
        run = _run()
        resp = auth_client.post(self._url(run.pk), {'enabled': 'yes'}, format='json')
        assert resp.status_code == 400

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.post(self._url(999999), {'enabled': True}, format='json')
        assert resp.status_code == 404

    def test_non_pollinator_run_rejected(self, auth_client):
        run = _run(module=Module.SEEDS)
        resp = auth_client.post(self._url(run.pk), {'enabled': True}, format='json')
        assert resp.status_code == 400

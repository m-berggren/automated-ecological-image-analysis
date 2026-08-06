"""Integration tests for the review workflow: bulk review, export/training
exclusion toggles, image include-in-training, and engulfment recompute.
"""

import pytest

from apps.analysis.models import Detection, DetectionStatus, InferenceRun
from apps.datasets.models import ImageAsset, Module

pytestmark = pytest.mark.django_db

BULK = '/api/analysis/detections/bulk/'


def _run():
    return InferenceRun.objects.create(module=Module.POLLINATORS)


def _image(include=False):
    return ImageAsset.objects.create(
        module=Module.POLLINATORS,
        file='x.jpg',
        purpose='inference',
        include_in_training=include,
    )


def _det(run, image, bbox=None, status=DetectionStatus.PENDING):
    return Detection.objects.create(
        inference_run=run,
        image=image,
        bbox=bbox or {'x1': 0, 'y1': 0, 'x2': 5, 'y2': 5},
        confidence=0.9,
        area=1.0,
        predicted_class='fly',
        status=status,
    )


class TestBulkReview:
    def test_confirm_many(self, auth_client):
        run, img = _run(), _image()
        d1, d2 = _det(run, img), _det(run, img)
        resp = auth_client.post(
            BULK, {'ids': [d1.pk, d2.pk], 'reviewer_status': 'confirmed'}, format='json'
        )
        assert resp.status_code == 200
        d1.refresh_from_db()
        d2.refresh_from_db()
        assert d1.status == DetectionStatus.ACCEPTED
        assert d2.status == DetectionStatus.ACCEPTED

    def test_corrected_sets_reviewer_label(self, auth_client):
        run, img = _run(), _image()
        d = _det(run, img)
        resp = auth_client.post(
            BULK,
            {
                'ids': [d.pk],
                'reviewer_status': 'corrected',
                'reviewer_label': 'bumblebee',
            },
            format='json',
        )
        assert resp.status_code == 200
        d.refresh_from_db()
        assert d.status == DetectionStatus.ACCEPTED
        assert d.reviewer_label == 'bumblebee'

    def test_empty_ids_rejected(self, auth_client):
        resp = auth_client.post(
            BULK, {'ids': [], 'reviewer_status': 'confirmed'}, format='json'
        )
        assert resp.status_code == 400


class TestExportExclusionToggle:
    def _url(self, pk):
        return f'/api/analysis/detections/{pk}/exclude/'

    def test_set_excluded(self, auth_client):
        d = _det(_run(), _image())
        resp = auth_client.post(self._url(d.pk), {'excluded': True}, format='json')
        assert resp.status_code == 200
        d.refresh_from_db()
        assert d.excluded_from_export is True

    def test_non_bool_rejected(self, auth_client):
        d = _det(_run(), _image())
        resp = auth_client.post(self._url(d.pk), {'excluded': 'yes'}, format='json')
        assert resp.status_code == 400

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.post(self._url(999999), {'excluded': True}, format='json')
        assert resp.status_code == 404


class TestTrainingExclusionToggle:
    def test_set_exclude_from_training(self, auth_client):
        d = _det(_run(), _image())
        resp = auth_client.post(
            f'/api/analysis/detections/{d.pk}/exclude-training/',
            {'excluded': True},
            format='json',
        )
        assert resp.status_code == 200
        d.refresh_from_db()
        assert d.exclude_from_training is True


class TestImageIncludeTraining:
    def test_set_included(self, auth_client):
        img = _image()
        resp = auth_client.post(
            f'/api/analysis/images/{img.pk}/include-training/',
            {'included': True},
            format='json',
        )
        assert resp.status_code == 200
        img.refresh_from_db()
        assert img.include_in_training is True

    def test_missing_returns_404(self, auth_client):
        resp = auth_client.post(
            '/api/analysis/images/999999/include-training/',
            {'included': True},
            format='json',
        )
        assert resp.status_code == 404


class TestRecomputeExclusions:
    def test_flags_duplicate(self, auth_client):
        run, img = _run(), _image()
        _det(
            run,
            img,
            bbox={'x1': 0, 'y1': 0, 'x2': 10, 'y2': 10},
            status=DetectionStatus.ACCEPTED,
        )
        _det(
            run,
            img,
            bbox={'x1': 3, 'y1': 3, 'x2': 5, 'y2': 5},
            status=DetectionStatus.ACCEPTED,
        )
        resp = auth_client.post(f'/api/analysis/runs/{run.pk}/recompute-exclusions/')
        assert resp.status_code == 200
        assert resp.data['excluded'] == 1

    def test_missing_run_returns_404(self, auth_client):
        resp = auth_client.post('/api/analysis/runs/999999/recompute-exclusions/')
        assert resp.status_code == 404

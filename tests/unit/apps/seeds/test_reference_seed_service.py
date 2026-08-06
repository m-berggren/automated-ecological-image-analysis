"""Database-backed tests for apps.seeds.reference_seed_service.

calculate_seed_status classifies every detection on an image as active/aborted
relative to a reference seed's area, persists the status, and writes the count
range into the image metadata. bulk_calculate_run_seed_status loops a run's
reference map and swallows per-image errors.
"""

import pytest

from apps.analysis.models import Detection, InferenceRun
from apps.datasets.models import ImageAsset, Module
from apps.seeds.reference_seed_service import (
    bulk_calculate_run_seed_status,
    calculate_seed_status,
)

pytestmark = pytest.mark.django_db

SQUARE_BIG = [0, 0, 10, 0, 10, 10, 0, 10]  # area 100
SQUARE_SMALL = [0, 0, 2, 0, 2, 2, 0, 2]  # area 4


def _run():
    return InferenceRun.objects.create(module=Module.SEEDS)


def _image():
    return ImageAsset.objects.create(
        module=Module.SEEDS, file='x.jpg', purpose='inference'
    )


def _det(run, image, polygon, confidence=0.9):
    return Detection.objects.create(
        inference_run=run,
        image=image,
        bbox={'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1, 'w': 1, 'h': 1},
        confidence=confidence,
        area=1.0,
        predicted_class='seed',
        polygon=polygon,
    )


class TestCalculateSeedStatus:
    def test_classifies_and_persists(self):
        run, img = _run(), _image()
        ref = _det(run, img, SQUARE_BIG)  # area 100 -> active
        small = _det(run, img, SQUARE_SMALL)  # area 4 <= 0.3*100 -> aborted

        result = calculate_seed_status(ref.id, img.id)

        assert result['summary']['active_seeds'] == 1
        assert result['summary']['aborted_seeds'] == 1
        ref.refresh_from_db()
        small.refresh_from_db()
        assert ref.seed_status == 'active'
        assert small.seed_status == 'aborted'

    def test_writes_metadata_to_image(self):
        run, img = _run(), _image()
        ref = _det(run, img, SQUARE_BIG)
        _det(run, img, SQUARE_SMALL)

        calculate_seed_status(ref.id, img.id)

        img.refresh_from_db()
        assert img.metadata['calculated_active'] == 1
        assert 'seed_range_min' in img.metadata
        assert 'seed_range_max' in img.metadata
        assert 'overall_confidence' in img.metadata


class TestBulkCalculateRunSeedStatus:
    def test_runs_each_reference(self):
        run, img = _run(), _image()
        ref = _det(run, img, SQUARE_BIG)
        run.reference_seeds = {str(img.id): ref.id}
        run.save(update_fields=['reference_seeds'])

        results = bulk_calculate_run_seed_status(run.id)

        assert str(img.id) in results
        assert results[str(img.id)]['summary']['active_seeds'] == 1

    def test_per_image_error_is_swallowed(self):
        run, img = _run(), _image()
        run.reference_seeds = {str(img.id): 999999}  # missing detection id
        run.save(update_fields=['reference_seeds'])

        results = bulk_calculate_run_seed_status(run.id)

        assert 'error' in results[str(img.id)]

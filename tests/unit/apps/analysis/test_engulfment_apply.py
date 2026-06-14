"""Database-backed tests for apply_engulfment_exclusions.

Exercises the overlap-based duplicate suppression end to end: the larger of a
same-insect pair is flagged excluded_from_export, reviewer-set exclusions are
left alone, and prior auto-exclusions are cleared on recompute.
"""

import pytest

from apps.analysis.engulfment import apply_engulfment_exclusions
from apps.analysis.models import Detection, DetectionStatus, InferenceRun
from apps.datasets.models import ImageAsset, Module

pytestmark = pytest.mark.django_db


def _run():
    return InferenceRun.objects.create(module=Module.POLLINATORS)


def _image():
    return ImageAsset.objects.create(
        module=Module.POLLINATORS, file='x.jpg', purpose='inference'
    )


def _det(run, image, bbox, *, excluded=False, user_set=False):
    return Detection.objects.create(
        inference_run=run,
        image=image,
        bbox=bbox,
        confidence=0.9,
        area=1.0,
        predicted_class='fly',
        status=DetectionStatus.ACCEPTED,
        excluded_from_export=excluded,
        export_exclusion_user_set=user_set,
    )


BIG = {'x1': 0, 'y1': 0, 'x2': 10, 'y2': 10}
SMALL_INSIDE = {'x1': 3, 'y1': 3, 'x2': 5, 'y2': 5}  # center (4,4) inside BIG
FAR = {'x1': 50, 'y1': 50, 'x2': 52, 'y2': 52}


def test_larger_box_of_pair_is_excluded():
    run, img = _run(), _image()
    big = _det(run, img, BIG)
    small = _det(run, img, SMALL_INSIDE)

    n = apply_engulfment_exclusions(run.id)

    assert n == 1
    big.refresh_from_db()
    small.refresh_from_db()
    assert big.excluded_from_export is True  # larger dropped
    assert small.excluded_from_export is False  # tighter crop kept


def test_non_overlapping_boxes_untouched():
    run, img = _run(), _image()
    a = _det(run, img, {'x1': 0, 'y1': 0, 'x2': 2, 'y2': 2})
    b = _det(run, img, FAR)
    assert apply_engulfment_exclusions(run.id) == 0
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.excluded_from_export is False
    assert b.excluded_from_export is False


def test_single_detection_on_image_is_ignored():
    run, img = _run(), _image()
    _det(run, img, BIG)
    assert apply_engulfment_exclusions(run.id) == 0


def test_reviewer_set_exclusion_is_not_overwritten():
    run, img = _run(), _image()
    # Larger box is reviewer-pinned: the rule must skip it.
    big = _det(run, img, BIG, user_set=True)
    _det(run, img, SMALL_INSIDE)
    assert apply_engulfment_exclusions(run.id) == 0
    big.refresh_from_db()
    assert big.excluded_from_export is False


def test_prior_auto_exclusion_is_cleared_when_no_longer_a_duplicate():
    run, img = _run(), _image()
    # Stale auto-exclusion with no overlapping partner -> recompute re-includes.
    stale = _det(run, img, BIG, excluded=True, user_set=False)
    apply_engulfment_exclusions(run.id)
    stale.refresh_from_db()
    assert stale.excluded_from_export is False

"""Database-backed tests for the training eligibility + consumption logic in
apps.pollinator.training.

These are the rules that decide which detections feed a training run:
lineage walking, the per-lineage "already consumed" guard, and the per-track
eligibility filters (PENDING-image exclusion, opt-in/exclude flags, class
filter). They are the bug-prone heart of the training pipeline, so they get
real rows rather than fakes.
"""

import pytest

from apps.analysis.models import (
    Detection,
    DetectionStatus,
    InferenceRun,
    JobStatus,
    ModelKind,
    ModelVersion,
    TrainingJob,
)
from apps.datasets.models import Module
from apps.pollinator.training import (
    _collect_binary_pool,
    _collect_detector_pool,
    _collect_group_pool,
    _consumed_detection_ids,
    _lineage_model_ids,
    _next_version_name,
)

pytestmark = pytest.mark.django_db


# --- factories ---------------------------------------------------------------


def _run():
    return InferenceRun.objects.create(module=Module.POLLINATORS)


def _image(include_in_training=False):
    from apps.datasets.models import ImageAsset

    return ImageAsset.objects.create(
        module=Module.POLLINATORS,
        file='x.jpg',
        purpose='inference',
        include_in_training=include_in_training,
    )


def _det(
    run,
    image,
    status=DetectionStatus.ACCEPTED,
    predicted_class='fly',
    reviewer_label='',
    exclude_from_training=False,
):
    return Detection.objects.create(
        inference_run=run,
        image=image,
        bbox={'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1, 'w': 1, 'h': 1},
        confidence=0.9,
        area=1.0,
        status=status,
        predicted_class=predicted_class,
        reviewer_label=reviewer_label,
        exclude_from_training=exclude_from_training,
    )


def _model(kind=ModelKind.DETECTOR, source=None, name='m'):
    return ModelVersion.objects.create(
        module=Module.POLLINATORS,
        kind=kind,
        version_name=name,
        model_file_path='file://x',
        source_model_version=source,
    )


def _ids(detections):
    return {d.id for d in detections}


# --- lineage -----------------------------------------------------------------


class TestLineageModelIds:
    def test_none_source(self):
        assert _lineage_model_ids(None) == []

    def test_walks_ancestry_chain(self):
        m1 = _model(name='m1')
        m2 = _model(source=m1, name='m2')
        m3 = _model(source=m2, name='m3')
        assert _lineage_model_ids(m3) == [m3.pk, m2.pk, m1.pk]

    def test_cycle_is_terminated(self):
        m1 = _model(name='m1')
        m2 = _model(source=m1, name='m2')
        m3 = _model(source=m2, name='m3')
        m1.source_model_version = m3  # introduce a cycle
        m1.save()
        assert _lineage_model_ids(m3) == [m3.pk, m2.pk, m1.pk]


# --- consumption guard -------------------------------------------------------


class TestConsumedDetectionIds:
    def test_none_source_consumes_nothing(self):
        assert _consumed_detection_ids(None) == set()

    def test_completed_job_in_lineage_consumes_its_detections(self):
        run, img = _run(), _image()
        d1, d2 = _det(run, img), _det(run, img)
        model = _model()
        job = TrainingJob.objects.create(
            module=Module.POLLINATORS,
            status=JobStatus.COMPLETED,
            resulting_model=model,
        )
        job.training_detections.set([d1, d2])
        assert _consumed_detection_ids(model) == {d1.id, d2.id}

    def test_incomplete_job_does_not_consume(self):
        run, img = _run(), _image()
        d1 = _det(run, img)
        model = _model()
        job = TrainingJob.objects.create(
            module=Module.POLLINATORS,
            status=JobStatus.PENDING,
            resulting_model=model,
        )
        job.training_detections.set([d1])
        assert _consumed_detection_ids(model) == set()

    def test_unrelated_lineage_does_not_consume(self):
        run, img = _run(), _image()
        d1 = _det(run, img)
        consumed_by = _model(name='b')
        job = TrainingJob.objects.create(
            module=Module.POLLINATORS,
            status=JobStatus.COMPLETED,
            resulting_model=consumed_by,
        )
        job.training_detections.set([d1])
        # A fresh, unrelated model shares no ancestry with consumed_by.
        fresh = _model(name='a')
        assert _consumed_detection_ids(fresh) == set()


# --- detector pool -----------------------------------------------------------


class TestCollectDetectorPool:
    def test_only_opt_in_pending_free_in_class(self):
        run = _run()
        img_a = _image(include_in_training=True)
        d_a = _det(run, img_a, DetectionStatus.ACCEPTED, 'fly')

        # Image with a pending detection: the whole image is ineligible.
        img_b = _image(include_in_training=True)
        _det(run, img_b, DetectionStatus.ACCEPTED, 'fly')
        _det(run, img_b, DetectionStatus.PENDING, 'fly')

        # Not opted into YOLO training.
        img_c = _image(include_in_training=False)
        _det(run, img_c, DetectionStatus.ACCEPTED, 'fly')

        pool = _collect_detector_pool(['fly'], None)
        assert _ids(pool) == {d_a.id}

    def test_class_filter_and_image_exclusion(self):
        run = _run()
        img = _image(include_in_training=True)
        d_fly = _det(run, img, DetectionStatus.ACCEPTED, 'fly')
        _det(run, img, DetectionStatus.ACCEPTED, 'other')  # filtered out by class

        assert _ids(_collect_detector_pool(['fly'], None)) == {d_fly.id}
        # Excluding the image drops everything on it.
        assert _collect_detector_pool(['fly'], None, exclude_image_ids={img.id}) == []


# --- binary pool -------------------------------------------------------------


class TestCollectBinaryPool:
    def test_accepted_and_rejected_split_with_exclusion(self):
        run, img = _run(), _image()
        acc = _det(run, img, DetectionStatus.ACCEPTED)
        rej = _det(run, img, DetectionStatus.REJECTED)
        excl = _det(run, img, DetectionStatus.ACCEPTED, exclude_from_training=True)

        accepted, rejected = _collect_binary_pool(None)
        assert _ids(accepted) == {acc.id}  # excl dropped
        assert _ids(rejected) == {rej.id}

        # include_excluded surfaces the greyed crop for the pool drawer.
        accepted_all, _r = _collect_binary_pool(None, include_excluded=True)
        assert excl.id in _ids(accepted_all)

    def test_exclude_ids_drops_specific_detections(self):
        run, img = _run(), _image()
        acc = _det(run, img, DetectionStatus.ACCEPTED)
        accepted, _r = _collect_binary_pool(None, exclude_ids={acc.id})
        assert accepted == []


# --- group pool --------------------------------------------------------------


class TestCollectGroupPool:
    def test_uses_reviewer_label_for_class(self):
        run, img = _run(), _image()
        # predicted 'fly' but reviewer corrected to 'bumblebee'.
        d = _det(run, img, DetectionStatus.ACCEPTED, 'fly', reviewer_label='bumblebee')
        assert _ids(_collect_group_pool(['bumblebee'], None)) == {d.id}
        assert _collect_group_pool(['fly'], None) == []  # corrected away from 'fly'

    def test_rejected_and_excluded_are_omitted(self):
        run, img = _run(), _image()
        _det(run, img, DetectionStatus.REJECTED, 'fly')
        _det(run, img, DetectionStatus.ACCEPTED, 'fly', exclude_from_training=True)
        assert _collect_group_pool(['fly'], None) == []


# --- version naming ----------------------------------------------------------


class TestNextVersionName:
    def test_first_version(self):
        assert _next_version_name('detector') == 'detector-v1'

    def test_increments_per_kind(self):
        _model(kind=ModelKind.DETECTOR, name='a')
        _model(kind=ModelKind.DETECTOR, name='b')
        assert _next_version_name('detector') == 'detector-v3'

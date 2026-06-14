"""Unit tests for the small status/log helpers in apps.pollinator.services."""

import pytest

from apps.analysis.models import InferenceRun
from apps.datasets.models import Module
from apps.pollinator.services import RunPaused, _append_log, _peek_status


class TestRunPaused:
    def test_is_baseexception_but_not_exception(self):
        assert issubclass(RunPaused, BaseException)
        assert not issubclass(RunPaused, Exception)

    def test_not_swallowed_by_except_exception(self):
        def worker():
            try:
                raise RunPaused()
            except Exception:  # noqa: BLE001 - prove it escapes
                return 'swallowed'

        with pytest.raises(RunPaused):
            worker()


class TestPeekStatus:
    pytestmark = pytest.mark.django_db

    def test_returns_current_status(self):
        run = InferenceRun.objects.create(module=Module.POLLINATORS)
        assert _peek_status(run.id) == run.status

    def test_missing_run_returns_none(self):
        assert _peek_status(999999) is None


class TestAppendLog:
    pytestmark = pytest.mark.django_db

    def test_appends_entry(self):
        run = InferenceRun.objects.create(module=Module.POLLINATORS)
        _append_log(run.id, 'hello', level='warning')
        run.refresh_from_db()
        assert run.activity_log[-1]['message'] == 'hello'
        assert run.activity_log[-1]['level'] == 'warning'

    def test_caps_at_200_newest_kept(self):
        run = InferenceRun.objects.create(module=Module.POLLINATORS)
        run.activity_log = [
            {'time': 't', 'message': f'm{i}', 'level': 'info'} for i in range(200)
        ]
        run.save(update_fields=['activity_log'])

        _append_log(run.id, 'newest')

        run.refresh_from_db()
        assert len(run.activity_log) == 200
        assert run.activity_log[-1]['message'] == 'newest'
        assert run.activity_log[0]['message'] == 'm1'  # oldest dropped

    def test_missing_run_is_swallowed(self):
        # Best-effort: a write to a non-existent run logs and returns, no raise.
        _append_log(999999, 'x')

"""Unit test for the RunCancelled exception contract.

RunCancelled must subclass BaseException (not Exception) so it flies through
the pipeline's ``except Exception:`` handlers and reaches the worker's outer
handler. If someone "fixes" it to inherit Exception, cancellation breaks
silently; this test guards that.
"""

import pytest

from apps.analysis.cancellation import RunCancelled


def test_is_baseexception_but_not_exception():
    assert issubclass(RunCancelled, BaseException)
    assert not issubclass(RunCancelled, Exception)


def test_not_swallowed_by_except_exception():
    def worker():
        try:
            raise RunCancelled()
        except Exception:  # noqa: BLE001 - deliberately broad to prove it escapes
            return 'swallowed'

    with pytest.raises(RunCancelled):
        worker()

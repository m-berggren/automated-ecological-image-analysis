"""Cooperative cancellation primitives shared across inference / training workers.

`RunCancelled` inherits from `BaseException` rather than `Exception` so it flies
through `except Exception:` handlers in the ML pipeline (e.g. the `_emit`
wrapper around progress callbacks) and lands at the worker's outer try/except,
which knows how to handle it (status stays CANCELLED, no Detection rows or
ModelVersion get persisted).
"""

from __future__ import annotations


class RunCancelled(BaseException):
    """Raised by a progress callback when the row's status has been
    externally flipped to CANCELLED. Workers catch it explicitly."""

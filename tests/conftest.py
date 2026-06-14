"""Auto-categorise tests by directory so they can be selected by marker.

Every test under tests/unit/ is marked `unit`, tests/integration/ -> `integration`,
tests/e2e/ -> `e2e`. No test has to be annotated by hand: `pytest -m integration`
selects the right set, and CI jobs decide which marker(s) to run (this file does
not decide *when* anything runs). Markers are declared in pyproject.toml.
"""

from pathlib import Path

import pytest

_DIR_MARKERS = ('unit', 'integration', 'e2e')


def pytest_collection_modifyitems(items):
    for item in items:
        parts = set(Path(str(item.fspath)).parts)
        for marker in _DIR_MARKERS:
            if marker in parts:
                item.add_marker(getattr(pytest.mark, marker))
                break

"""Unit tests for ml_pipelines.pollinator.device.pick_device.

Only the override precedence is asserted (explicit arg > env > auto-detect);
the auto-detect branch depends on host hardware and is intentionally untested.
"""

from ml_pipelines.pollinator import device


def test_explicit_argument_wins(monkeypatch):
    monkeypatch.setenv('AEA_DEVICE', 'mps')
    assert device.pick_device('cpu') == 'cpu'


def test_env_var_used_when_no_argument(monkeypatch):
    monkeypatch.setenv('AEA_DEVICE', 'cpu')
    assert device.pick_device() == 'cpu'


def test_empty_env_falls_through_to_autodetect(monkeypatch):
    monkeypatch.setenv('AEA_DEVICE', '')
    # Auto-detect must return one of the known device strings.
    assert device.pick_device() in {'cuda', 'mps', 'cpu'}

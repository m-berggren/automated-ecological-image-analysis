"""Compute-device selection for the pollinator models.

A single place to decide where torch runs, so the detector, classifiers, and
training entrypoints agree instead of each hardcoding a cuda/cpu ternary.

Auto-detect order: CUDA, then Apple MPS (Metal), then CPU. Set the AEA_DEVICE
environment variable to force a specific device (e.g. ``AEA_DEVICE=cpu`` as a
kill switch if MPS misbehaves on a given op). The returned value is a plain
string so it works for both ``torch.device(...)`` and ultralytics' ``device=``.

Note on MPS: some torch ops are not implemented for Metal. Set
``PYTORCH_ENABLE_MPS_FALLBACK=1`` (the dev launcher does) so those fall back to
CPU rather than raising.
"""

from __future__ import annotations

import os

import torch


def pick_device(requested: str | None = None) -> str:
    """Return a torch device string: explicit arg > AEA_DEVICE env > auto-detect."""
    choice = requested or os.environ.get('AEA_DEVICE')
    if choice:
        return choice
    if torch.cuda.is_available():
        return 'cuda'
    mps = getattr(torch.backends, 'mps', None)
    if mps is not None and mps.is_available():
        return 'mps'
    return 'cpu'

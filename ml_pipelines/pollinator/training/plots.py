"""Optional artifact plots for the classifier trainers.

The Ultralytics (YOLO) trainer auto-writes a rich set of run-dir images
(confusion matrices, curves). The classifier trainers are our own loops, so
they have to render their own. These helpers write PNGs into the run dir using
the same filenames the artifact ingester recognises
(apps/analysis/artifacts.py), so classifier model cards match YOLO's richness.

Plotting is best-effort: if matplotlib is missing the functions log and return
False rather than raising, so a headless training run never fails for lack of a
plot. No sklearn dependency — matrices are passed in pre-computed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


def save_confusion_matrix(
    matrix: Sequence[Sequence[float]],
    labels: Sequence[str],
    out_path: Path,
    title: str = 'Confusion Matrix',
) -> bool:
    """Render an (NxN) confusion matrix (matrix[true][pred]) to out_path.
    Returns True on success, False if matplotlib is unavailable or rendering
    fails. Never raises."""
    try:
        import matplotlib

        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        logger.warning('matplotlib unavailable; skipping confusion matrix %s', out_path)
        return False

    try:
        n = len(labels)
        fig, ax = plt.subplots(figsize=(1.4 * n + 2.5, 1.4 * n + 2.5))
        im = ax.imshow(matrix, cmap='Blues')
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels)
        ax.set_xlabel('Predicted')
        ax.set_ylabel('True')
        ax.set_title(title)
        flat = [v for row in matrix for v in row]
        thresh = (max(flat) / 2) if flat else 0
        for i in range(n):
            for j in range(len(matrix[i])):
                v = matrix[i][j]
                ax.text(
                    j,
                    i,
                    str(v),
                    ha='center',
                    va='center',
                    color='white' if v > thresh else 'black',
                )
        fig.tight_layout()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        logger.info('Wrote confusion matrix %s', out_path)
        return True
    except Exception:
        logger.exception('Failed to render confusion matrix %s', out_path)
        return False

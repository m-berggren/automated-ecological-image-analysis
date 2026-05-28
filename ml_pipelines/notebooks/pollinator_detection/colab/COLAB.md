# colab/

Master pipeline notebooks that orchestrate training via the `pollinator` Python package
(`ml-pipelines/pollinator/`). These are meant to be run in Google Colab and require the
backend package to be installed (either from the repo or via pip).

```
colab/
└── colab_master_pipeline.ipynb     ← full retrain orchestration
```

## Difference from experiments/

| | `experiments/` | `colab/` |
|---|---|---|
| Dependencies | Self-contained — no package needed | Calls `pollinator.*` package |
| Use case | Ad-hoc runs, standalone experimentation | Scheduled / backend-linked retraining |
| 5-class support | ✓ (`train_5class.ipynb`) | ✗ (not in package) |
| Deployed to backend | ✗ | ✓ (same code the Django app calls) |

## colab_master_pipeline.ipynb

Calls three workflow functions from the `pollinator` package:

- `pollinator.workflows.retrain_yolo` — YOLO fine-tuning (2-stage, AdamW, tiling)
- `pollinator.workflows.retrain_binary` — binary classifier retraining
- `pollinator.workflows.retrain_group` — group classifier retraining

Mount Google Drive first; the notebook expects the project root at
`/content/drive/MyDrive/pollinator-classification/`.

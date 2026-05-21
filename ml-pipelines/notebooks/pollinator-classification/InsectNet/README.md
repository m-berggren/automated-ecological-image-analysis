# InsectNet/

Third-party insect classification backbone used as the group classifier in this project.
See `NOTICE` at the project root for the full license and attribution.

---

## What it is

InsectNet is a CNN backbone pre-trained on a large insect image dataset, published in:

> Chiranjeevi, S. et al. (2025). *InsectNet: A large-scale insect classification model.*  
> PNAS Nexus. https://academic.oup.com/pnasnexus/article/4/1/pgae575/7933354

**License:** CC BY-NC 4.0 — non-commercial use only.  
**Original repo:** https://github.com/ShivaniChiranjeevi/Insect-Classifier/  
**Modification:** Energy threshold in `evaluate.py` changed from 11.49 → 25.

---

## Files

| File | In git? | Description |
|------|---------|-------------|
| `evaluate.py` | ✅ yes | Adapter code from the original repo (one line changed) |
| `data/classes.csv` | ✅ yes | InsectNet class list (1,000+ insect species) |
| `data/classes.txt` | ✅ yes | Same list as plain text |
| `model.pth` | ❌ no (gitignored) | Pre-trained weights — **must be downloaded manually** |

---

## Downloading model.pth

The weights are hosted on Zenodo and are **not included in this repo** (gitignored):

```
https://zenodo.org/records/14538000
```

Download `model.pth` from that page and place it directly in this folder:

```
InsectNet/
└── model.pth   ← download here
```

---

## When is it needed?

| Notebook | Needs InsectNet? | Why |
|----------|-----------------|-----|
| `experiments/training/train_binary_group.ipynb` | ✅ yes | Loads `InsectNet/model.pth` as the group classifier backbone |
| `experiments/training/train_5class.ipynb` | ✅ yes | Same |
| `experiments/training/retrain_cropbased.ipynb` | ❌ no | Loads the already fine-tuned `models/4group_insectnet.pth` — InsectNet weights are baked in |
| All inference and evaluation notebooks | ❌ no | Only the fine-tuned `.pth` in `models/` is used |

In short: you only need `model.pth` if you are **training from scratch**. Retraining and inference use `models/4group_insectnet.pth` which already contains the adapted InsectNet weights.

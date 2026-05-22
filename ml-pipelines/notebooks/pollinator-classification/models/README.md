# models/

Current production model weights used for inference. Tracked in git via Git LFS (or stored
separately — check `.gitignore`).

```
models/
├── binary_best.pth         ← binary classifier: insect vs background
├── 4group_insectnet.pth    ← 4-class group classifier (InsectNet backbone)
├── 5group_efficientnet.pth ← 5-class classifier (EfficientNet backbone)
├── 5group_insectnet.pth    ← 5-class classifier (InsectNet backbone)
└── yolo_best.pt            ← YOLO detector (fine-tuned from yolo26n.pt)
```

## Updating a model

After a training run completes, copy the best checkpoint here:

```bash
# After YOLO training
cp outputs/training/model_runs/{run_name}/weights/best.pt models/yolo_best.pt

# After classifier retraining
cp outputs/training/model_runs/{run_name}/binary_best.pth models/binary_best.pth
```

The notebooks load models from this folder by default. Historical checkpoints stay in
`outputs/training/model_runs/` — only the current best weights live here.

## Model architecture

| File | Architecture | Classes | Notes |
|------|-------------|---------|-------|
| `binary_best.pth` | EfficientNet-B2 **or** InsectNet | 2 (insect, background) | Stage 1 of crop pipeline; backbone auto-detected from checkpoint |
| `binary_efficientnet_best.pth` | EfficientNet-B2 | 2 | Saved when `BINARY_BACKBONE='both'`; kept for comparison |
| `binary_insectnet_best.pth` | InsectNet | 2 | Saved when `BINARY_BACKBONE='both'`; kept for comparison |
| `4group_insectnet.pth` | InsectNet (fine-tuned) | 4 (bee, fly, butterfly, other) | Stage 2 of crop pipeline |
| `5group_efficientnet.pth` | EfficientNet-B2 | 5 (+ background) | Standalone alternative |
| `5group_insectnet.pth` | InsectNet (fine-tuned) | 5 (+ background) | Standalone alternative |
| `yolo_best.pt` | YOLOv26n (Ultralytics) | 4 (bee, fly, butterfly, other) | Fine-tuned 2-stage |

The `*insectnet*.pth` files are fine-tuned from the InsectNet backbone. The backbone code
and original weights live in `InsectNet/` — see `InsectNet/README.md` for the download
link. You only need `InsectNet/model.pth` if retraining from scratch; retraining and
inference use the `.pth` files in this folder directly.

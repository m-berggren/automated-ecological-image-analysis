# Operating-curve figure: data and pipeline

How `combined_operating_curve.png` ("Recall against review burden as the YOLO
threshold varies") is produced, from raw data to final image. The same chain
also feeds `combined_complementarity.png`, `combined_failure_panel.png`, and the
combined-pipeline results table, since they all read the same stored
predictions.

## Paths

All paths are resolved once in `paths.py`. The small inputs are vendored next to
the scripts so a run here is self-contained **on disk**; the large inputs default
to the thesis repo and are overridable by environment variable.

The JSON artifacts and `figures/` are git-ignored (see `.gitignore`), matching
the repo convention that ignores any `predictions/` directory. So a fresh clone
has empty data: repopulate `predictions/` (re-run Stage 1, copy the JSONs in, or
point `FLY_EVAL_PRED_DIR` at them) before running stages 2 and 3.

| Name | Default | Override |
|---|---|---|
| `PRED_DIR` | `./predictions/` | `FLY_EVAL_PRED_DIR` |
| `VETTED_JSON` | `./predictions/vetted_predictions.json` | `FLY_EVAL_VETTED` |
| `OPERATING_CURVE_JSON` | `./operating_curve.json` | `FLY_EVAL_CURVE` |
| `DATASET` (`IMAGES`/`LABELS`) | `thesis-aid/yolo-test-inference-with-annotations` | `FLY_EVAL_DATASET` |
| `GRID` | `thesis-aid/grid` | `FLY_EVAL_GRID` |
| `OUT_DIR` | `./figures/` | `FLY_EVAL_OUT` |

To retarget on a machine that lacks the thesis repo, set `THESIS_AID_ROOT` (the
fallback for the un-vendored inputs) or the specific `FLY_EVAL_*` variables. No
code edits needed.

## Raw inputs

1. **Vetted field images** in `$DATASET/images/` (358 frames, 3008x1692, three
   plots: `dia`, `dryo`, `various`).
2. **Ground-truth labels** in `$DATASET/labels/` (YOLO-normalized `.txt`, CVAT
   classes `bumblebee/fly/butterfly/other/unsure`). 430 annotated flies in
   total. Fly is the only class with enough vetted ground truth, so the curve is
   fly-only.
3. **Trained models** (paths relative to your model store):
   - YOLO26n detector, e.g. `iter3_3class_plot_stratified/stage2_finetune/weights/best.pt`
   - binary insect/background gate: EfficientNet checkpoint
   - group classifier: InsectNet checkpoint

## Pipeline

### Stage 1: run the real pipeline, capture raw predictions
`combined_pipeline_eval.py` invokes the actual deployed inference
(`python -m pollinator.workflows.inference`) once per plot, at deliberately low
capture thresholds so every candidate is retained for later re-thresholding:

- `--infer-yolo-conf 0.05`, `--infer-binary-thr 0.05`
- `--slice-size 640`, `--overlap 0.2`, `--merge-iou 0.3`

Output: per-plot prediction files in `PRED_DIR`: `dia_results.json`,
`dryo_results.json`, `various_results.json`.

Each detection record holds `bbox`, `source` (`yolo` / `preprocessing` /
`both`), `yolo_confidence`, `insectnet_class`, `binary_confidence`. Capturing at
0.05 is what makes the later threshold sweep possible without re-running
inference.

### Stage 2: sweep thresholds, produce curve data
`sweep_operating_curve.py` reads the three `*_results.json` from `PRED_DIR`, the
ground-truth labels, and image sizes. For each YOLO confidence in
`[0.05 .. 0.50]` it rebuilds the YOLO-only and combined fly detections (binary
gate held at 0.20), greedy-IoU-matches them to ground truth at **IoU 0.50**, and
computes fly **recall** and **false-positive count**. It also sweeps the crop
branch over its own binary gate. Output: `operating_curve.json`.

### Stage 3: render the figure
`make_yolo_figures.py`, function `operating_curve()`, reads
`OPERATING_CURVE_JSON` and draws the three curves plus the deployed-point ring.
Figures land in `OUT_DIR` (default `./figures/`).

## Chain

```
images + labels + models
  -> combined_pipeline_eval.py   (calls pollinator.workflows.inference, per plot, conf 0.05)
  -> PRED_DIR/{dia,dryo,various}_results.json
  -> sweep_operating_curve.py    (re-threshold + IoU-match to ground truth)
  -> operating_curve.json
  -> make_yolo_figures.py :: operating_curve()
  -> figures/yolo_operating_curve.png
```

## Parameters baked into the numbers

- Match criterion: **IoU 0.50**. Class: **fly only**.
- Binary gate held at **0.20** for the YOLO/combined curves; the crop curve
  sweeps the gate (0.05..0.50).
- X-axis "false positives" = predicted fly boxes that match no ground-truth fly.
- Stages 2 and 3 are pure post-processing on the stored JSON, so the curve can
  be regenerated without re-running inference.

## Regenerating

The predictions are vendored, so Stage 1 is only needed if models changed.
Stages 2 and 3 run as-is.

```fish
# Stage 1 (slow, only if predictions are missing or models changed).
# Images, labels, pipeline-root and output default via paths.py; only the
# model checkpoints are required.
uv run python combined_pipeline_eval.py \
    --yolo-model  /path/to/best.pt \
    --binary-model /path/to/efficientnet_binary.pth \
    --group-model  /path/to/insectnet_group.pth \
    --plots dia dryo various

# Stages 2 + 3 (fast, pure post-processing on the vendored predictions)
uv run --with pillow python sweep_operating_curve.py
uv run --with matplotlib --with pillow python make_yolo_figures.py

# Qualitative panels (need the large image set; default to the thesis repo)
uv run --with matplotlib --with pillow python gen_failure_panel.py
uv run --with matplotlib --with pillow python build_failure_grid.py
```

## Consistency note

The curve is end-to-end on the real pipeline output (it runs the actual
`pollinator.workflows.inference`), so it agrees with the combined-pipeline
results table and the complementarity figure, which are computed from the same
`PRED_DIR/*_results.json`.

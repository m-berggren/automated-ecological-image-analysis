import os
from collections import defaultdict

from seed_src.train import train_model
from seed_src.utils import load_model, run_sahi
from seed_src.metrics import calculate_tp_fp_fn


# -------------------------
# TRAIN
# -------------------------
train_results = train_model()
best_model_path = os.path.join(train_results.save_dir, "weights/best.pt")

# -------------------------
# LOAD MODEL
# -------------------------
model = load_model(best_model_path)

# -------------------------
# LOAD DATA
# -------------------------
VAL_DIR = "data/seed/val"

image_paths = []

for species in os.listdir(VAL_DIR):
    species_dir = os.path.join(VAL_DIR, species, "images")

    for img in os.listdir(species_dir):
        image_paths.append((species, os.path.join(species_dir, img)))

# -------------------------
# RESULTS STORAGE
# -------------------------
results = defaultdict(lambda: {
    "total_error": 0,
    "total_gt": 0,
    "images": 0,
    "tp": 0,
    "fp": 0,
    "fn": 0
})

# -------------------------
# LOOP
# -------------------------
for species, img_path in image_paths:

    gt_boxes = load_ground_truth(img_path)

    result = run_sahi(img_path, model)

    preds = []
    for pred in result.object_prediction_list:
        b = pred.bbox
        preds.append([b.minx, b.miny, b.maxx, b.maxy])

    tp, fp, fn = calculate_tp_fp_fn(preds, gt_boxes, iou_threshold=0.4)

    detected = len(preds)
    expected = len(gt_boxes)
    diff = detected - expected

    results[species]["total_error"] += abs(diff)
    results[species]["total_gt"] += expected
    results[species]["images"] += 1
    results[species]["tp"] += tp
    results[species]["fp"] += fp
    results[species]["fn"] += fn

# -------------------------
# RESULTS
# -------------------------
print("\n==== PER SPECIES RESULTS ====\n")

for species, r in results.items():
    mae = r["total_error"] / r["images"] if r["images"] > 0 else 0

    print(f"{species}:")
    print(f"  Images: {r['images']}")
    print(f"  MAE: {mae:.2f}")
    print(f"  TP: {r['tp']} | FP: {r['fp']} | FN: {r['fn']}")
    print("-" * 30)
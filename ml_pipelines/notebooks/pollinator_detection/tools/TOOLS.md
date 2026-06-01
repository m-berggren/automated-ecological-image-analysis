# Helper scripts

Tools for three tasks: **triage** (picking interesting frames), **labeling** (assigning
class labels to crops), and **data preparation** (downloading web images, flattening
folder structures).

---

## Quick reference

| Script | Platform | Task | Run as |
|--------|----------|------|--------|
| `frame_flag_mac.py` | macOS | Browse camera folders and flag frames | `python3 frame_flag_mac.py` |
| `feh-triage.sh` | Linux | Same as above using `feh` viewer | `./feh-triage.sh` |
| `_feh-action.sh` | Linux | Helper called by feh-triage.sh — do not run directly | — |
| `crop_labeler.py` | Any | Label extracted crops with class keys | `python3 crop_labeler.py` |
| `relabel.py` | Any | Correct existing labeled crops / review inference output | `python3 relabel.py` |
| `download_web_images.py` | Any | Download iNaturalist reference images | `python3 download_web_images.py` |
| `flatten-jpg.sh` | Any | Flatten nested JPG folders into one flat dir | `bash flatten-jpg.sh` |
| `flags_all.json` | — | Exported frame flags data file | — |

---

## Common workflows

### Triage — find interesting frames before preprocessing

**macOS:**
```bash
python3 tools/triage/frame_flag_mac.py path/to/camera_folder
```
A Finder dialog opens to pick a destination folder. Press `m` to mark frames, `Esc` to
quit. On exit, the marked frames **plus 2 context frames before and after each one** are
copied to the destination. The context frames ensure the preprocessing pipeline has a
prior frame to diff against. A `flags_all.json` file is also saved with all marked paths.

**Linux:**
```bash
./tools/triage/feh-triage.sh path/to/camera_folder
```
Press `f` to flag, `q` to quit. Output: `flagged.txt` inside the camera folder.

### Labeling — assign classes to raw crops

After running `infer_cropbased.ipynb` in `MODE = 'preprocess'`, point `crop_labeler.py`
at the extracted crops:

```bash
python3 tools/labeling/crop_labeler.py \
    --results path/to/crop_results/run_name/camera_name \
    --output  path/to/data/training/annotated_crops
```

Keys: `b` = background · `1` = bumblebee · `2` = fly · `3` = butterfly · `4` = other ·
`u` = unsure · `Q` = quit & save.

### Label crops after inference — primary workflow

After running `infer_cropbased.ipynb`, use `crop_labeler.py` to review and label crops.
It shows the original source frame with bounding boxes so you can verify each detection
in context, and records progress in a JSON file so you can quit and resume at any time.

```bash
python3 tools/labeling/crop_labeler.py \
    --results path/to/outputs/inference/crop_results/run_01 \
    --output  path/to/data/training/annotated_crops
```

Crops are **moved** (not copied) into `annotated_crops/{dataset_name}/{class}/` as you label them.
The predicted class from `results.csv` is shown as a default label for each crop.

### Fix uncertain predictions — active-learning loop (future use)

`experiments/training/prepare_retrain.ipynb` pre-filters crops by confidence threshold
before labeling — only uncertain predictions (below `CONF_THRESHOLD_LOW`) are queued
for review; high-confidence ones are skipped entirely.

**This workflow requires a trustworthy model.** When confidence scores are unreliable
(e.g. early-stage or poorly-performing models), confidence-based filtering is
meaningless — low-confidence predictions are not necessarily wrong, and
high-confidence ones are not necessarily right. In that case, skip this notebook and
label all crops directly with `crop_labeler.py`.

See [§ prepare_retrain vs crop_labeler](#prepare_retrain-vs-relabel) for when each fits.

### Download extra web images (group classifier only)

```bash
python3 tools/data_prep/download_web_images.py
```

### Flatten a nested camera folder structure

```bash
bash tools/data_prep/flatten-jpg.sh source_dir dest_dir          # symlinks (fast)
bash tools/data_prep/flatten-jpg.sh --copy source_dir dest_dir   # real copies
```

---

## Script reference

### `frame_flag_mac.py` — macOS frame triage

**Purpose:** Browse all images in a camera folder as a fast slideshow, mark frames
that look like they might contain an insect, and **copy the marked frames (plus their
surrounding context frames) to a destination folder** of your choice.

**When to use:** Before running the preprocessing pipeline. Flagging interesting frames
first lets you do targeted labeling runs instead of processing everything. The copy step
lets you hand off a focused set of frames without touching the original camera folder.

**How it works:**

1. At startup, two Finder dialogs open: one to pick the image root folder (if not given
   on the command line), and one to pick the **destination folder** where copies will go.
2. You browse the slideshow and press `m` to mark frames.
3. When you press `Esc` to quit, all marked frames **plus N frames before and after each
   one** are copied to `{destination}/{camera_name}_{timestamp}/`, preserving the
   per-camera folder structure. N is controlled by `--context-frames` (default `2`).

The context frames are included so the preprocessing pipeline has enough preceding frames
to build a rolling background — without them, the marked frame would be diffed against
nothing and produce no detections.

**Usage:**
```bash
python3 tools/triage/frame_flag_mac.py                                 # opens Finder pickers for both folders
python3 tools/triage/frame_flag_mac.py path/to/camera/folder          # skip image-root picker; destination picker still opens
python3 tools/triage/frame_flag_mac.py --export-dir /path/to/dest     # set destination on command line (no picker)
python3 tools/triage/frame_flag_mac.py --context-frames 2             # copy 2 frames before and after each marked frame
python3 tools/triage/frame_flag_mac.py --interval 0.05                # faster slideshow (50 ms/frame)
python3 tools/triage/frame_flag_mac.py --export-name my_session       # name the output subfolder
```

**Controls:**

| Key | Action |
|-----|--------|
| `m` | Mark current frame |
| `u` | Unmark current frame |
| `Space` / `h` | Pause / resume slideshow |
| `a` / `←` | Previous image |
| `d` / `→` | Next image |
| `n` | Next camera folder |
| `b` | Previous camera folder |
| `Esc` | Quit, save flags, and copy marked frames to destination |

**Output:**
- `flags_all.json` — full list of all ever-marked frame paths (persists across sessions)
- `{destination}/{camera_name}_{timestamp}/` — copies of marked frames + context frames

> Uses osascript for the folder picker (not tkinter) — tkinter + OpenCV crash together
> on macOS. Works on macOS only.

---

### `feh-triage.sh` + `_feh-action.sh` — Linux frame triage

**Purpose:** Same as `frame_flag_mac.py` but for Linux, using the `feh` image viewer.

**Requirements:** `feh` must be installed (`sudo apt install feh`).

**Usage:**
```bash
./tools/triage/feh-triage.sh path/to/camera/folder
```

**Controls:** `f` = flag, `u` = unflag. All other `feh` defaults (space, arrows, q) work normally.

**Output:** A `flagged.txt` file inside the camera folder. The script automatically
resumes from the last flagged frame if you quit and re-run.

`_feh-action.sh` is called internally by `feh-triage.sh` — do not run it directly.

---

### What happens after triage?

```
Camera folder images
      ↓  (triage: frame_flag_mac.py or feh-triage.sh)
Flagged frame list (JSON or flagged.txt)
      ↓  (preprocessing in infer_cropbased.ipynb → MODE = 'preprocess')
Extracted candidate crops in crop_results/{run_name}/crops/
      ↓  (labeling: crop_labeler.py)
Labeled crops in annotated_crops/{dataset_name}/{class}/
      ↓  (training or retraining)
```

---

### `crop_labeler.py` — interactive crop labeling

**Purpose:** Interactive OpenCV GUI for assigning class labels to extracted crops.
Shows the full camera frame at the top (with numbered bounding boxes) and a strip of
crops at the bottom.

**When to use:**
- **Initial labeling:** after running `infer_cropbased.ipynb` in preprocessing mode
- **Retraining labeling:** after running `prepare_retrain.ipynb` to select low-confidence crops

**Usage:**
```bash
python3 tools/labeling/crop_labeler.py \
    --results path/to/crops_to_label \
    --output  path/to/annotated_crops
```

The `--output` folder will have the standard class structure:
```
annotated_crops/
  background/  bumblebee/  fly/  butterfly/  other/  unsure/
```

**Controls:**

| Key | Action |
|-----|--------|
| `←` / `a` | Previous image |
| `→` / `d` | Next image |
| `↑` / `↓` | Scroll crop strip |
| `b` | Label: **background** |
| `1` | Label: **bumblebee** |
| `2` | Label: **fly** |
| `3` | Label: **butterfly** |
| `4` | Label: **other** |
| `u` | Label: **unsure** |
| `R` | Toggle image-nav / crop-nav mode |
| `C` | Clear all labels in current image |
| `P` | Preview selected crop fullscreen |
| `Q` | Quit and save |

**Two navigation modes:** `IMAGE_NAV` (default) — label keys apply to all unlabeled
crops in the current image at once. `CROP_NAV` (press `R`) — arrow keys step through
individual crops one at a time.

---

### `relabel.py` — at-a-glance grid browser for labeled crops

> **Note:** `relabel.py` is currently slow to load and navigate, especially on large
> crop sets. **`crop_labeler.py` is the recommended primary labeling tool** — it shows
> frame context and tracks progress per camera. Use `relabel.py` when you want a quick
> visual scan of an entire class folder as thumbnails (e.g. to spot obvious outliers),
> not as the main labeling workflow.

Two modes depending on whether you pass `--dest`:

#### Correct mode (no `--dest`) — fix labels in `annotated_crops/`

Browse crops already organised into class subfolders and move mislabelled ones to the
right class.

```bash
python3 tools/labeling/relabel.py --labeled path/to/data/training/annotated_crops
```

#### Review mode (`--dest`) — turn inference output into training data

After `infer_cropbased.ipynb` Cell 8 (organise crops by class), correct predictions and
copy confirmed crops into `annotated_crops/`.

```bash
python3 tools/labeling/relabel.py \
    --labeled path/to/crop_results/run_01/camera_A/crops \
    --dest    path/to/data/training/annotated_crops
```

- Press a key to copy the selected crop to `dest/{class}/`.
- The original inference output is not deleted.
- Progress is tracked in `reviewed.txt` inside `--labeled` — safe to quit and resume.
- Run once per camera folder.

#### Controls (both modes)

| Key / Action | Effect |
|---|---|
| Click folder (sidebar) | Switch to that class |
| Click crop (grid) | Select it |
| `b` | Send to **background** |
| `1` | Send to **bumblebee** |
| `2` | Send to **fly** |
| `3` | Send to **butterfly** |
| `4` | Send to **other** |
| `u` | Send to **unsure** |
| `a` / `←` | Previous crop |
| `d` / `→` | Next crop |
| `w` / `s` | Previous / next folder |
| Mouse wheel | Scroll grid |
| `q` / `Esc` | Quit (progress saved) |

---

### <a name="prepare_retrain-vs-relabel"></a>`prepare_retrain.ipynb` vs `crop_labeler.py` — when to use which

| | `prepare_retrain.ipynb` + `crop_labeler.py` | `crop_labeler.py` directly |
|---|---|---|
| **When** | Model confidence scores are trustworthy | Model is unreliable / early-stage |
| **What it does** | Filters to low-confidence crops only; high-confidence ones are skipped | Labels all crops from scratch |
| **Benefit** | Only review the uncertain fraction — saves time on large runs | Ensures every crop is human-verified |
| **Prerequisite** | Model must already be reasonably accurate | None |

**Active-learning round (once the model is trustworthy):**
```
infer_cropbased.ipynb
        ↓
prepare_retrain.ipynb   ← filters to low-confidence crops only
        ↓                  high-confidence predictions go straight to retrain unchanged
crop_labeler.py  --results retrain_review/  --output annotated_crops/
        ↓
retrain_cropbased.ipynb
```

**Current recommended workflow (model not yet trustworthy):**
```
infer_cropbased.ipynb
        ↓
crop_labeler.py  --results crop_results/run_XX/  --output annotated_crops/
  ← label every crop; ignore predicted confidence
        ↓
retrain_cropbased.ipynb  (or train_binary_group.ipynb from scratch)
```

Note: `CONF_THRESHOLD_HIGH` in `prepare_retrain.ipynb` (default 0.95) controls what
counts as "confident enough to skip". Crops above this threshold are excluded from the
review set and go directly into retraining as-is. Setting `FORCE_ALL = True` disables
all thresholds and queues every crop — equivalent to bypassing `prepare_retrain` entirely.

---

### `download_web_images.py` — iNaturalist reference images

**Purpose:** Downloads research-grade insect photos from iNaturalist (Sweden + Norway)
into `data/training/web_images/`. Each run creates a new timestamped batch folder:

```
data/training/web_images/
├── batch_initial/               ← first download (moved from flat layout)
│   ├── bumblebee/
│   ├── fly/
│   ├── butterfly/
│   └── other/
└── batch_20260529_143000/       ← second download (new images only)
    ├── bumblebee/
    └── ...
```

**When to use:** To supplement `annotated_crops/` with extra web images for both
classifiers:
- **Group / 5-class classifier**: use directly, each class as-is.
- **Binary classifier**: all classes count as `insect` — set `USE_WEB_FOR_BINARY = True`
  in `train_binary_group.ipynb` or `retrain_cropbased.ipynb` (enabled by default).

**Usage:**
```bash
python3 tools/data_prep/download_web_images.py
```

Just run it — no flags needed. Each run automatically creates a new `batch_YYYYMMDD_HHMMSS/`
folder. Dedup is cross-batch: photo IDs already present in **any** existing batch folder
are skipped, so you never re-download images from a previous round.

> **`batch_initial/` limitation.** The original images were downloaded before the batch
> system existed and use an old naming scheme (`{taxon}_{place}_{counter}.jpg`) that
> contains no photo ID. The dedup check cannot see them, so a small number may be
> re-downloaded into a new batch. This is a minor disk-space inefficiency — training
> correctness is unaffected because `WEB_BATCHES` lets you pick exactly which batches
> to include. If you want a clean slate, delete `batch_initial/` and re-run this script.

To download more images for a class, increase the `n=` count for the relevant taxon at the
bottom of the script and re-run. Only genuinely new photos are fetched.

**Choosing which batches to use for training** — set `WEB_BATCHES` in the training notebook:
```python
WEB_BATCHES = []                           # all batches (default)
WEB_BATCHES = ['batch_20260529_143000']    # only this batch (e.g. for retrain on new data only)
```

**iNaturalist taxon IDs used** (verify at `https://www.inaturalist.org/taxa/<id>`):

| Class | Taxon | ID | Place IDs |
|-------|-------|----|-----------|
| `bumblebee` | *Bombus* (genus) | **52775** | Sweden 7599, Norway 7016 |
| `fly` | Diptera (order) | **47822** | Sweden 7599, Norway 7016 |
| `butterfly` | Lepidoptera (order) | **47157** | Sweden 7599, Norway 7016 |
| `other` | Coleoptera (beetles) | **47208** | Sweden 7599, Norway 7016 |
| `other` | Hymenoptera (wasps, ants) | **47201** | Sweden 7599, Norway 7016 |
| `other` | Hemiptera (true bugs) | **47744** | Sweden 7599, Norway 7016 |

> Hymenoptera (47201) is used for **other**. *Bombus* (52775) is downloaded separately
> for **bumblebee** — no overlap.

Edit the `TAXON_*` constants at the top of the script to change taxon IDs, counts, or
place IDs. Requires `pip install requests`.

---

### `flatten-jpg.sh` — flatten nested JPG folders

**Purpose:** Recursively finds all `.jpg`/`.jpeg` files under a source directory and
creates symlinks (or copies) in a single flat output folder. Subfolder paths are encoded
into filenames using `__` so files from different cameras never collide.

**When to use:** Some cameras produce deeply nested `DCIM/` subfolders. The pipeline
expects leaf directories containing JPG files — this script flattens the hierarchy.

**Usage:**
```bash
bash tools/data_prep/flatten-jpg.sh source_dir dest_dir            # symlinks (instant, no disk use)
bash tools/data_prep/flatten-jpg.sh --copy source_dir dest_dir     # real copies (portable)
bash tools/data_prep/flatten-jpg.sh --help
```

> Default mode creates symlinks. Use `--copy` when the destination will be moved to
> another machine or drive.

---

### `flags_all.json`

Exported frame flags from a past triage session. Format matches the output of
`frame_flag_mac.py`. Can be used to reconstruct which frames were manually identified
as containing insects during the initial data collection phase.

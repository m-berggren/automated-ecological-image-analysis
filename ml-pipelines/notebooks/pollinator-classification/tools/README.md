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

### Review inference results — correct predictions & build training data

After running `infer_cropbased.ipynb` with `MODE = 'infer'` and Cell 8 (organise crops
by class), use `relabel.py` in **review mode**:

```bash
python3 tools/labeling/relabel.py \
    --labeled path/to/crop_results/run_01/camera_A/crops \
    --dest    path/to/data/training/annotated_crops
```

Progress is saved in `reviewed.txt` — quit and resume at any time without re-reviewing.

To fix labels already in `annotated_crops/`, use **correct mode** (no `--dest`):

```bash
python3 tools/labeling/relabel.py --labeled path/to/data/training/annotated_crops
```

### Fix uncertain predictions — active-learning loop

If an inference run produced too many crops to review manually, use
`experiments/training/prepare_retrain.ipynb` to pre-filter by confidence threshold before labeling.
See [§ prepare_retrain vs relabel](#prepare_retrain-vs-relabel) for when each fits.

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
Labeled crops in annotated_crops/{class}/
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

### `relabel.py` — correct labels or review inference output

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

### <a name="prepare_retrain-vs-relabel"></a>`prepare_retrain.ipynb` vs `relabel.py` — when to use which

| | `prepare_retrain.ipynb` | `relabel.py` (review mode) |
|---|---|---|
| **Input** | A completed inference run (`crop_results/`) | An organised `crops/` folder (from Cell 8) |
| **What it does** | Reads `results.csv`, selects low-confidence crops, copies them to `retrain_review/` | GUI to correct predictions and copy crops to `annotated_crops/` |
| **When to use** | Thousands of inference crops — only review uncertain ones | Review crops visually (all, or pre-filtered set from `prepare_retrain`) |
| **Output** | `retrain_review/{class}/` | `annotated_crops/{class}/` |

**Typical active-learning round:**
```
infer_cropbased.ipynb  →  Cell 8 (organise by class)
                       ↓
      [OPTIONAL] prepare_retrain.ipynb   ← filter by low confidence
                       ↓
      relabel.py --labeled crops/ --dest annotated_crops/
                       ↓
      retrain_cropbased.ipynb
```

If your run has fewer than ~300 crops, skip `prepare_retrain` and go straight to `relabel.py`.

---

### `download_web_images.py` — iNaturalist reference images

**Purpose:** Downloads research-grade insect photos from iNaturalist for Sweden and
Norway into `data/web_images/{class}/`.

**When to use:** To supplement `annotated_crops/` with extra web images for both
classifiers:
- **Group / 5-class classifier**: use directly, each class as-is.
- **Binary classifier**: all classes count as `insect` — set `USE_WEB_FOR_BINARY = True`
  in `train_binary_group.ipynb` or `retrain_cropbased.ipynb` (enabled by default).

**Usage:**
```bash
python3 tools/data_prep/download_web_images.py
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

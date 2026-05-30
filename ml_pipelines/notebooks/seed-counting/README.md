# Seed Counting Notebooks

This directory contains the original prototyping Jupyter notebooks used to develop the seed module pipeline.

> **Note:** These notebooks have been converted into standard Python modules inside [`../../seed_src/`](../../seed_src/). For production or offline evaluation, use those scripts instead.

## Notebooks Overview

* **`main.ipynb`**: The original scratchpad for the YOLO-OBB SAHI inference loop and training orchestration. This was eventually refactored and split into the [`ml_pipelines/main.py`](../../main.py) orchestrator and several scripts inside subdirectories of `ml_pipelines/seed_src/`.
* **`label-extractor.ipynb`**: The prototyping environment for the EasyOCR pipeline used to read handwritten species labels from image margins. This has been refactored into [`seed_src/utils/label_extractor.py`](../../seed_src/utils/label_extractor.py).

## Usage
It is recommended to run training and inference via the Python files, as they include critical updates to the seed module pipeline. However, if you are running the Jupyter notebooks via Google Colab, ensure you mount your Google Drive and adjust the paths to point to your `data/seed/` directory. If running the notebooks locally, you must install the Jupyter dependencies from the main `pyproject.toml` / `uv.lock`.
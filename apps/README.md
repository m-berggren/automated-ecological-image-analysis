# Engineering Thesis Project

Automated ecological image analysis tool built with Django, Vue.js, and PyTorch.

## Architecture

Three layers, each with a single responsibility:

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Frontend | `frontend/` | Vue SPA. Upload, review, training, and results pages. Talks to the backend over the REST API only. |
| Backend | `apps/`, `config/` | Django + DRF. Owns the database, the REST API, and orchestration. Runs inference and training in background threads. |
| ML core | `ml-pipelines/` | Framework-agnostic PyTorch / YOLO code. No Django imports. Consumed by the backend at runtime and by the Colab notebooks for research. |

The backend never embeds model code; it imports `ml-pipelines` and drives it.
The same `ml-pipelines` functions are called by both the Django worker and the
notebooks, so research and production share one implementation.

### Directory map

```
apps/                Django apps
  accounts/            auth
  datasets/            ImageAsset, Upload (ingest + storage)
  analysis/            cross-cutting models: Detection, InferenceRun,
                       ModelVersion, TrainingJob; crops; model-file storage
  pollinator/          pollinator module: inference + training orchestration,
                       training-pool endpoints, dual-detector merge
config/              Django settings, URLs, ASGI/WSGI
frontend/            Vue 3 + TypeScript SPA
ml-pipelines/        ML core (see ml-pipelines/README.md)
  pollinator/          library consumed by the backend + notebooks
  seed_src/            standalone seed-detection pipeline (script-driven)
  notebooks/           Colab research notebooks
data/, media/        datasets and uploaded/generated files
```

### Data flow (pollinator module)

1. Images are uploaded and stored as `ImageAsset` rows (`datasets`).
2. An `InferenceRun` is started; a background thread drives
   `PollinatorInferencePipeline` over the images one at a time, writing
   `Detection` rows and per-detection crops (`analysis` + `pollinator`).
3. A reviewer corrects detections in the UI (sets `reviewer_label`).
4. Reviewed detections feed a `TrainingJob`, which calls into
   `ml-pipelines` to retrain and produces a new `ModelVersion`.
5. Activating that `ModelVersion` makes the next `InferenceRun` use it.

The single inference loop lives in the backend worker
(`apps/pollinator/services.py`), not in the ML library; the library exposes a
stateful per-image step (`prime()` once, then `process_image()` per frame).

## Documentation

| Area | Doc |
|------|-----|
| ML core overview | [ml-pipelines/README.md](ml-pipelines/README.md) |
| Pollinator pipeline | [ml-pipelines/pollinator/README.md](ml-pipelines/pollinator/README.md) |
| Seed pipeline | [ml-pipelines/seed_src/README.md](ml-pipelines/seed_src/README.md) |
| Frontend | [frontend/README.md](frontend/README.md) |
| Backend apps | [apps/README.md](apps/README.md) |
| Backend core (models, runs, training) | [apps/analysis/README.md](apps/analysis/README.md) |
| Backend pollinator module | [apps/pollinator/README.md](apps/pollinator/README.md) |
| Research notebooks | `ml-pipelines/notebooks/` (planned) |

## Prerequisites

### uv (required)

Python package manager, using it instead of pip. Install with one of:

- `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `pip install uv`
- `brew install uv` (macOS)

### Node.js 24 (required)

Install with one of:

- `mise install` (if you use [mise](https://mise.jdx.dev))
- [Download from nodejs.org](https://nodejs.org)
- `brew install node` (macOS)

## Setup

```bash
git clone <repo-url>
cd engineering-thesis-project

# Python dependencies
uv sync

# Frontend dependencies
cd frontend && npm install && cd ..

# Database
uv run python manage.py migrate
```

## Development

Run both in separate terminals:

```bash
# Django server
uv run python manage.py runserver

# Vue dev server (hot reload)
cd frontend && npm run dev
```

Open http://localhost:8000 to view the application. The Vue dev server on port 5173 is only used for isolated frontend development with hot reload.

## Formatting & Linting

```bash
# Python
uv run ruff format .
uv run ruff check .

# Django templates
uv run djlint templates/ --reformat

# Frontend (Vue/TS)
cd frontend && npm run format
npm run type-check
```

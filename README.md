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

## Docker (production-style stack)

A three-service Compose stack: Postgres, the Django API on gunicorn, and nginx
serving the built Vue SPA while reverse-proxying `/api`, `/admin`, `/media`, and
`/static` to the backend. Single origin, so no CORS. Uses `config.settings.production`.

```bash
cp .env.example .env          # then edit SECRET_KEY, SQL_PASSWORD, etc.
docker compose up --build     # open http://localhost:8080
```

The backend container runs migrations and `collectstatic` on startup. State
persists in named volumes:

| Volume | Mount | Holds |
|--------|-------|-------|
| `postgres_data` | db `/var/lib/postgresql/data` | database |
| `media_data` | backend `/app/media` (nginx ro) | pollinator/analysis runs, crops, model files, training output |
| `data_store` | backend `/app/data` | seed module datasets, labels, weights |
| `static_data` | backend `/app/staticfiles` (nginx ro) | collected admin/DRF static |
| `model_cache` | backend `/app/.cache` | torch / EasyOCR / Ultralytics / cloud-model weights |

**Storage grows unbounded.** A pollinator run of 10k images is roughly 16 GB of
source images plus ~6 GB of crops, stored once under
`media/runs/<module>/<run_id>/`. Nothing caps or auto-prunes this; the only
reclaim is deleting a run (`DELETE /api/analysis/runs/<id>/`, which removes its
images and crops). Size `media_data`'s host disk accordingly and prune old runs.

Create an admin user once the stack is up:

```bash
docker compose exec backend python manage.py createsuperuser
```

### Demo data (optional)

To start with real, browsable data instead of an empty app, set `IMPORT_DEMO=true`
in `.env`. On first boot the entrypoint downloads the demo bundle and model
weights from the URLs in [demo_assets/sources.json](demo_assets/README.md) (or
uses a local `demo_assets/demo_bundle.zip` if mounted), idempotently. If no
superuser exists, a default `admin` / `admin123` is created (override via the
`DJANGO_SUPERUSER_*` env vars; change it for any non-local deployment). Locally,
without Docker: `uv run python manage.py import_demo`.

Notes:

- torch / torchvision are pinned to the **CPU** wheels in `pyproject.toml`
  (`[tool.uv.sources]`), which keeps the image small and GPU-free. This also
  applies to a local `uv sync`. For local GPU work, point the `pytorch-cpu`
  index at a CUDA channel (e.g. `.../whl/cu124`) and re-lock.
- The container builds a standalone SPA (`BUILD_TARGET=standalone`); the default
  `npm run build` still emits the `static/vue` manifest for Django integration.

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

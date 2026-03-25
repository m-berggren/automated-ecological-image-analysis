# Engineering Thesis Project

Automated ecological image analysis tool built with Django, Vue.js, and PyTorch.

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

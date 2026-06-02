# syntax=docker/dockerfile:1

# ── Builder: resolve and install the locked dependencies into /app/.venv ─────
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# The project is a non-packaged ("virtual") Django app, so only the dependency
# metadata is needed to build the venv. Copy it first for layer caching.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group prod

# ── Runtime: slim image with just the venv, source, and OpenCV's shared libs ─
FROM python:3.13-slim

# libgl1 + libglib2.0-0 are required by opencv-python at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    TORCH_HOME=/app/.cache/torch \
    EASYOCR_MODULE_PATH=/app/.cache/easyocr \
    YOLO_CONFIG_DIR=/app/.cache/ultralytics \
    AEA_MODEL_CACHE=/app/.cache/aea-models

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . .

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]

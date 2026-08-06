"""Model-file storage abstraction.

ModelVersion.model_file_path stores a URI rather than always a raw filesystem
path. Local paths and file:// URIs are returned as-is; cloud-scheme URIs
(s3://, gs://) are downloaded into a local cache directory on first call and
the cached path returned thereafter. This keeps inference/training callers
unaware of where the actual bytes live.

Backends are imported lazily so a local deployment doesn't need boto3 or
google-cloud-storage installed.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)


def model_dir(module: str, model_version_id: int) -> Path:
    """Canonical directory for a model version's files.

    Layout: MEDIA_ROOT/models/<module>/<model_version_id>/ with weights<ext>
    at the root and artifact files under artifacts/. Every model — uploaded
    by hand or produced by a training job — lives here so the upload view,
    training jobs, and future ingest paths stay in sync.
    """
    return Path(settings.MEDIA_ROOT) / 'models' / module / str(model_version_id)


def weights_path(module: str, model_version_id: int, ext: str) -> Path:
    """Canonical absolute path for a model version's weights file.

    `ext` is the original checkpoint suffix (e.g. '.pt', '.pth') with or
    without the leading dot.
    """
    if not ext.startswith('.'):
        ext = f'.{ext}'
    return model_dir(module, model_version_id) / f'weights{ext}'


def move_weights_into_place(
    src: Path, module: str, model_version_id: int, ext: str
) -> Path:
    """Move `src` to the canonical weights location and return that path.

    Uses shutil.move so cross-device moves (tempdir on a separate mount from
    MEDIA_ROOT) work without leaving the source behind.
    """
    dst = weights_path(module, model_version_id, ext)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst


def link_or_copy(src: Path, dst: Path) -> None:
    """Materialise `src` at `dst` cheaply.

    Tries a hardlink first (instant, zero disk cost) and falls back to a
    full copy when the two paths live on different filesystems — typical
    when a system tempdir lives on a separate mount from MEDIA_ROOT.
    Idempotent: if `dst` already exists the link/copy is skipped.
    """
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:  # pragma: no cover
        shutil.copy2(src, dst)


# Where downloaded cloud-backed model files are cached on the local machine.
# Override with AEA_MODEL_CACHE if the default isn't writable.
_DEFAULT_CACHE = '/var/cache/aea-models'
_MODEL_CACHE = Path(os.environ.get('AEA_MODEL_CACHE', _DEFAULT_CACHE))


def resolve_model_path(uri: str) -> Path:
    """Return a local filesystem path for a model file referenced by `uri`.

    Supported schemes:
      - No scheme or `file://`: treated as a local path, returned as-is.
      - `s3://bucket/key`: downloaded via boto3 to the local cache.
      - `gs://bucket/key`: downloaded via google-cloud-storage to the local cache.

    Downloads are cached: the first call fetches, subsequent calls reuse.
    The cache directory is `/var/cache/aea-models` by default; override with
    the AEA_MODEL_CACHE env var (useful in containers without root access).

    Raises ValueError on unknown schemes. Raises whatever the backend client
    raises on auth/network failures.
    """
    parsed = urlparse(uri)
    scheme = parsed.scheme

    if scheme in ('', 'file'):
        return Path(parsed.path) if scheme == 'file' else Path(uri)

    _MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    key = parsed.path.lstrip('/')
    cached = _MODEL_CACHE / parsed.netloc / key
    if cached.exists():
        logger.debug(f'Reusing cached model: {cached}')
        return cached
    cached.parent.mkdir(parents=True, exist_ok=True)

    if scheme == 's3':  # pragma: no cover
        logger.info(f'Downloading s3://{parsed.netloc}/{key} -> {cached}')
        import boto3

        boto3.client('s3').download_file(parsed.netloc, key, str(cached))
    elif scheme == 'gs':  # pragma: no cover
        logger.info(f'Downloading gs://{parsed.netloc}/{key} -> {cached}')
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(parsed.netloc)
        bucket.blob(key).download_to_filename(str(cached))
    else:
        raise ValueError(f'Unsupported model URI scheme: {scheme!r} in {uri!r}')

    return cached

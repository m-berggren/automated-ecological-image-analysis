"""Detector training-dataset upload: validate + stage a user-supplied YOLO zip.

A user can fine-tune the YOLO detector on their own data by uploading a zip
laid out as:

    <root>/
        images/     *.jpg | *.jpeg | *.png
        labels/     *.txt   (YOLO format: "cls cx cy w h", normalised 0-1)
        data.yaml   must contain `names:` (the uploader's class ordering)

The backend is the only trusted gate; never rely on client-side checks.

Rules enforced here:
  - zip-slip and zip-bomb guards before extraction.
  - An image without a matching label is kept as a background/negative
    image (valid YOLO input); a label without a matching image is rejected
    (there is nothing to label).
  - Every class name in the uploader's data.yaml must exist in the target
    model's class list. The uploader's indices are remapped onto the target
    ordering, so a CVAT export whose index 0 means a different class can't
    silently mislabel every box. Unknown class names are rejected outright.

validate_and_stage returns a structured report and, on success, writes a flat
staging dir (images/ + labels/ with remapped indices) under MEDIA_ROOT/tmp.
merge_uploaded_into_dataset later distributes those pairs across train/val/test
with the job's configured split, alongside the DB-derived detections.
"""

from __future__ import annotations

import logging
import secrets
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Optional

import yaml
from django.conf import settings

from apps.analysis.storage import link_or_copy

logger = logging.getLogger(__name__)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}

# Zip-bomb guards: refuse archives that would explode on disk or in the
# member loop. Tuned generously for image datasets; both are cheap to raise.
MAX_ENTRIES = 200_000
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3  # 20 GiB

# Marker used as a dominant-class bucket key for label-free (background)
# images so they get spread across splits like any other class.
_BACKGROUND = '__background__'


class DetectorUploadError(Exception):
    """Hard validation failure that aborts the upload (bad structure, unsafe
    archive, unknown classes). Soft per-line issues are collected into the
    report's `errors` list instead."""


def _staging_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / 'tmp' / 'detector_uploads'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_unsafe_member(name: str) -> bool:
    """True for paths that could escape the extraction dir (zip-slip):
    absolute paths, Windows drive letters, or any `..` segment."""
    if name.startswith('/') or name.startswith('\\'):
        return True
    if len(name) >= 2 and name[1] == ':':  # e.g. C:\...
        return True
    return '..' in PurePosixPath(name).parts


def _open_checked(zip_path: Path) -> zipfile.ZipFile:
    """Open the archive, enforcing entry-count, size, and slip guards before
    any bytes are read out."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise DetectorUploadError(f'not a valid zip archive: {exc}') from exc

    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise DetectorUploadError(
            f'zip has too many entries ({len(infos)} > {MAX_ENTRIES})'
        )
    total = 0
    for info in infos:
        if _is_unsafe_member(info.filename):
            raise DetectorUploadError(f'unsafe path in zip: {info.filename!r}')
        total += info.file_size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise DetectorUploadError('zip exceeds the uncompressed size limit')
    return zf


def _detect_root(infos: list[zipfile.ZipInfo]) -> str:
    """Locate the dataset root by the (single) data.yaml. Tolerates one
    wrapper folder. Returns the prefix ('' for archive root)."""
    yamls = [i.filename for i in infos if PurePosixPath(i.filename).name == 'data.yaml']
    if not yamls:
        raise DetectorUploadError('data.yaml not found in zip')
    if len(yamls) > 1:
        raise DetectorUploadError(
            'multiple data.yaml found; zip must contain exactly one'
        )
    parent = str(PurePosixPath(yamls[0]).parent)
    return '' if parent == '.' else parent


def _read_names(zf: zipfile.ZipFile, root: str) -> list[str]:
    """Parse `names:` from data.yaml into an index-ordered list. Accepts both
    the list form and the {0: 'a', 1: 'b'} index-map form."""
    path = f'{root}/data.yaml' if root else 'data.yaml'
    try:
        doc = yaml.safe_load(zf.read(path).decode('utf-8'))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise DetectorUploadError(f'data.yaml could not be parsed: {exc}') from exc
    if not isinstance(doc, dict) or 'names' not in doc:
        raise DetectorUploadError('data.yaml is missing a names: entry')
    names = doc['names']
    if isinstance(names, dict):
        try:
            names = [names[k] for k in sorted(names, key=lambda k: int(k))]
        except (ValueError, TypeError) as exc:
            raise DetectorUploadError(
                'data.yaml names: index map has non-integer keys'
            ) from exc
    if not isinstance(names, list) or not names:
        raise DetectorUploadError(
            'data.yaml names: must be a non-empty list or index map'
        )
    return [str(n) for n in names]


def _remap_label(
    raw: str, stem: str, remap: dict[int, int], n_their: int, target_classes: list[str]
) -> tuple[list[str], list[str], dict[str, int]]:
    """Validate one label file and rewrite class indices to the target order.
    Returns (output_lines, errors, per-target-class counts)."""
    out: list[str] = []
    errs: list[str] = []
    counts: dict[str, int] = defaultdict(int)
    for ln_no, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        parts = s.split()
        if len(parts) != 5:
            errs.append(f'{stem}.txt line {ln_no}: expected 5 fields, got {len(parts)}')
            continue
        try:
            cls = int(parts[0])
            cx, cy, w, h = (float(v) for v in parts[1:])
        except ValueError:
            errs.append(f'{stem}.txt line {ln_no}: non-numeric token')
            continue
        if cls < 0 or cls >= n_their:
            errs.append(f'{stem}.txt line {ln_no}: class index {cls} out of range')
            continue
        if not all(0.0 <= v <= 1.0 for v in (cx, cy, w, h)):
            errs.append(f'{stem}.txt line {ln_no}: coords must be normalised to [0,1]')
            continue
        our = remap[cls]
        out.append(f'{our} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}')
        counts[target_classes[our]] += 1
    return out, errs, counts


def validate_and_stage(uploaded_file, target_classes: list[str]) -> dict:
    """Validate the uploaded zip against `target_classes` and, on success,
    write a flat staging dir under MEDIA_ROOT/tmp.

    Returns a report dict: {ok, token, staging_dir, image_count,
    background_count, class_histogram, errors}. The staging dir is removed
    unless ok is True. Raises DetectorUploadError on hard (structural) failures.
    """
    token = secrets.token_hex(8)
    root_dir = _staging_root()
    zip_path = root_dir / f'{token}.zip'
    with open(zip_path, 'wb') as fh:
        for chunk in uploaded_file.chunks():
            fh.write(chunk)

    staging = root_dir / token
    try:
        report = _process(zip_path, staging, target_classes, token)
    finally:
        zip_path.unlink(missing_ok=True)
    if not report['ok']:
        _rmtree(staging)
    return report


def _process(
    zip_path: Path, staging: Path, target_classes: list[str], token: str
) -> dict:
    name_to_idx = {c.lower(): i for i, c in enumerate(target_classes)}
    zf = _open_checked(zip_path)
    with zf:
        infos = zf.infolist()
        root = _detect_root(infos)
        names = _read_names(zf, root)

        remap: dict[int, int] = {}
        unknown: list[str] = []
        for their_idx, nm in enumerate(names):
            key = nm.strip().lower()
            if key in name_to_idx:
                remap[their_idx] = name_to_idx[key]
            else:
                unknown.append(nm)
        if unknown:
            raise DetectorUploadError(
                f'data.yaml has classes not in the target model {target_classes}: {unknown}'
            )

        img_prefix = f'{root}/images/' if root else 'images/'
        lbl_prefix = f'{root}/labels/' if root else 'labels/'
        images: dict[str, zipfile.ZipInfo] = {}
        labels: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            if info.is_dir():
                continue
            fn = info.filename
            stem = PurePosixPath(fn).stem
            if (
                fn.startswith(img_prefix)
                and PurePosixPath(fn).suffix.lower() in IMAGE_EXTS
            ):
                images[stem] = info
            elif fn.startswith(lbl_prefix) and fn.lower().endswith('.txt'):
                labels[stem] = info
        if not images:
            raise DetectorUploadError('no images found under images/')

        errors: list[str] = []
        orphans = sorted(set(labels) - set(images))
        if orphans:
            errors.append(
                f'{len(orphans)} label file(s) have no matching image: {orphans[:10]}'
            )

        out_img = staging / 'images'
        out_lbl = staging / 'labels'
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        histogram: dict[str, int] = defaultdict(int)
        n_background = 0
        for stem, info in images.items():
            ext = PurePosixPath(info.filename).suffix.lower()
            (out_img / f'{stem}{ext}').write_bytes(zf.read(info))
            lbl_info = labels.get(stem)
            if lbl_info is None:
                (out_lbl / f'{stem}.txt').write_text('')
                n_background += 1
                continue
            raw = zf.read(lbl_info).decode('utf-8', 'replace')
            lines, line_errs, counts = _remap_label(
                raw, stem, remap, len(names), target_classes
            )
            errors.extend(line_errs)
            for cls, c in counts.items():
                histogram[cls] += c
            (out_lbl / f'{stem}.txt').write_text(
                '\n'.join(lines) + ('\n' if lines else '')
            )

    ok = not errors
    return {
        'ok': ok,
        'token': token if ok else None,
        'staging_dir': str(staging) if ok else None,
        'image_count': len(images),
        'background_count': n_background,
        'class_histogram': dict(histogram),
        'errors': errors,
    }


def staging_dir_for(token: str) -> Optional[Path]:
    """Resolve a staging token to its dir, guarding against path injection.
    Returns None if the token is malformed or the dir is absent."""
    if not token or not all(c in '0123456789abcdef' for c in token):
        return None
    path = _staging_root() / token
    return path if path.is_dir() else None


def merge_uploaded_into_dataset(
    staging_dir: Path, dataset_dir: Path, class_filter: list[str], splits: dict
) -> int:
    """Distribute staged image+label pairs across train/val/test using the
    job's split, writing into dataset_dir alongside the DB-derived data.
    Returns the number of images merged."""
    from .training import _stratified_image_split

    staging_dir = Path(staging_dir)
    src_img = staging_dir / 'images'
    src_lbl = staging_dir / 'labels'

    images_by_dominant: dict[str, list[str]] = defaultdict(list)
    meta: dict[str, tuple[Path, Path]] = {}
    for img_path in sorted(src_img.iterdir()):
        if not img_path.is_file():
            continue
        stem = img_path.stem
        lbl_path = src_lbl / f'{stem}.txt'
        counts: dict[int, int] = defaultdict(int)
        if lbl_path.exists():
            for line in lbl_path.read_text().splitlines():
                line = line.strip()
                if line:
                    counts[int(line.split()[0])] += 1
        dominant = class_filter[max(counts, key=counts.get)] if counts else _BACKGROUND
        images_by_dominant[dominant].append(stem)
        meta[stem] = (img_path, lbl_path)

    train, val, test = _stratified_image_split(images_by_dominant, splits)
    written = 0
    for split, stems in (('train', train), ('val', val), ('test', test)):
        di = dataset_dir / 'images' / split
        dl = dataset_dir / 'labels' / split
        di.mkdir(parents=True, exist_ok=True)
        dl.mkdir(parents=True, exist_ok=True)
        for stem in stems:
            img_path, lbl_path = meta[stem]
            # up_ prefix avoids colliding with the DB path's img_<id> names.
            link_or_copy(img_path, di / f'up_{stem}{img_path.suffix}')
            (dl / f'up_{stem}.txt').write_text(
                lbl_path.read_text() if lbl_path.exists() else ''
            )
            written += 1
    return written


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)

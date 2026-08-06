#!/usr/bin/env python3
"""Build a demo bundle (manifest.json + media) from an existing instance.

Reads the source SQLite database with raw SQL and copies the referenced media
files, so it is decoupled from any particular branch's Django models. The
companion `manage.py import_demo` command rebuilds the rows through the current
ORM and copies the media into the target MEDIA_ROOT.

Model weight files are NOT bundled: they are large and shipped as separate
archives (e.g. one Zenodo file per model). The manifest still records each
model's media-relative `model_file_path` so the seeded rows point at the right
location once the weight archives are restored. This script also writes/updates
`demo_assets/sources.json` with the bundle's checksum and a scaffold for the
weight archive URLs (filled in after upload).

Usage:
    python scripts/export_demo.py --source ../aea-merge-tg78-into-72 --runs 1 2 \
        --out demo_assets/demo_bundle.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

# Dependency order. Each entry maps a source table to the Django model label the
# seed command resolves it against. Order matters: parents before children.
GROUPS: list[tuple[str, str]] = [
    ('analysis_modelversion', 'analysis.ModelVersion'),
    ('analysis_modelartifact', 'analysis.ModelArtifact'),
    ('datasets_upload', 'datasets.Upload'),
    ('datasets_imageasset', 'datasets.ImageAsset'),
    ('analysis_inferencerun', 'analysis.InferenceRun'),
    ('analysis_detection', 'analysis.Detection'),
    ('pollinator_pollinatordetection', 'pollinator.PollinatorDetection'),
]

PLACEHOLDER_URL = 'REPLACE_WITH_ZENODO_URL'


def rows(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def media_rel(path: str) -> str:
    """Reduce an absolute or media-relative path to a MEDIA_ROOT-relative one."""
    marker = '/media/'
    if marker in path:
        return path.split(marker, 1)[1]
    return path.lstrip('/')


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_sources(
    sources_path: Path, bundle_name: str, bundle_md5: str, weight_paths: list[str]
) -> None:
    """Create or update the sources manifest used by import_demo's downloader.

    Preserves any URLs/checksums already filled in on a prior run; only the
    bundle checksum is refreshed, so re-exporting never clobbers links pasted
    after a Zenodo upload. Each weight is fetched directly to its dest path
    (md5 matches the value Zenodo shows for the file).
    """
    existing: dict = {}
    if sources_path.exists():
        existing = json.loads(sources_path.read_text())

    weights = existing.get('weights')
    if not weights:
        weights = [
            {'dest': p, 'url': PLACEHOLDER_URL, 'md5': PLACEHOLDER_URL}
            for p in weight_paths
        ]

    data = {
        'bundle_url': existing.get(
            'bundle_url', f'{PLACEHOLDER_URL}_FOR_{bundle_name}'
        ),
        'bundle_md5': bundle_md5,
        'weights': weights,
    }
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(json.dumps(data, indent=2) + '\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        '--source',
        required=True,
        help='Source project root (holds data/db.sqlite3 + media/)',
    )
    ap.add_argument(
        '--runs', type=int, nargs='+', default=[1, 2], help='InferenceRun ids to export'
    )
    ap.add_argument('--out', default='demo_assets/demo_bundle.zip')
    args = ap.parse_args()

    source = Path(args.source).resolve()
    db_path = source / 'data' / 'db.sqlite3'
    src_media = source / 'media'
    if not db_path.exists():
        print(f'error: {db_path} not found', file=sys.stderr)
        return 1

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    run_ids = args.runs
    placeholders = ','.join('?' * len(run_ids))

    runs = rows(
        cur,
        f'SELECT * FROM analysis_inferencerun WHERE id IN ({placeholders})',
        tuple(run_ids),
    )
    upload_ids = sorted({r['upload_id'] for r in runs if r['upload_id'] is not None})
    up_ph = ','.join('?' * len(upload_ids)) or 'NULL'

    uploads = rows(
        cur, f'SELECT * FROM datasets_upload WHERE id IN ({up_ph})', tuple(upload_ids)
    )
    images = rows(
        cur,
        f'SELECT * FROM datasets_imageasset WHERE upload_id IN ({up_ph})',
        tuple(upload_ids),
    )
    detections = rows(
        cur,
        f'SELECT * FROM analysis_detection WHERE inference_run_id IN ({placeholders})',
        tuple(run_ids),
    )
    det_ids = [d['id'] for d in detections]
    det_ph = ','.join('?' * len(det_ids)) or 'NULL'
    poll = rows(
        cur,
        f'SELECT * FROM pollinator_pollinatordetection WHERE detection_id IN ({det_ph})',
        tuple(det_ids),
    )
    # All model rows are exported as-is from the live DB, so any artifacts the
    # operator deleted upstream are simply absent here.
    modelversions = rows(cur, 'SELECT * FROM analysis_modelversion')
    modelartifacts = rows(cur, 'SELECT * FROM analysis_modelartifact')

    by_table = {
        'analysis_modelversion': modelversions,
        'analysis_modelartifact': modelartifacts,
        'datasets_upload': uploads,
        'datasets_imageasset': images,
        'analysis_inferencerun': runs,
        'analysis_detection': detections,
        'pollinator_pollinatordetection': poll,
    }

    # Collect media files to copy (MEDIA_ROOT-relative). Weights are excluded;
    # they ship as separate archives.
    media_files: set[str] = set()
    for img in images:
        if img.get('file'):
            media_files.add(img['file'])
    for d in detections:
        if d.get('crop'):
            media_files.add(d['crop'])
    for a in modelartifacts:
        if a.get('file'):
            media_files.add(a['file'])

    # Rewrite each model's weight path to a media-relative one. The file itself
    # is not bundled; the path lets the seeded row find the weight once the
    # separate archive is restored.
    weight_paths: list[str] = []
    for mv in modelversions:
        p = mv.get('model_file_path')
        if not p:
            continue
        rel = media_rel(p)
        mv['model_file_path'] = rel
        weight_paths.append(rel)
    weight_paths = sorted(set(weight_paths))

    staging = Path(tempfile.mkdtemp(prefix='demo_bundle_'))
    try:
        copied, missing = 0, []
        for rel in sorted(media_files):
            src = src_media / rel
            dst = staging / 'media' / rel
            if not src.exists():
                missing.append(rel)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

        manifest = {
            'version': 2,
            'runs': run_ids,
            'demo_user_fk_columns': [
                'uploaded_by_id',
                'initiated_by_id',
                'reviewed_by_id',
                'created_by_id',
            ],
            'media_relative_path_fields': ['model_file_path'],
            'groups': [
                {'label': label, 'rows': by_table[table]} for table, label in GROUPS
            ],
        }
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2))

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(staging / 'manifest.json', 'manifest.json')
            media_dir = staging / 'media'
            for p in sorted(media_dir.rglob('*')):
                if p.is_file():
                    z.write(p, str(p.relative_to(staging)))

        bundle_md5 = md5_file(out)
        sources_path = out.parent / 'sources.json'
        write_sources(sources_path, out.name, bundle_md5, weight_paths)

        size_mb = out.stat().st_size / 1e6
        print(f'Wrote {out} ({size_mb:.0f} MB)')
        print(f'  md5={bundle_md5}')
        print(
            f'  runs={run_ids} uploads={len(uploads)} images={len(images)} '
            f'detections={len(detections)} pollinator={len(poll)} '
            f'models={len(modelversions)} artifacts={len(modelartifacts)}'
        )
        print(f'  media files copied={copied}')
        print(f'  weight paths recorded={len(weight_paths)} (files shipped separately)')
        print(f'  sources scaffold: {sources_path}')
        if missing:
            print(
                f'  WARNING: {len(missing)} referenced media files were missing, '
                f'e.g. {missing[:3]}'
            )
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())

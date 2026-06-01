"""Populate a fresh database with a real demo dataset from a bundle.

The bundle (manifest.json + media/) is produced by scripts/export_demo.py and
delivered out-of-band (it is too large for git). This command rebuilds the rows
through the current ORM and copies the media into MEDIA_ROOT, so a new user gets
prepopulated, browsable runs without running any inference.

    python manage.py import_demo                       # default bundle path
    python manage.py import_demo --bundle /path/to.zip
    python manage.py import_demo --reset               # wipe + re-seed

Auto-download: when the local bundle is absent, the URLs in
`demo_assets/sources.json` (or --url) are used to fetch the data bundle and the
separate model-weight archives, verifying their sha256. Entries whose URL is
still a placeholder are skipped with a warning, so the scaffold is harmless
until the real Zenodo links are filled in.

Idempotent: re-running without --reset is a no-op once the demo data exists.

PKs are auto-generated and FKs are remapped in-memory, so the loader never
collides with rows the user has already created and never has to fight the
database's id sequences.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from argparse import ArgumentParser
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import is_naive, make_aware

PLACEHOLDER_URL = 'REPLACE_WITH_ZENODO_URL'


def _is_placeholder(url: str | None) -> bool:
    return not url or url.startswith(PLACEHOLDER_URL)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _state_path() -> Path:
    """Where the seed records its inserted PKs so --reset is exact."""
    return Path(settings.MEDIA_ROOT) / '.demo_import.json'


def _strip_nulls(value: object) -> object:
    """Postgres rejects U+0000 in text and jsonb; remove it everywhere.

    SQLite stores raw camera EXIF (which often pads strings with NULs) without
    complaint, so the bundle may carry them through. Strip recursively before
    handing the value to the ORM.
    """
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value]
    return value


class Command(BaseCommand):
    help = 'Seed the database with the real demo dataset from a bundle.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        default_bundle = (
            Path(settings.BASE_DIR) / 'demo_assets' / 'demo_bundle.zip'
        )
        parser.add_argument('--bundle', default=str(default_bundle))
        parser.add_argument(
            '--url', help='Override the data bundle URL (else demo_assets/sources.json)'
        )
        parser.add_argument(
            '--reset', action='store_true', help='Delete existing demo data first'
        )
        parser.add_argument(
            '--owner',
            help='Attribute seeded rows to this existing username '
            '(default: first superuser, else no owner)',
        )

    def handle(self, *args, **opts) -> None:
        sources = self._load_sources()
        with tempfile.TemporaryDirectory(prefix='import_demo_') as tmp:
            workdir = Path(tmp)
            bundle = self._resolve_bundle(
                Path(opts['bundle']), opts.get('url'), sources, workdir
            )
            extract_dir = workdir / 'extract'
            extract_dir.mkdir()
            self._extract(bundle, extract_dir)
            manifest = json.loads((extract_dir / 'manifest.json').read_text())
            self._seed(manifest, extract_dir / 'media', opts)

        self._fetch_weights(sources)

    def _load_sources(self) -> dict:
        path = Path(settings.BASE_DIR) / 'demo_assets' / 'sources.json'
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _resolve_bundle(
        self, local: Path, url_override: str | None, sources: dict, workdir: Path
    ) -> Path:
        if local.exists():
            return local
        url = url_override or sources.get('bundle_url')
        if _is_placeholder(url):
            raise CommandError(
                f'Bundle not found: {local}\n'
                'Mount the demo archive there, pass --bundle/--url, or fill in '
                'bundle_url in demo_assets/sources.json.'
            )
        # demo_assets is mounted read-only, so download into the writable
        # workdir rather than next to the local path.
        dest = workdir / 'demo_bundle.zip'
        self.stdout.write(f'Bundle not found locally; downloading from {url}')
        self._download(url, dest)
        self._verify(dest, sources.get('bundle_md5'))
        return dest

    def _download(self, url: str, dest: Path) -> None:
        tmp = dest.with_suffix(dest.suffix + '.part')
        with urllib.request.urlopen(url) as resp, open(tmp, 'wb') as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(dest)

    def _verify(self, path: Path, expected: str | None) -> None:
        if _is_placeholder(expected):
            self.stdout.write(self.style.WARNING(f'No md5 to verify for {path.name}'))
            return
        actual = _md5(path)
        if actual != expected:
            raise CommandError(
                f'Checksum mismatch for {path.name}: expected {expected}, got {actual}'
            )

    def _extract(self, bundle: Path, dest: str) -> None:
        if bundle.suffix == '.zip':
            with zipfile.ZipFile(bundle) as z:
                z.extractall(dest)
        else:
            with tarfile.open(bundle, 'r:*') as tar:
                tar.extractall(dest)

    def _fetch_weights(self, sources: dict) -> None:
        """Download each model weight file directly to its MEDIA_ROOT path.

        Idempotent: an entry whose dest already exists is skipped, as is one
        whose URL is still a placeholder. Each file is downloaded to a temp
        location and md5-checked before being moved into place.
        """
        media_root = Path(settings.MEDIA_ROOT)
        weights = sources.get('weights', [])
        for entry in weights:
            dest = media_root / entry['dest']
            if dest.exists():
                continue
            url = entry.get('url')
            if _is_placeholder(url):
                self.stdout.write(
                    self.style.WARNING(
                        f'Weight source not configured yet, skipping: {entry["dest"]}'
                    )
                )
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='weights_') as tmp:
                tmp_file = Path(tmp) / 'weight'
                self.stdout.write(f'Downloading {entry["dest"]} from {url}')
                self._download(url, tmp_file)
                self._verify(tmp_file, entry.get('md5'))
                shutil.move(str(tmp_file), str(dest))

        missing = [e['dest'] for e in weights if not (media_root / e['dest']).exists()]
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f'{len(missing)} weight file(s) still missing, e.g. {missing[:3]}'
                )
            )

    @transaction.atomic
    def _seed(self, manifest: dict, media_src: Path, opts: dict) -> None:
        if _state_path().exists() and not opts['reset']:
            self.stdout.write(
                self.style.WARNING(
                    'Demo data already present; nothing to do (use --reset to rebuild).'
                )
            )
            return
        if opts['reset']:
            self._reset(manifest)

        owner = self._ensure_owner(opts)
        owner_pk = owner.pk
        self._copy_media(media_src)

        user_fk_cols = set(manifest['demo_user_fk_columns'])
        path_fields = set(manifest['media_relative_path_fields'])
        media_root = Path(settings.MEDIA_ROOT)

        # old_pk -> new_pk per model label, used to rewrite FK columns in later
        # groups. Auto-generated PKs mean the database advances its sequences
        # naturally — no risk of collisions with user-created rows, ever.
        id_map: dict[str, dict[int, int]] = {}
        deferred: list[tuple[type[models.Model], str, int, int]] = []
        counts: dict[str, int] = {}

        for group in manifest['groups']:
            label = group['label']
            model = apps.get_model(label)
            pk_attname = model._meta.pk.attname
            fields = {f.attname: f for f in model._meta.concrete_fields}
            fk_remaps = self._fk_remap_targets(model, id_map)
            self_fk_attnames = {
                f.attname
                for f in model._meta.concrete_fields
                if f.is_relation and f.related_model is model
            }
            # If the PK is itself an FK to a model we've already seeded (e.g.
            # PollinatorDetection.detection_id mirrors Detection.id), set it
            # explicitly via the remap; otherwise let the DB auto-generate it.
            pk_is_fk = pk_attname in fk_remaps

            group_map: dict[int, int] = {}
            for record in group['rows']:
                old_pk = record[pk_attname]
                kwargs: dict[str, object] = {}
                for attname, field in fields.items():
                    if attname == pk_attname and not pk_is_fk:
                        continue
                    if attname not in record:
                        continue
                    value = record[attname]
                    if attname in user_fk_cols:
                        value = owner_pk if value is not None else None
                    elif attname in path_fields and value:
                        value = str(media_root / value)
                    elif attname in fk_remaps and value is not None:
                        value = id_map[fk_remaps[attname]].get(value)
                    elif attname in self_fk_attnames and value is not None:
                        deferred.append((model, attname, old_pk, value))
                        value = None
                    else:
                        value = self._coerce(field, value)
                    kwargs[attname] = value
                obj = model.objects.create(**kwargs)
                group_map[old_pk] = obj.pk
            id_map[label] = group_map
            counts[label] = len(group_map)

        # Second pass: wire self-referential FKs to their new PKs.
        for model, attname, old_pk, old_target_pk in deferred:
            group_map = id_map[model._meta.label]
            new_pk = group_map[old_pk]
            new_target_pk = group_map.get(old_target_pk)
            if new_target_pk is not None:
                model.objects.filter(pk=new_pk).update(
                    **{attname: new_target_pk}
                )

        self._write_state(id_map)
        summary = ', '.join(
            f'{label.split(".")[-1]}={n}' for label, n in counts.items()
        )
        self.stdout.write(
            self.style.SUCCESS(f'Seeded demo: {summary}. Owner: {owner.username}.')
        )

    def _fk_remap_targets(
        self, model: type[models.Model], id_map: dict
    ) -> dict[str, str]:
        """Map FK attnames on `model` to labels of already-seeded targets."""
        targets: dict[str, str] = {}
        for f in model._meta.concrete_fields:
            if not (f.is_relation and f.related_model):
                continue
            label = f.related_model._meta.label
            if label in id_map:
                targets[f.attname] = label
        return targets

    def _coerce(self, field: models.Field, value: object) -> object:
        if value is None:
            return None
        if isinstance(field, models.JSONField) and isinstance(value, str):
            return _strip_nulls(json.loads(value))
        if isinstance(field, models.DateTimeField) and isinstance(value, str):
            dt = parse_datetime(value)
            if dt is not None and settings.USE_TZ and is_naive(dt):
                dt = make_aware(dt)
            return dt
        if isinstance(field, models.DateField) and isinstance(value, str):
            return parse_date(value)
        if isinstance(value, str):
            return _strip_nulls(value)
        return value

    def _ensure_owner(self, opts: dict):
        """The user the seeded rows are attributed to.

        An explicit --owner must already exist. Otherwise an existing superuser
        is reused; if there is none (the from-scratch case), a default admin is
        created so the instance is immediately usable. The credentials default
        to admin / admin123 but are overridable via the DJANGO_SUPERUSER_*
        environment variables for non-local deployments.
        """
        User = get_user_model()
        name = opts.get('owner')
        if name:
            user = User.objects.filter(username=name).first()
            if not user:
                raise CommandError(
                    f'--owner {name!r} not found; create the user first.'
                )
            return user

        existing = User.objects.filter(is_superuser=True).order_by('pk').first()
        if existing:
            return existing

        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        user = User.objects.create_superuser(
            username=username, email=email, password=password
        )
        self.stdout.write(
            self.style.WARNING(
                f'Created superuser {username!r} (change the password for any '
                'non-local deployment).'
            )
        )
        return user

    def _copy_media(self, media_src: Path) -> None:
        if not media_src.exists():
            return
        media_root = Path(settings.MEDIA_ROOT)
        for src in media_src.rglob('*'):
            if src.is_dir():
                continue
            dst = media_root / src.relative_to(media_src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(src, dst)

    def _write_state(self, id_map: dict[str, dict[int, int]]) -> None:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {label: list(group.values()) for label, group in id_map.items()}
        path.write_text(json.dumps(payload))

    def _read_state(self) -> dict | None:
        path = _state_path()
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _reset(self, manifest: dict) -> None:
        """Delete prior demo data. Prefers the state file written by the last
        successful seed; falls back to the manifest's original PKs so a DB
        seeded by an earlier version of this command can still be wiped."""
        state = self._read_state()
        if state:
            run_pks = state.get('analysis.InferenceRun', [])
            upload_pks = state.get('datasets.Upload', [])
            mv_pks = state.get('analysis.ModelVersion', [])
        else:
            run_pks = manifest['runs']
            upload_pks = sorted(
                {
                    r['upload_id']
                    for g in manifest['groups']
                    if g['label'] == 'analysis.InferenceRun'
                    for r in g['rows']
                    if r.get('upload_id') is not None
                }
            )
            mv_pks = [
                r['id']
                for g in manifest['groups']
                if g['label'] == 'analysis.ModelVersion'
                for r in g['rows']
            ]

        InferenceRun = apps.get_model('analysis.InferenceRun')
        Upload = apps.get_model('datasets.Upload')
        ModelVersion = apps.get_model('analysis.ModelVersion')

        for run in InferenceRun.objects.filter(pk__in=run_pks).only('pk', 'module'):
            run_dir = Path(settings.MEDIA_ROOT) / 'runs' / run.module / str(run.pk)
            if run_dir.exists():
                shutil.rmtree(run_dir, ignore_errors=True)
        InferenceRun.objects.filter(pk__in=run_pks).delete()
        Upload.objects.filter(pk__in=upload_pks).delete()
        ModelVersion.objects.filter(pk__in=mv_pks).delete()
        _state_path().unlink(missing_ok=True)
        self.stdout.write(self.style.WARNING('Reset: removed prior demo data.'))

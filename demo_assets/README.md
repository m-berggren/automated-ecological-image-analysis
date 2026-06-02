# Demo bundle

`import_demo` populates a fresh database with a real, browsable dataset (the
seed and pollinator runs with their images, crops, detections, and model
records). The data and media are too large for git, so they ship out-of-band:

- `demo_bundle.zip` — manifest + images/crops (no model weights).
- Model weights ship as **separate archives** (e.g. one Zenodo file per model),
  listed in `sources.json`.

Everything in this directory except this README and `sources.json` is
gitignored.

## sources.json

Holds the download URLs and checksums used when a local bundle is absent:

```json
{
  "bundle_url": "https://zenodo.org/records/<id>/files/demo_bundle.zip?download=1",
  "bundle_md5": "...",
  "weights": [
    {"dest": "models/seeds/1/weights.pt",
     "url": "https://zenodo.org/records/<id>/files/seed-yolo-phyca.pt?download=1",
     "md5": "..."}
  ]
}
```

`export_demo.py` writes this file with the real `bundle_md5` and a `weights`
entry per model (placeholder URLs); fill in each `url` and `md5` after upload.
`md5` is the checksum Zenodo shows for the file. Each weight is downloaded
directly to its `dest` (a MEDIA_ROOT-relative path). Entries whose URL is still
`REPLACE_WITH_ZENODO_URL` are skipped, so the scaffold is harmless until
finalized.

## Loading it

Local:

```bash
uv run python manage.py import_demo            # uses demo_assets/demo_bundle.zip
uv run python manage.py import_demo --reset    # wipe demo data and reload
```

If the local bundle is missing, the URLs in `sources.json` are used to download
the data bundle and weight archives (checksum-verified).

Docker: set `IMPORT_DEMO=true` in `.env`. The entrypoint runs `import_demo` on
startup (idempotent), downloading from `sources.json` if no local bundle is
mounted.

Ownership and login: seeded rows are attributed to an existing superuser if one
is present, to `--owner <username>` if given, or otherwise to a freshly created
`admin` / `admin123`. Override those defaults with the `DJANGO_SUPERUSER_*`
environment variables, and change the password for any non-local deployment.

## Regenerating the bundle

From a populated source instance (e.g. a sibling checkout):

```bash
python scripts/export_demo.py --source ../aea-merge-tg78-into-72 --runs 1 2 \
    --out demo_assets/demo_bundle.zip
```

This writes `demo_bundle.zip` and refreshes `sources.json` (preserving any URLs
already filled in). Upload the zip and the weight archives to Zenodo, then paste
their URLs into `sources.json`.

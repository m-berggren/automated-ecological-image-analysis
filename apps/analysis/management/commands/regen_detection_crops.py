"""Re-render Detection.crop files from the current source images + bboxes.

Useful when crop files on disk are stale relative to the live DB rows: e.g.
an earlier crop writer read the wrong bbox keys, so every saved file was a
top-left corner cut. Calling write_detection_crop again produces a correct
JPEG and updates Detection.crop to point at it.

Old files are deleted before the new one is written so the storage backend
does not add a uniqueness suffix and we end up with one file per row.

Run unscoped or filter by run:
    uv run python manage.py regen_detection_crops
    uv run python manage.py regen_detection_crops --run 3
"""

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from apps.analysis.crops import write_detection_crop
from apps.analysis.models import Detection


class Command(BaseCommand):
    help = 'Regenerate Detection.crop JPEGs from the current bbox + source image.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--run',
            type=int,
            default=None,
            help='Restrict to a single InferenceRun id.',
        )

    def handle(self, *args, run, **options):
        qs = Detection.objects.select_related('image').order_by('id')
        if run is not None:
            qs = qs.filter(inference_run_id=run)

        total = qs.count()
        self.stdout.write(f'Regenerating crops for {total} detection(s)...')

        ok = 0
        skipped = 0
        for d in qs.iterator(chunk_size=200):
            if d.crop and default_storage.exists(d.crop.name):
                default_storage.delete(d.crop.name)
            d.crop = None
            if write_detection_crop(d):
                d.save(update_fields=['crop'])
                ok += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f'Done. wrote={ok} skipped={skipped} total={total}'),
        )

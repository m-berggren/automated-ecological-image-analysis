from django.apps import AppConfig


class SeedsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.seeds'

    def ready(self):
        """Mark any jobs that were running when Django last shut down as failed."""
        try:
            from apps.analysis.models import TrainingJob, JobStatus
            from apps.datasets.models import Module
            from django.utils import timezone

            orphaned = TrainingJob.objects.filter(
                module=Module.SEEDS,
                status__in=[JobStatus.RUNNING, JobStatus.PENDING],
            )
            count = orphaned.update(
                status=JobStatus.FAILED,
                error_message='Job interrupted — server was restarted.',
                completed_at=timezone.now(),
            )
            if count:
                import logging

                logging.getLogger(__name__).warning(
                    f'Marked {count} orphaned seed training jobs as failed on startup'
                )
        except Exception:
            pass  # DB might not exist yet during first migration

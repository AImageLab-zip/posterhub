from django.core.management.base import BaseCommand

from bot_engine.models import ResearchPoster


class Command(BaseCommand):
    help = (
        "Regenerate poster thumbnails so the EXIF orientation is applied "
        "(fixes portrait posters that were stored sideways)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List posters without changing anything")

    def handle(self, *args, **options):
        posters = ResearchPoster.objects.exclude(image="").exclude(image__isnull=True)
        done = failed = 0
        for poster in posters:
            if options["dry_run"]:
                self.stdout.write(f"would regenerate poster {poster.pk}")
                continue
            old = poster.thumbnail.name if poster.thumbnail else None
            poster.thumbnail = None
            poster.generate_thumbnail(save=False)
            if poster.thumbnail:
                # update_fields keeps updated_at untouched
                poster.save(update_fields=["thumbnail"])
                if old and old != poster.thumbnail.name:
                    poster.thumbnail.storage.delete(old)
                done += 1
            else:
                # generation failed: keep the previous thumbnail
                if old:
                    poster.thumbnail = old
                failed += 1
                self.stderr.write(f"poster {poster.pk}: thumbnail generation failed")
        self.stdout.write(self.style.SUCCESS(f"Regenerated {done}, failed {failed}"))

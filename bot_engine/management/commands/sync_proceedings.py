from django.core.management.base import BaseCommand

from bot_engine.proceedings import sync_sources


class Command(BaseCommand):
    help = "Download enabled proceedings sources and refresh their paper lists (all, or the given source IDs)."

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="*", type=int)

    def handle(self, *args, **options):
        for source, status in sync_sources(options["ids"] or None).items():
            style = self.style.SUCCESS if status == "ok" else self.style.WARNING
            self.stdout.write(style(f"{source}: {status}"))

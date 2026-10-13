import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from routes.services.importer import import_prices


class Command(BaseCommand):
    help = "Validate and atomically import a complete fuel-price CSV snapshot."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument(
            "--report", type=Path, help="Save the full report, including rejected rows."
        )

    def handle(self, *args, **options):
        try:
            report = import_prices(options["path"])
            if options["report"]:
                options["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
        except (ValueError, OSError, UnicodeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps({k: v for k, v in report.items() if k != "rejected_rows"}, indent=2)
        )

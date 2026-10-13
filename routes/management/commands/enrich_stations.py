import csv
import json
import math
import uuid
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routes.models import Dataset, Station
from routes.services.errors import PlanningError
from routes.services.locations import lookup_city, state_at


class Command(BaseCommand):
    help = "Persist reviewed station coordinates and/or explicit GeoNames city fallbacks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--coordinates", help="CSV: source_id,latitude,longitude,source,precision,confidence"
        )
        parser.add_argument("--allow-city-fallback", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dataset = Dataset.objects.select_for_update().filter(id=1).first()
        if not dataset:
            raise CommandError("Import fuel prices first.")
        stations = {s.source_id: s for s in Station.objects.all()}
        changed = set()
        if options["coordinates"]:
            try:
                with open(options["coordinates"], encoding="utf-8-sig", newline="") as handle:
                    seen = set()
                    for row in csv.DictReader(handle):
                        identifier = row["source_id"].strip()
                        if identifier in seen or identifier not in stations:
                            raise ValueError(f"Duplicate or unknown source_id: {identifier}")
                        seen.add(identifier)
                        station = stations[identifier]
                        lat, lon = float(row["latitude"]), float(row["longitude"])
                        if not (
                            math.isfinite(lat)
                            and math.isfinite(lon)
                            and -90 <= lat <= 90
                            and -180 <= lon <= 180
                        ):
                            raise ValueError("Invalid coordinates.")
                        if state_at(lat, lon) != station.state:
                            raise ValueError(f"State mismatch for {identifier}.")
                        if (
                            row["precision"] not in {"station", "city"}
                            or row["confidence"] not in {"high", "medium", "low"}
                            or not row["source"].strip()
                            or len(row["source"]) > 500
                        ):
                            raise ValueError(
                                "Coordinates require source, precision (station/city), and confidence (high/medium/low)."
                            )
                        station.latitude, station.longitude = lat, lon
                        station.coordinate_source, station.precision, station.confidence = (
                            row["source"],
                            row["precision"],
                            row["confidence"],
                        )
                        changed.add(identifier)
            except (KeyError, ValueError, OSError, PlanningError) as exc:
                raise CommandError(str(exc)) from exc
        if options["allow_city_fallback"]:
            for station in stations.values():
                if station.latitude is not None:
                    continue
                city = lookup_city(station.city, station.state)
                if city:
                    station.latitude, station.longitude = city["latitude"], city["longitude"]
                    station.coordinate_source = f"GeoNames:{city['geonameid']}"
                    station.precision, station.confidence = "city", "low"
                    changed.add(station.source_id)
        if changed:
            Station.objects.bulk_update(
                [stations[k] for k in changed],
                ["latitude", "longitude", "coordinate_source", "precision", "confidence"],
                batch_size=500,
            )
            dataset.version = uuid.uuid4()
            dataset.save()
        self.stdout.write(
            json.dumps(
                {
                    "total": len(stations),
                    "updated": len(changed),
                    "coverage": dict(Counter(s.precision for s in stations.values())),
                }
            )
        )

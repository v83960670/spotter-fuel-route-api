"""Isolated synthetic benchmark. Never connects to a routing service or production DB."""

import argparse
import json
import os
import statistics
import sys
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_DEBUG", "true")

import django  # noqa: E402
from django.conf import settings  # noqa: E402

settings.DATABASES["default"]["NAME"] = ":memory:"
settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
settings.ALLOW_APPROXIMATE_STATIONS = False
settings.LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {"routes": {"handlers": [], "level": "CRITICAL"}},
}
django.setup()

from django.core.cache import cache  # noqa: E402
from django.core.management import call_command  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from routes.models import Dataset, Station  # noqa: E402
from routes.services.locations import city_index  # noqa: E402
from routes.services.optimizer import FuelPoint, optimize_fuel  # noqa: E402
from routes.services.provider import RoadRoute  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/benchmark.json"))
    args = parser.parse_args()
    call_command("migrate", verbosity=0)
    Dataset.objects.create(source_sha256="synthetic-benchmark")
    # Synthetic line, station coordinates, prices, and road mileage. Not navigable evidence.
    coordinates = [[-105 + i * 0.01, 40] for i in range(1501)]
    route = RoadRoute(Decimal(1300), 80000, coordinates)
    Station.objects.bulk_create(
        [
            Station(
                source_id=str(i),
                name=f"Synthetic station {i}",
                address="fixture",
                city="Fixture",
                state="CO",
                price=Decimal(2) + Decimal(i % 40) / 20,
                latitude=40 + (i % 5) * 0.001,
                longitude=-105 + (i / 8151) * 15,
                precision="station",
                confidence="high",
                coordinate_source="synthetic benchmark",
            )
            for i in range(8151)
        ],
        batch_size=500,
    )
    city_index()
    client = APIClient()
    request = {"start": "Denver, CO", "finish": "Chicago, IL", "initial_fuel_price": "4"}
    cold, warm = [], []
    with patch("routes.services.planner.directions", return_value=route) as mocked:
        for _ in range(5):
            cache.clear()
            began = perf_counter()
            response = client.post("/api/v1/routes/optimize/", request, format="json")
            cold.append((perf_counter() - began) * 1000)
            if response.status_code != 200:
                raise RuntimeError(response.content.decode())
            began = perf_counter()
            cached = client.post("/api/v1/routes/optimize/", request, format="json")
            warm.append((perf_counter() - began) * 1000)
            assert cached.status_code == 200 and cached.json()["metrics"]["directions_calls"] == 0
        call_count = mocked.call_count
    points = [
        FuelPoint(str(i), Decimal(i) / 10, Decimal(2) + Decimal(i % 50) / 10)
        for i in range(1, 10001)
    ]
    times = []
    for _ in range(20):
        began = perf_counter()
        optimize_fuel(Decimal(1100), points, Decimal(10), Decimal(50), Decimal(50))
        times.append((perf_counter() - began) * 1000)
    report = {
        "kind": "synthetic offline benchmark; provider mocked; no network latency included",
        "python": sys.version.split()[0],
        "station_count": 8151,
        "geometry_points": len(coordinates),
        "cold_samples_ms": [round(v, 3) for v in cold],
        "warm_samples_ms": [round(v, 3) for v in warm],
        "cold_median_ms": round(statistics.median(cold), 3),
        "warm_median_ms": round(statistics.median(warm), 3),
        "mock_directions_calls_for_five_cold_and_five_warm_requests": call_count,
        "optimizer_10000_candidates_median_ms": round(statistics.median(times), 3),
        "api_metrics_last_cold_request": response.json()["metrics"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

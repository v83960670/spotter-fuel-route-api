import csv
import json
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from routes.models import Station
from routes.services.importer import COLUMNS, import_prices

pytestmark = pytest.mark.django_db


def test_import_to_api_pipeline_with_only_http_transport_mocked(tmp_path, settings):
    settings.ALLOW_APPROXIMATE_STATIONS = True
    settings.ORS_API_KEY = "test-placeholder"
    path = tmp_path / "fuel.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(COLUMNS))
        writer.writeheader()
        for identifier, city, state, price in [
            ("a", "Chicago", "IL", "4"),
            ("b", "Denver", "CO", "3"),
        ]:
            writer.writerow(
                {
                    "OPIS Truckstop ID": identifier,
                    "Truckstop Name": "Synthetic fixture",
                    "Address": "Fixture",
                    "City": city,
                    "State": state,
                    "Rack ID": "test",
                    "Retail Price": price,
                }
            )
    import_prices(path)
    call_command("enrich_stations", allow_city_fallback=True)
    chicago = Station.objects.get(source_id="a")
    denver = Station.objects.get(source_id="b")
    # Synthetic provider response anchored at actual city centroids, not a real road route.
    geometry = {
        "type": "LineString",
        "coordinates": [[chicago.longitude, chicago.latitude], [denver.longitude, denver.latitude]],
    }
    provider = {
        "features": [
            {
                "geometry": geometry,
                "properties": {
                    "summary": {"distance": Decimal(400) * Decimal("1609.344"), "duration": 20000}
                },
            }
        ]
    }
    provider["features"][0]["properties"]["summary"]["distance"] = float(
        provider["features"][0]["properties"]["summary"]["distance"]
    )
    with patch("httpx.Client.post", return_value=httpx.Response(200, json=provider)) as post:
        response = APIClient().post(
            "/api/v1/routes/optimize/",
            {
                "start": "Chicago, IL",
                "finish": "Denver, CO",
                "initial_fuel_gallons": 10,
                "initial_fuel_price": 4,
            },
            format="json",
        )
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["fuel_stops"][0]["source_id"] == "a"
    assert data["fuel_stops"][0]["precision"] == "city"
    assert data["fuel"]["on_route_purchase_cost"] == "120.00"
    assert data["fuel"]["total_trip_fuel_cost"] == "160.00"
    post.assert_called_once()


def test_coordinate_api_and_non_us_failure(tmp_path, settings):
    path = tmp_path / "boundaries.json"
    path.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "properties": {"state": "IL"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[-90, 40], [-87, 40], [-87, 43], [-90, 43], [-90, 40]]
                            ],
                        },
                    }
                ]
            }
        )
    )
    settings.US_BOUNDARIES_PATH = path
    client = APIClient()
    body = {
        "start": {"latitude": 41.8, "longitude": -87.65},
        "finish": {"latitude": 43.65, "longitude": -79.38},
    }
    assert (
        client.post("/api/v1/routes/optimize/", body, format="json").json()["error"]["code"]
        == "outside_usa"
    )
    for bad in [True, "NaN", "Infinity"]:
        body["start"]["latitude"] = bad
        assert client.post("/api/v1/routes/optimize/", body, format="json").status_code == 400

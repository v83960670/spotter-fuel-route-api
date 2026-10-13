import uuid
from decimal import Decimal as D
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from routes.models import Dataset
from routes.services.errors import PlanningError
from routes.services.optimizer import FuelPoint
from routes.services.provider import RoadRoute

pytestmark = pytest.mark.django_db
URL = "/api/v1/routes/optimize/"
BODY = {"start": "Chicago, IL", "finish": "Denver, CO"}


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def dataset():
    return Dataset.objects.create(source_sha256="abc")


def test_real_serialization_cache_and_call_count(client, dataset):
    route = RoadRoute(D(450), 12345, [[-87.65, 41.85], [-104.99, 39.74]])
    with patch("routes.services.planner.directions", return_value=route) as provider:
        first = client.post(URL, BODY, format="json")
        second = client.post(URL, BODY, format="json")
    assert first.status_code == second.status_code == 200
    assert first.json()["metrics"]["directions_calls"] == 1
    assert second.json()["metrics"]["directions_calls"] == 0
    assert second.json()["metrics"]["cache_hit"]
    assert first.json()["fuel"]["total_trip_fuel_cost"] is None
    assert first.json()["geometry"]["type"] == "LineString"
    provider.assert_called_once()


def test_initial_price_accounts_only_consumed_fuel(client, dataset):
    route = RoadRoute(D(100), 3600, [[-87.65, 41.85], [-86, 41]])
    with patch("routes.services.planner.directions", return_value=route):
        data = client.post(URL, {**BODY, "initial_fuel_price": "4"}, format="json").json()
    assert data["fuel"]["total_trip_fuel_cost"] == "40.00"
    assert data["fuel"]["initial_inventory_value"] == "200.00"
    assert data["fuel"]["on_route_purchase_cost"] == "0.00"


def test_multi_stop_api_accounting(client, dataset):
    route = RoadRoute(D(1300), 90000, [[-87.65, 41.85], [-104.99, 39.74]])
    points = [
        FuelPoint("a", D(400), D(5)),
        FuelPoint("b", D(700), D(3)),
        FuelPoint("c", D(1100), D(4)),
    ]
    metadata = {p.source_id: {"name": p.source_id, "precision": "station"} for p in points}
    with (
        patch("routes.services.planner.directions", return_value=route),
        patch("routes.services.planner.match_stations", return_value=(points, metadata, [])),
    ):
        data = client.post(URL, {**BODY, "initial_fuel_price": "4"}, format="json").json()
    assert len(data["fuel_stops"]) == 3
    assert data["fuel"]["total_trip_fuel_cost"] == "490.00"
    assert data["fuel"]["consumed_gallons"] == "130.0000"
    assert data["fuel"]["remaining_gallons"] == "0.0000"


def test_version_and_vehicle_changes_invalidate_cache(client, dataset):
    route = RoadRoute(D(100), 3000, [[-87.65, 41.85], [-86, 41]])
    with patch("routes.services.planner.directions", return_value=route) as provider:
        assert client.post(URL, BODY, format="json").status_code == 200
        Dataset.objects.update(version=uuid.uuid4())
        assert client.post(URL, BODY, format="json").status_code == 200
        assert client.post(URL, {**BODY, "mpg": 20}, format="json").status_code == 200
    assert provider.call_count == 3


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"start": "Chicago, IL"},
        {**BODY, "mpg": 0},
        {**BODY, "initial_fuel_gallons": 51},
        {**BODY, "max_range_miles": -1},
        {**BODY, "start": "Toronto, ON"},
        {**BODY, "start": {"latitude": 91, "longitude": 0}},
        {**BODY, "unexpected": 2},
        {**BODY, "start": ""},
        {**BODY, "mpg": "NaN"},
    ],
)
def test_invalid_input_never_calls_provider(client, body):
    with patch("routes.services.planner.directions") as provider:
        response = client.post(URL, body, format="json")
    assert response.status_code == 400
    assert "error" in response.json()
    provider.assert_not_called()


def test_provider_error_status(client, dataset):
    with patch(
        "routes.services.planner.directions",
        side_effect=PlanningError("routing_timeout", "Timed out", 504),
    ):
        response = client.post(URL, BODY, format="json")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "routing_timeout"


def test_same_location_requires_no_routing(client, dataset):
    with patch("routes.services.planner.directions") as provider:
        response = client.post(
            URL, {"start": "Chicago, IL", "finish": "Chicago, IL"}, format="json"
        )
    assert response.status_code == 200
    assert response.json()["distance_miles"] == "0.0000"
    provider.assert_not_called()


def test_empty_dataset_and_health(client):
    assert client.get("/api/v1/health/").json() == {"status": "ok"}
    assert client.post(URL, BODY, format="json").status_code == 503
    assert client.get("/").status_code == 200


def test_concurrent_import_does_not_cache_mixed_snapshot(client, dataset):
    def changed(*args):
        Dataset.objects.update(version=uuid.uuid4())
        return [], {}, []

    with (
        patch(
            "routes.services.planner.directions",
            return_value=RoadRoute(D(10), 60, [[-87.65, 41.85], [-87.6, 41.9]]),
        ),
        patch("routes.services.planner.match_stations", side_effect=changed),
    ):
        response = client.post(URL, BODY, format="json")
    assert response.status_code == 409

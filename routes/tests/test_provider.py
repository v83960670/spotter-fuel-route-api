from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from routes.services.errors import PlanningError
from routes.services.provider import directions

START = {"longitude": -87.65, "latitude": 41.85}
FINISH = {"longitude": -104.99, "latitude": 39.74}


def payload():
    return {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-87.65, 41.85], [-104.99, 39.74]],
                },
                "properties": {"summary": {"distance": 1609344, "duration": 50000}},
            }
        ]
    }


def test_request_schema_and_single_call(settings):
    settings.ORS_API_KEY = "test-placeholder"
    with patch("httpx.Client.post", return_value=httpx.Response(200, json=payload())) as post:
        route = directions(START, FINISH)
    assert route.distance_miles == Decimal(1000)
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0].endswith("/directions/driving-car/geojson")
    assert kwargs["json"]["coordinates"] == [[-87.65, 41.85], [-104.99, 39.74]]
    assert kwargs["headers"]["Authorization"] == "test-placeholder"


@pytest.mark.parametrize(
    "status,code",
    [
        (429, "routing_rate_limited"),
        (401, "routing_authentication"),
        (403, "routing_authentication"),
        (404, "no_road_route"),
        (400, "no_road_route"),
        (500, "routing_unavailable"),
        (302, "routing_unavailable"),
    ],
)
def test_provider_failures_are_safe(settings, status, code):
    settings.ORS_API_KEY = "test-placeholder"
    with (
        patch(
            "httpx.Client.post", return_value=httpx.Response(status, text="sensitive provider text")
        ),
        pytest.raises(PlanningError) as exc,
    ):
        directions(START, FINISH)
    assert exc.value.code == code
    assert "sensitive" not in exc.value.message


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout("private url"), "routing_timeout"),
        (httpx.ConnectError("private url"), "routing_unavailable"),
    ],
)
def test_network_errors(settings, exception, code):
    settings.ORS_API_KEY = "test-placeholder"
    with patch("httpx.Client.post", side_effect=exception), pytest.raises(PlanningError) as exc:
        directions(START, FINISH)
    assert exc.value.code == code


@pytest.mark.parametrize(
    "data", [{}, {"features": []}, {"features": [None]}, {"features": [{"geometry": None}]}]
)
def test_malformed_response(settings, data):
    settings.ORS_API_KEY = "test-placeholder"
    with (
        patch("httpx.Client.post", return_value=httpx.Response(200, json=data)),
        pytest.raises(PlanningError) as exc,
    ):
        directions(START, FINISH)
    assert exc.value.code == "invalid_provider_response"


def test_no_key_does_not_make_request(settings):
    settings.ORS_API_KEY = ""
    with patch("httpx.Client.post") as post, pytest.raises(PlanningError):
        directions(START, FINISH)
    post.assert_not_called()

import math
from dataclasses import dataclass
from decimal import Decimal

import httpx
from django.conf import settings

from routes.services.errors import PlanningError

METERS_PER_MILE = Decimal("1609.344")


@dataclass(frozen=True)
class RoadRoute:
    distance_miles: Decimal
    duration_seconds: float
    coordinates: list[list[float]]


def directions(start: dict, finish: dict) -> RoadRoute:
    if not settings.ORS_API_KEY:
        raise PlanningError(
            "routing_not_configured", "Set ORS_API_KEY in the server environment.", 503
        )
    body = {
        "coordinates": [[p["longitude"], p["latitude"]] for p in (start, finish)],
        "instructions": False,
        "units": "m",
    }
    try:
        # No automatic retries: one attempted call, including quota and timeout failures.
        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False
        ) as client:
            response = client.post(
                f"{settings.ORS_BASE_URL}/directions/driving-car/geojson",
                json=body,
                headers={"Authorization": settings.ORS_API_KEY, "Accept": "application/geo+json"},
            )
    except httpx.TimeoutException as exc:
        raise PlanningError(
            "routing_timeout", "Routing provider timed out. Try again later.", 504
        ) from exc
    except httpx.RequestError as exc:
        raise PlanningError("routing_unavailable", "Routing provider is unavailable.", 502) from exc
    if response.status_code == 429:
        raise PlanningError(
            "routing_rate_limited",
            "Routing quota exhausted. Retry after the provider quota resets.",
            503,
        )
    if response.status_code in {401, 403}:
        raise PlanningError(
            "routing_authentication",
            "Routing credentials were rejected. Check the server configuration.",
            503,
        )
    if response.status_code in {400, 404}:
        raise PlanningError(
            "no_road_route",
            "Provider could not route these locations; check endpoints and provider distance limits.",
        )
    if response.status_code != 200:
        raise PlanningError(
            "routing_unavailable", "Routing provider returned an unsuccessful response.", 502
        )
    try:
        data = response.json()
        feature = data["features"][0]
        geometry = feature["geometry"]
        coordinates = geometry["coordinates"]
        summary = feature["properties"]["summary"]
        distance = Decimal(str(summary["distance"])) / METERS_PER_MILE
        duration = float(summary["duration"])
        if not distance.is_finite() or distance <= 0 or not math.isfinite(duration) or duration < 0:
            raise ValueError("Invalid route totals.")
        if geometry["type"] != "LineString" or not 2 <= len(coordinates) <= 200_000:
            raise ValueError("Invalid geometry.")
        for p in coordinates:
            if (
                len(p) < 2
                or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                    for v in p[:2]
                )
                or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90)
            ):
                raise ValueError("Invalid geometry coordinate.")
        if all(p[:2] == coordinates[0][:2] for p in coordinates):
            raise ValueError("Degenerate geometry.")
        return RoadRoute(distance, duration, [p[:2] for p in coordinates])
    except (ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
        raise PlanningError(
            "invalid_provider_response", "Routing provider returned malformed route data.", 502
        ) from exc

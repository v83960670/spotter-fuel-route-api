import copy
import hashlib
import json
import logging
from decimal import Decimal
from time import perf_counter

from django.conf import settings
from django.core.cache import cache

from routes.models import Dataset
from routes.services.errors import PlanningError
from routes.services.locations import resolve_location
from routes.services.matching import match_stations
from routes.services.optimizer import money, optimize_fuel, quantity
from routes.services.provider import RoadRoute, directions

logger = logging.getLogger("routes")


def plan_route(parameters: dict) -> dict:
    began = perf_counter()
    start, finish = resolve_location(parameters["start"]), resolve_location(parameters["finish"])
    version = Dataset.objects.filter(id=1).values_list("version", flat=True).first()
    if version is None:
        raise PlanningError(
            "dataset_not_ready", "Import the fuel-price CSV before planning routes.", 503
        )
    same = all(start[k] == finish[k] for k in ("latitude", "longitude"))
    key_data = {
        **parameters,
        "start": start,
        "finish": finish,
        "version": str(version),
        "approximate": settings.ALLOW_APPROXIMATE_STATIONS,
        "corridor": settings.STATION_CORRIDOR_MILES,
        "provider": settings.ORS_BASE_URL,
        "algorithm": 1,
    }
    key = (
        "route:"
        + hashlib.sha256(json.dumps(key_data, sort_keys=True, default=str).encode()).hexdigest()
    )
    result = cache.get(key)
    if result is not None:
        result = copy.deepcopy(result)
        result["metrics"] = {
            "cache_hit": True,
            "directions_calls": 0,
            "geocoding_calls": 0,
            "provider_ms": 0,
            "station_selection_ms": 0,
            "optimization_ms": 0,
            "total_ms": round((perf_counter() - began) * 1000, 3),
        }
        return result
    provider_start = perf_counter()
    route = (
        RoadRoute(Decimal(0), 0, [[start["longitude"], start["latitude"]]] * 2)
        if same
        else directions(start, finish)
    )
    provider_ms = (perf_counter() - provider_start) * 1000
    selection_start = perf_counter()
    points, metadata, warnings = (
        ([], {}, [])
        if same
        else match_stations(
            route, settings.STATION_CORRIDOR_MILES, settings.ALLOW_APPROXIMATE_STATIONS
        )
    )
    selection_ms = (perf_counter() - selection_start) * 1000
    optimization_start = perf_counter()
    initial = parameters["initial_fuel_gallons"]
    capacity = parameters["max_range_miles"] / parameters["mpg"]
    plan = optimize_fuel(route.distance_miles, points, parameters["mpg"], capacity, initial)
    optimization_ms = (perf_counter() - optimization_start) * 1000
    # FIFO attribution: initial fuel is consumed first. Unconsumed fuel retains value.
    price = parameters.get("initial_fuel_price")
    initial_used = min(initial, plan["consumed"])
    initial_value = initial * price if price is not None else None
    consumed_cost = (
        plan["purchase_cost"] + initial_used * price
        if price is not None
        else (plan["purchase_cost"] if initial_used == 0 else None)
    )
    warnings += [
        "Fuel plan is an estimate along one selected driving route. Road access and fuel needed for station detours are not measured; range feasibility excludes detours.",
        "Dataset prices have no observation timestamps and may be stale.",
    ]
    if settings.ALLOW_APPROXIMATE_STATIONS:
        warnings.append(
            "Approximate mode is enabled: city coordinates do not establish actual truck-stop locations or access."
        )
    if start["precision"] == "city" or finish["precision"] == "city":
        warnings.append("Named endpoints resolve to GeoNames city centers, not street addresses.")
    if price is None and initial_used > 0:
        warnings.append(
            "Starting fuel has no supplied price. Total trip fuel cost is unknown; purchase cost excludes its value."
        )
    stops = [{**metadata[stop["source_id"]], **stop} for stop in plan["stops"]]
    result = {
        "start": start,
        "finish": finish,
        "distance_miles": quantity(route.distance_miles),
        "duration_seconds": route.duration_seconds,
        "geometry": {"type": "LineString", "coordinates": route.coordinates},
        "fuel_stops": stops,
        "fuel": {
            "mpg": quantity(parameters["mpg"]),
            "max_range_miles": quantity(parameters["max_range_miles"]),
            "tank_capacity_gallons": quantity(capacity),
            "initial_gallons": quantity(initial),
            "consumed_gallons": quantity(plan["consumed"]),
            "purchased_gallons": quantity(plan["purchased"]),
            "remaining_gallons": quantity(plan["remaining"]),
            "on_route_purchase_cost": money(plan["purchase_cost"]),
            "initial_inventory_value": money(initial_value) if initial_value is not None else None,
            "total_trip_fuel_cost": money(consumed_cost) if consumed_cost is not None else None,
            "currency": "USD",
            "accounting": "Initial fuel consumed first; trip cost values consumed initial fuel plus purchases. Unconsumed initial inventory is excluded. Decimal ROUND_HALF_UP at output; rounded line items may differ from total by cents.",
        },
        "optimization": {
            "method": "next-cheaper-station greedy",
            "scope": "minimum purchase cost on a fixed route under zero-detour, continuous-fuel assumptions",
            "candidate_count": len(points),
            "approximate_mode": settings.ALLOW_APPROXIMATE_STATIONS,
        },
        "warnings": warnings,
        "dataset_version": str(version),
        "map_preview_url": "/",
        "metrics": {
            "cache_hit": False,
            "directions_calls": 0 if same else 1,
            "geocoding_calls": 0,
            "provider_ms": round(provider_ms, 3),
            "station_selection_ms": round(selection_ms, 3),
            "optimization_ms": round(optimization_ms, 3),
            "total_ms": round((perf_counter() - began) * 1000, 3),
        },
    }
    # A concurrent import must not publish a result mixing snapshots.
    if Dataset.objects.filter(id=1).values_list("version", flat=True).first() != version:
        raise PlanningError(
            "dataset_changed", "Fuel data changed during planning. Retry the request.", 409
        )
    cache.set(key, result, settings.ROUTE_CACHE_SECONDS)
    logger.info("route_completed %s", result["metrics"])
    return result

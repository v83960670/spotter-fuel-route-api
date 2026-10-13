import json
from functools import lru_cache
from pathlib import Path

import geonamescache
from django.conf import settings
from shapely.geometry import Point, shape

from routes.services.errors import PlanningError

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


@lru_cache(maxsize=1)
def city_index() -> dict:
    index = {}
    gazetteer = geonamescache.GeonamesCache(min_city_population=500)
    for city in gazetteer.get_cities().values():
        if city["countrycode"] != "US" or city["admin1code"] not in US_STATES:
            continue
        key = (normalize(city["name"]), city["admin1code"])
        index.setdefault(key, []).append(city)
    return index


def lookup_city(city: str, state: str) -> dict | None:
    matches = city_index().get((normalize(city), state.upper()), [])
    # Same-name places within a state are ambiguous; do not silently pick one.
    return matches[0] if len(matches) == 1 else None


@lru_cache(maxsize=2)
def boundaries(path: str, modified_ns: int) -> list:
    with Path(path).open(encoding="utf-8") as handle:
        document = json.load(handle)
    return [(f["properties"]["state"], shape(f["geometry"])) for f in document["features"]]


def state_at(latitude: float, longitude: float) -> str | None:
    path = Path(settings.US_BOUNDARIES_PATH)
    if not path.exists():
        raise PlanningError(
            "geography_not_ready",
            "Run python scripts/setup_geography.py to install US boundaries.",
            503,
        )
    point = Point(longitude, latitude)
    for state, polygon in boundaries(str(path), path.stat().st_mtime_ns):
        if polygon.covers(point):
            return state
    return None


def resolve_location(value: str | dict) -> dict:
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        if len(parts) != 2 or parts[1].upper() not in US_STATES:
            raise PlanningError(
                "invalid_location", "Use an unambiguous US 'City, ST' or US coordinates.", 400
            )
        city = lookup_city(parts[0], parts[1].upper())
        if city is None:
            raise PlanningError(
                "unknown_location",
                "City is missing or ambiguous in the offline gazetteer. Supply coordinates.",
                400,
            )
        return {
            "label": f"{city['name']}, {city['admin1code']}",
            "latitude": city["latitude"],
            "longitude": city["longitude"],
            "state": city["admin1code"],
            "precision": "city",
            "source": f"GeoNames:{city['geonameid']}",
        }
    state = state_at(value["latitude"], value["longitude"])
    if state is None:
        raise PlanningError(
            "outside_usa", "Coordinates must fall inside a US state or DC boundary.", 400
        )
    return {
        **value,
        "label": "Supplied coordinates",
        "state": state,
        "precision": "user_supplied",
        "source": "request",
    }

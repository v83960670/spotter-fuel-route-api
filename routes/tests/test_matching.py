from decimal import Decimal as D

import pytest

from routes.models import Station
from routes.services.matching import match_stations
from routes.services.provider import RoadRoute

pytestmark = pytest.mark.django_db


def station(identifier, lon, lat, price="3", precision="station"):
    return Station.objects.create(
        source_id=identifier,
        name=identifier,
        address="fixture",
        city="Test",
        state="IL",
        price=D(price),
        longitude=lon,
        latitude=lat,
        precision=precision,
    )


def test_matches_full_geometry_and_excludes_distant_or_unresolved():
    station("near", -89.5, 40)
    station("far", -89.5, 41)
    station("unresolved", -89.5, 40, precision="unresolved")
    route = RoadRoute(D(100), 1000, [[-90, 40], [-89.5, 40], [-89, 40]])
    points, _, _ = match_stations(route, 5, False)
    assert [p.source_id for p in points] == ["near"]
    assert abs(points[0].mile - 50) < D(".1")


def test_city_coordinates_require_explicit_mode():
    station("city", -89.5, 40, precision="city")
    route = RoadRoute(D(100), 1000, [[-90, 40], [-89, 40]])
    assert not match_stations(route, 5, False)[0]
    assert len(match_stations(route, 5, True)[0]) == 1


def test_doubling_back_does_not_silently_choose_first_pass():
    station("ambiguous", -89.5, 40)
    route = RoadRoute(D(200), 1000, [[-90, 40], [-89, 40], [-90, 40]])
    points, _, warnings = match_stations(route, 5, False)
    assert not points
    assert "ambiguous" in warnings[0]


def test_progress_is_route_order_not_longitude():
    station("a", -89.75, 40)
    station("b", -89.25, 40)
    route = RoadRoute(D(100), 1000, [[-89, 40], [-90, 40]])
    points, _, _ = match_stations(route, 5, False)
    assert [p.source_id for p in sorted(points, key=lambda p: p.mile)] == ["b", "a"]

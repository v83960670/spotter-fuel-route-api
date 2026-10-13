import json

import pytest

from routes.services.errors import PlanningError
from routes.services.locations import resolve_location, state_at


@pytest.fixture
def boundary_file(settings, tmp_path):
    # Synthetic rectangle for unit tests; live Census validation is a separate smoke check.
    path = tmp_path / "states.json"
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


def test_coordinate_boundary_validation(boundary_file):
    assert resolve_location({"latitude": 41.85, "longitude": -87.65})["state"] == "IL"
    assert state_at(40, -90) == "IL"
    with pytest.raises(PlanningError) as exc:
        resolve_location({"latitude": 43.65, "longitude": -79.38})
    assert exc.value.code == "outside_usa"


def test_missing_boundary_data_is_actionable(settings, tmp_path):
    settings.US_BOUNDARIES_PATH = tmp_path / "absent.json"
    with pytest.raises(PlanningError) as exc:
        state_at(41, -88)
    assert exc.value.status == 503


@pytest.mark.parametrize(
    "name", ["Toronto, ON", "London, GB", "FakeCity, IL", "Chicago", "Paris, France"]
)
def test_non_us_or_missing_places(name):
    with pytest.raises(PlanningError):
        resolve_location(name)


def test_named_locations_are_labeled_as_city_coordinates():
    city = resolve_location(" Chicago , il ")
    assert city["precision"] == "city"
    assert city["source"] == "GeoNames:4887398"

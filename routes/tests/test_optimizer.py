import random
from decimal import Decimal as D

import pytest

from routes.services.errors import PlanningError
from routes.services.optimizer import FuelPoint, money, optimize_fuel


def solve(distance, points=(), initial=50):
    return optimize_fuel(
        D(distance),
        [FuelPoint(str(i), D(m), D(p)) for i, (m, p) in enumerate(points)],
        D(10),
        D(50),
        D(initial),
    )


@pytest.mark.parametrize("distance,remaining", [(0, 50), (100, 40), (499, D(".1")), (500, 0)])
def test_short_and_exact_range(distance, remaining):
    result = solve(distance)
    assert not result["stops"]
    assert result["remaining"] == remaining
    assert result["consumed"] == D(distance) / 10


def test_just_over_range_requires_fuel():
    with pytest.raises(PlanningError, match="Cannot reach"):
        solve(501)
    result = solve(501, [(500, 4)])
    assert result["purchased"] == D(".1")
    assert result["purchase_cost"] == D(".4")


def test_multiple_stops_and_partial_purchases():
    result = solve(1300, [(400, 5), (700, 3), (1100, 4)])
    assert result["purchased"] == 80
    assert result["purchase_cost"] == 290
    assert [s["gallons"] for s in result["stops"]] == ["20.0000", "50.0000", "10.0000"]
    assert result["remaining"] == 0


def test_expensive_station_needed_to_reach_cheaper_station():
    result = solve(800, [(100, 6), (400, 3)], initial=10)
    assert result["stops"][0]["gallons"] == "30.0000"
    assert result["purchase_cost"] == 300


def test_skip_expensive_and_fill_cheapest_usefully():
    result = solve(900, [(200, 2), (400, 7), (650, 5)])
    assert [s["source_id"] for s in result["stops"]] == ["0", "2"]
    assert result["purchase_cost"] == 140


@pytest.mark.parametrize("points", [[(600, 1)], [(300, 3), (900, 2)]])
def test_infeasible_gaps(points):
    with pytest.raises(PlanningError):
        solve(1200, points)


def test_same_mile_duplicates_and_stations_behind_origin():
    result = solve(700, [(-10, 1), (400, 6), (400, 2), (400, 2)])
    assert result["stops"][0]["source_id"] == "2"
    assert result["purchase_cost"] == 40


def test_zero_initial_fuel_can_buy_at_start():
    assert solve(100, [(0, "3.12345")], initial=0)["purchase_cost"] == D("31.23450")
    with pytest.raises(PlanningError):
        solve(100, [(1, 3)], initial=0)


def test_money_rounds_half_up():
    assert money(D("12.345")) == "12.35"


def brute_force(distance, points, capacity, initial):
    # Independent integer fuel-state DP. All distances and fuel are integral here.
    states = {initial: 0}
    previous = 0
    for mile, price in sorted(points) + [(distance, 0)]:
        states = {
            fuel - (mile - previous): cost
            for fuel, cost in states.items()
            if fuel >= mile - previous
        }
        if not states:
            return None
        if mile == distance:
            return min(states.values())
        updated = {}
        for fuel, cost in states.items():
            for buy in range(capacity - fuel + 1):
                updated[fuel + buy] = min(updated.get(fuel + buy, float("inf")), cost + buy * price)
        states, previous = updated, mile


def test_greedy_matches_independent_exhaustive_reference():
    rng = random.Random(73)
    for _ in range(500):
        distance, capacity = rng.randint(2, 20), rng.randint(1, 8)
        initial = rng.randint(0, capacity)
        positions = sorted(rng.sample(range(distance), rng.randint(0, min(distance, 8))))
        points = [(m, rng.randint(1, 9)) for m in positions]
        expected = brute_force(distance, points, capacity, initial)
        candidates = [FuelPoint(str(i), D(m), D(p)) for i, (m, p) in enumerate(points)]
        if expected is None:
            with pytest.raises(PlanningError):
                optimize_fuel(D(distance), candidates, D(1), D(capacity), D(initial))
        else:
            assert (
                optimize_fuel(D(distance), candidates, D(1), D(capacity), D(initial))[
                    "purchase_cost"
                ]
                == expected
            )

"""Minimum purchase cost on a fixed one-dimensional route (no detour costs)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from routes.services.errors import PlanningError

ZERO = Decimal(0)
EPSILON = Decimal("0.000000001")


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def quantity(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class FuelPoint:
    source_id: str
    mile: Decimal
    price: Decimal


def optimize_fuel(
    distance: Decimal,
    points: list[FuelPoint],
    mpg: Decimal,
    capacity: Decimal,
    initial_fuel: Decimal,
) -> dict:
    if (
        not all(v.is_finite() for v in (distance, mpg, capacity, initial_fuel))
        or distance < 0
        or mpg <= 0
        or capacity <= 0
        or not ZERO <= initial_fuel <= capacity
    ):
        raise ValueError("Invalid vehicle or distance.")
    if any(not p.price.is_finite() or p.price <= 0 or not p.mile.is_finite() for p in points):
        raise ValueError("Prices must be finite and positive; mile markers must be finite.")
    # Retain the cheapest deterministic option at each progress position.
    ordered = sorted(
        (p for p in points if ZERO <= p.mile < distance),
        key=lambda p: (p.mile, p.price, p.source_id),
    )
    stations = []
    for point in ordered:
        if not stations or point.mile != stations[-1].mile:
            stations.append(point)
    stations.append(FuelPoint("destination", distance, ZERO))
    # Nearest strictly cheaper point to the right, found in linear time.
    cheaper = [None] * len(stations)
    stack = []
    for i in range(len(stations) - 1, -1, -1):
        while stack and stations[stack[-1]].price >= stations[i].price:
            stack.pop()
        if stack:
            cheaper[i] = stack[-1]
        stack.append(i)
    fuel, previous, cost, purchased = initial_fuel, ZERO, ZERO, ZERO
    stops = []
    for i, point in enumerate(stations):
        fuel -= (point.mile - previous) / mpg
        if fuel < -EPSILON:
            raise PlanningError(
                "no_feasible_fueling",
                f"Cannot reach mile {quantity(point.mile)} from mile {quantity(previous)} with the available fuel and station data.",
            )
        fuel = max(ZERO, fuel)
        previous = point.mile
        if i == len(stations) - 1:
            break
        target = capacity
        if cheaper[i] is not None:
            target = min(capacity, (stations[cheaper[i]].mile - point.mile) / mpg)
        target = min(target, (distance - point.mile) / mpg)
        buy = max(ZERO, target - fuel)
        if buy > EPSILON:
            stop_cost = buy * point.price
            stops.append(
                {
                    "source_id": point.source_id,
                    "mile_marker": quantity(point.mile),
                    "gallons": quantity(buy),
                    "cost": money(stop_cost),
                }
            )
            cost += stop_cost
            purchased += buy
            fuel += buy
    return {
        "stops": stops,
        "purchase_cost": cost,
        "purchased": purchased,
        "consumed": distance / mpg,
        "remaining": fuel,
    }

"""Regenerate the credential-free Postman assessment collection."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def request(name, body=None, status=200, description="", health=False):
    path = "/api/v1/health/" if health else "/api/v1/routes/optimize/"
    definition = {
        "method": "GET" if health else "POST",
        "header": [] if health else [{"key": "Content-Type", "value": "application/json"}],
        "url": "{{base_url}}" + path,
        "description": description,
    }
    if body is not None:
        definition["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    checks = [f"pm.test('Expected HTTP {status}', () => pm.response.to.have.status({status}));"]
    if status == 200 and not health:
        checks += [
            "pm.test('Map-ready route', () => pm.expect(pm.response.json().geometry.type).to.eql('LineString'));",
            "pm.test('Nonnegative remaining fuel', () => pm.expect(Number(pm.response.json().fuel.remaining_gallons)).to.be.at.least(0));",
            "pm.test('At most one directions call', () => pm.expect(pm.response.json().metrics.directions_calls).to.be.at.most(1));",
        ]
    return {
        "name": name,
        "request": definition,
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": checks}}],
    }


def main():
    body = {"start": "Chicago, IL", "finish": "Denver, CO", "initial_fuel_price": "3.75"}
    items = [
        request("Health", health=True),
        request(
            "Short route — Chicago to Milwaukee",
            {"start": "Chicago, IL", "finish": "Milwaukee, WI", "initial_fuel_price": "3.75"},
        ),
        request(
            "Assessment route — Chicago to Denver",
            body,
            description="Requires ORS key, imported prices and reviewed coordinates or explicit approximate mode. Initial price is a user-supplied accounting example, not observed market data.",
        ),
        request(
            "Long route — Chicago to Los Angeles",
            {"start": "Chicago, IL", "finish": "Los Angeles, CA", "initial_fuel_price": "3.75"},
            description="Multiple stops expected if the station corridor is feasible. Sparse California data or provider limits may correctly produce an error; confirm before recording.",
        ),
        request(
            "Coordinate input",
            {
                "start": {"latitude": 41.85003, "longitude": -87.65005},
                "finish": {"latitude": 39.73915, "longitude": -104.9847},
            },
        ),
        request(
            "Same location — no directions call", {"start": "Chicago, IL", "finish": "Chicago, IL"}
        ),
        request("Invalid location — Canada", {"start": "Toronto, ON", "finish": "Denver, CO"}, 400),
        request("Invalid vehicle — over capacity", {**body, "initial_fuel_gallons": 51}, 400),
        request(
            "No feasible fueling — tiny range, empty tank",
            {**body, "max_range_miles": 1, "initial_fuel_gallons": 0},
            422,
            description="Requires configured provider and assessment data. Expect no feasible fueling for this dataset; 503 instead indicates missing setup. The deterministic equivalent is covered by automated tests.",
        ),
    ]
    document = {
        "info": {
            "name": "Spotter Fuel Route API",
            "description": "Real requests to the configured backend. No API keys belong in this collection. Live routes require the original CSV and server-side ORS setup.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "variable": [{"key": "base_url", "value": "http://127.0.0.1:8000"}],
    }
    environment = {
        "name": "Spotter local",
        "values": [{"key": "base_url", "value": "http://127.0.0.1:8000", "enabled": True}],
        "_postman_variable_scope": "environment",
    }
    target = ROOT / "postman"
    target.mkdir(exist_ok=True)
    (target / "spotter.postman_collection.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    (target / "local.postman_environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

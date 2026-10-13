"""Exercise a running server; uses its real configured provider and price data."""

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--start", default="Chicago, IL")
    parser.add_argument("--finish", default="Denver, CO")
    parser.add_argument("--output", type=Path, default=Path("artifacts/live-response.json"))
    args = parser.parse_args()
    with httpx.Client(timeout=60) as client:
        health = client.get(args.base_url.rstrip("/") + "/api/v1/health/")
        health.raise_for_status()
        for number in range(2):
            response = client.post(
                args.base_url.rstrip("/") + "/api/v1/routes/optimize/",
                json={"start": args.start, "finish": args.finish},
            )
            data = response.json()
            if response.status_code != 200:
                print(json.dumps(data, indent=2))
                raise SystemExit(1)
            print(
                json.dumps(
                    {
                        "request": number + 1,
                        "distance_miles": data["distance_miles"],
                        "stops": len(data["fuel_stops"]),
                        "fuel": data["fuel"],
                        "metrics": data["metrics"],
                    },
                    indent=2,
                )
            )
            if number == 0:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            elif data["metrics"]["directions_calls"] != 0:
                raise SystemExit("Second identical request unexpectedly missed the cache.")


if __name__ == "__main__":
    main()

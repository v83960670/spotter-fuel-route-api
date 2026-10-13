# Spotter fuel route API

A Django API that retrieves a driving route and minimizes estimated fuel purchases
at eligible stations along it. Defaults: **500-mile range, 10 MPG, 50-gallon tank**.
It supports multiple stops, partial purchases, explicit starting-fuel accounting,
and a Leaflet map preview.

The optimization is exact for its fixed-route, zero-detour mathematical model.
The geographic fueling plan is an **estimate**: station access and road detours
are not measured. City-coordinate fallback is opt-in and labeled in every response.
This is an assessment application, not a dispatch or navigation safety system.

## Requirements and setup

Python 3.13 or 3.14, Git, and an openrouteservice API key. Tested dependency pins:
Django 6.1.2 and DRF 3.18.3, verified against their official release pages.
SQLite is the default; no Docker, Redis, or worker service is needed.

```sh
git clone https://github.com/v83960670/spotter-fuel-route-api.git
cd spotter-fuel-route-api
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on PowerShell or
`source .venv/bin/activate` on macOS/Linux, then:

```sh
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` (`Copy-Item .env.example .env` on PowerShell;
`cp .env.example .env` on macOS/Linux). Set `ORS_API_KEY` locally. Never commit it.
Create a free account at [HeiGIT](https://account.heigit.org/) and obtain your own
openrouteservice key. The key stays in the backend and is sent as an Authorization
header, never to the preview browser.

```sh
python manage.py migrate
python scripts/setup_geography.py
python manage.py import_fuel_prices data/private/fuel-prices-for-be-assessment.csv
python manage.py enrich_stations --allow-city-fallback
```

Supply the original assessment CSV at the indicated path first. It is deliberately
not redistributed. For the city fallback demonstration, set
`ALLOW_APPROXIMATE_STATIONS=true` in `.env`. To use reviewed exact coordinates,
follow [data/README.md](data/README.md); leave approximate mode disabled.

```sh
python manage.py runserver 127.0.0.1:8000
```

Open [the map preview](http://127.0.0.1:8000/) or import the files under `postman/`.
The map requires internet access for Leaflet and OpenStreetMap tiles. Django does
not serve a fabricated route when provider credentials are missing.

## API

`GET /api/v1/health/` checks the application and database connection.

`POST /api/v1/routes/optimize/` accepts JSON:

```json
{"start":"Chicago, IL","finish":"Denver, CO","initial_fuel_price":"3.75"}
```

Coordinate form and advanced parameters:

```json
{
  "start":{"latitude":41.85003,"longitude":-87.65005},
  "finish":{"latitude":39.73915,"longitude":-104.9847},
  "mpg":"10",
  "max_range_miles":"500",
  "initial_fuel_gallons":"25",
  "initial_fuel_price":"3.75"
}
```

Named locations use an offline GeoNames city/state index. Unsupported or ambiguous
names require coordinates. Coordinate input is checked against downloaded US state
polygons, not a coarse rectangular country box. The 50 states and DC are supported;
territories are excluded. US endpoints can still produce a provider-selected route
passing through another country; the planner has only US fuel candidates.

Responses contain `start`, `finish`, `distance_miles`, `duration_seconds`, GeoJSON
`geometry`, ordered `fuel_stops`, `fuel`, `optimization`, `warnings`,
`dataset_version`, `metrics`, and `map_preview_url`. Each stop includes its source
identifier, location evidence, price, route mile marker, gallons, and cost. Money
and quantities are strings to preserve decimal representation; coordinates and
timing metrics are JSON numbers. The map URL opens the interactive planner; it is
not a persisted share link to a previous request.

Errors have an `error` object with a stable `code` and a `message` or validation
`details`. Typical statuses: 400 invalid input, 422 no feasible fueling/road route,
409 dataset changed mid-request, 503 missing setup/provider quota or credentials,
502 malformed/unavailable provider, 504 provider timeout, and 429 local throttling.

## Fuel optimization and accounting

The optimizer orders station projections by progress along the entire route.
At each point, buy enough to reach the next cheaper station if it is within range;
otherwise buy to capacity or the destination's remaining need. It visits virtual
station positions without requiring a physical stop unless a purchase is positive.
Equal-position options collapse to the cheapest deterministic choice. Sorting costs
O(n log n); a monotonic stack finds next-cheaper stations in O(n).

The exchange argument is straightforward: buying fuel at a dearer station to carry
past a reachable cheaper station cannot improve cost. When no cheaper reachable
station exists, moving a necessary future purchase back to the current station
cannot increase cost. This assumes divisible fuel, unlimited supply, fixed prices,
no stop penalties, no detours, and a fixed route. Tests compare this strategy with
an independent exhaustive fuel-state DP on 500 seeded small cases.

Starting fuel defaults to a full tank. Without `initial_fuel_price`, the API reports
purchase cost and leaves total trip cost null whenever initially owned fuel was
consumed. It never prices that fuel at zero or invents a nearby price. With a price,
starting inventory is consumed first (FIFO); total trip cost includes consumed
initial fuel and on-route purchases. Unconsumed starting inventory is excluded.
Purchases never intentionally leave bought fuel at the destination. All monetary
arithmetic uses Decimal; output uses ROUND_HALF_UP to cents. Quantities display four
decimals, while calculations retain precision. Rounded line items may differ from
the rounded aggregate by a cent or two.

## Data and matching

CSV imports are atomic snapshots with Decimal prices (up to eight decimals), US
filtering, whitespace normalization, duplicate handling, row provenance, and stable
identifiers. Conflicting prices use the maximum observed price; the file cannot
establish recency. Conflicting locations are quarantined. See
[data documentation](data/README.md) and [source attribution](docs/DATA_SOURCES.md).

Coordinates are enriched outside requests. Exact coordinates require a reviewed
input file; city fallback uses licensed GeoNames data, with source IDs, city precision,
and low confidence persisted. Missing/ambiguous cities remain unresolved.

Matching uses indexed database bounds plus a Shapely STRtree over every route
segment. A route-centered azimuthal equidistant projection estimates proximity;
ellipsoidal segment lengths estimate progress, scaled to the provider's road mileage.
The corridor defaults to 5 miles. Nearby returning/parallel segments with materially
ambiguous projections are excluded rather than assigned arbitrarily. Projection
distortion, geometry simplification, and unmeasured road access limit accuracy.

## Provider calls, caching, and performance

One HTTP POST to
`https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson`
per uncached route. GeoJSON uses `[longitude, latitude]`; summary distance is meters
and duration seconds. No station routing calls or online geocoding calls occur.
Identical endpoints use no directions call. Failures do not retry automatically.
Connect timeout is 5 seconds; HTTPX read/write/pool timeout is 20 seconds.

Result keys include resolved endpoints, vehicle and initial-fuel parameters,
provider, matching settings, algorithm version, and dataset version. Price imports
and coordinate updates invalidate via the version. Cache TTL defaults to 15 minutes.
The default cache and throttle are per-process; concurrent misses may each call ORS.
Use a shared cache and request coalescing before scaling across processes.

Responses expose actual local stage timings and directions/geocoding call counts
for successful requests. Run a reproducible **synthetic, provider-mocked** benchmark:

```sh
python scripts/benchmark.py --output artifacts/benchmark.json
```

It uses a temporary in-memory database with 8,151 synthetic candidates and does not
modify the imported assessment database. [Recorded measurements](docs/BENCHMARK_RESULTS.json)
exclude real provider latency and must not be presented as live performance.

ORS quotas are plan-specific; verify your current limits in the
[HeiGIT plans dashboard](https://account.heigit.org/info/plans). Quota responses
become actionable 503 errors. No quota values are hardcoded or promised here.

## Verification and demonstration

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
pytest --cov=routes --cov-report=term-missing
ruff check .
ruff format --check .
python scripts/live_smoke.py
```

Automated tests are offline, with explicit provider mocks; the last command uses
the running server's **real** provider. It saves a response to ignored `artifacts/`
and checks that the repeated request hits the cache. A missing key, unresolved
stations, or an infeasible corridor is a reported failure, not a substitute response.

- [Verification report](docs/VERIFICATION.md)
- [Postman collection](postman/spotter.postman_collection.json)
- [Postman environment](postman/local.postman_environment.json)
- [Loom walkthrough and recording checklist](docs/LOOM_DEMO_SCRIPT.md)

## Structure

```text
config/                    Django settings, URLs, WSGI
routes/api/                Thin HTTP views and structured error handling
routes/serializers.py      Input validation and output contract
routes/services/           Import, geography, provider, matching, optimization
routes/management/commands/Import and coordinate enrichment
routes/tests/              Offline business-rule and integration tests
routes/templates/          Leaflet preview
scripts/                   Geography setup, benchmark, real-provider smoke test
data/                      Data instructions; private files ignored
docs/                      Decisions, evidence, demonstration
postman/                   Importable requests and environment
```

## Deployment and limitations

The private GitHub repository hosts the source; it is not a deployed HTTP service.
For a local WSGI demo, use `waitress-serve --listen=127.0.0.1:8000 config.wsgi:application`.
Before exposing a service, set `DJANGO_DEBUG=false`, a generated `DJANGO_SECRET_KEY`,
allowed hosts, HTTPS redirect/secure-cookie flags, and a TLS reverse proxy. Protect
the endpoint with authentication and infrastructure rate limits to prevent strangers
from consuming the ORS quota. The included DRF throttle is only a local demo limit.
Run `python manage.py check --deploy` in the deployment environment and resolve its
relevant findings. No cloud service or paid resources are provisioned by this repo.

The ORM and migrations avoid SQLite-specific spatial extensions. PostgreSQL can be
configured with Django's standard database settings and a psycopg dependency, but
PostgreSQL integration has not been tested. Schedule imports serially on SQLite;
its write locking differs from PostgreSQL's row locks.

Highest-value improvements: reviewed truck-stop coordinates, actual road access
and detour distances with a larger routing budget, price timestamps, wider place
name coverage, shared caching, and live load testing. No global cheapest-driving-route
or real-road range guarantee is made. Keep the repository private until its owner
explicitly approves public visibility.

## References

[Django releases](https://www.djangoproject.com/download/),
[DRF release notes](https://www.django-rest-framework.org/community/release-notes/),
[ORS request/response documentation](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types),
[ORS FAQ](https://giscience.github.io/openrouteservice/frequently-asked-questions).

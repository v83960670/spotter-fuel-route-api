# Verification record

Verified locally on 14 October 2026 (Asia/Kolkata), Windows, Python 3.14.6,
Django 6.1.2, DRF 3.18.3. This is a record of observed checks, not a claim that
all deployment environments or real-world routes have been tested.

## Automated checks

- 70 automated tests passed; no failures or skips in the completed full run.
- Application statement coverage: 97%, excluding test code and migrations.
- Includes an independent exhaustive fuel-state dynamic program used against 500
  seeded cases, not merely assertions copied from the production algorithm.
- Includes the complete CSV import → offline enrichment → HTTP provider mock →
  geometry matching → optimizer → JSON API path. Only the outbound HTTP transport
  is mocked in that integration test.
- Ruff lint and format checks passed.
- Django system checks passed; no pending model migration changes.
- Migrations applied successfully to SQLite.
- A subsequent focused run of all six matching/integration tests passed after
  vectorizing geometry calculations; the full suite was then rerun for release.

The local sandbox required a workspace temporary directory for pytest. To repeat
in a similarly restricted environment, create `artifacts/`, then use a fresh path:

```sh
pytest -q --basetemp=artifacts/pytest-review --cov=routes --cov-report=term-missing
```

Do not point `--basetemp` at a directory containing valuable files; pytest owns it.
Normal development and CI can use plain `pytest`.

## Actual assessment data

The original file was located in the user's Downloads folder and copied into
ignored `data/private/`. The importer processed it directly:

| Measurement | Observed count |
|---|---:|
| Source rows | 8,151 |
| Canadian/provincial rows filtered | 620 |
| Unique US station records imported | 6,626 |
| Redundant US rows collapsed | 905 |
| Exact duplicate rows | 26 |
| Identifier groups with conflicting prices | 487 |
| Conflicting-location identifiers | 0 |
| Invalid rows rejected | 0 |
| Stations resolved to city coordinates | 5,980 |
| Stations left unresolved | 646 |
| Verified exact station coordinates supplied | 0 |

Exact duplicate and price-conflict statistics are separate diagnostic counts,
not mutually exclusive partitions of the 905 redundant rows. City coverage is
90.25%; this is place-name coverage, not verified truck-stop accuracy. Prices with
eight decimals are retained, with a regression test for `3.00733333`.

Census boundary data downloaded successfully. An actual-boundary smoke check
accepted Chicago (IL), Denver (CO), Honolulu (HI), and Anchorage (AK), and rejected
Toronto and a Mexican coordinate. Automated unit tests use synthetic polygons so
the suite does not depend on a geographic download or the network.

## Performance

See [BENCHMARK_RESULTS.json](BENCHMARK_RESULTS.json) for measured samples. The
benchmark uses 8,151 synthetic stations deliberately near a 1,501-point synthetic
geometry, an isolated in-memory database, and a mocked directions provider. The
recorded final cold median is 1,123.016 ms and warm median 21.158 ms. The optimizer
alone handles 10,000 ordered candidate inputs in a median of 102.425 ms.

Five cold plus five warm API requests made exactly five calls to the mocked
provider. No external routing calls were made by this benchmark. These are local
single-process measurements, not a production throughput or live latency claim.

## Server and live integration

The app was started with Waitress on localhost. The database-backed health endpoint
responded, and the Leaflet page loaded in the browser. Missing credentials first
produced the expected structured 503 response. The owner then configured their
ORS key in the ignored `.env`; its value was never printed or committed.

**Live ORS routing passed** using the actual imported assessment data and explicit
city-coordinate approximation mode:

| Route from Chicago | Road miles | Fuel stops | On-route purchases | Cold total | Warm total |
|---|---:|---:|---:|---:|---:|
| Milwaukee | 93.2172 | 0 | $0.00 | 1,225.774 ms | 12.766 ms |
| Denver | 1,003.2918 | 2 | $146.07 | 4,318.051 ms | 12.982 ms |
| Los Angeles | 2,016.0987 | 9 | $466.08 | 2,895.546 ms | 67.099 ms |

Each first request made exactly one directions call; each repeated request made
zero. These are individual observations, not averaged live benchmarks. The first
Denver request included initial loading of the offline place-name index. No initial
fuel price was supplied, so total trip cost is correctly null; the table reports
only purchases. Road routes are real, but station positions and detour feasibility
remain approximate. Full local responses are saved in ignored `artifacts/`.

The browser rendered the real Chicago–Denver geometry, start/finish markers, two
numbered fuel markers, purchase quantities, and explicit approximation warnings.
The tile integration uses the required OSM URL and an origin-sending referrer policy.
No Loom video has been recorded; the provided script is ready for the owner to record.

No public cloud HTTP deployment, PostgreSQL run, or concurrent load test is claimed.
GitHub hosts the source privately; it does not serve the Django API.

## Review and remaining limits

A separate review pass checked range invariants, FIFO starting-fuel accounting,
Decimal rounding, source-row preservation, importer atomicity, coordinate provenance,
provider credential handling, cache versioning, and double-back projection behavior.
The review added eight-decimal price preservation, rejected non-finite and boolean
inputs, and added a complete import-to-API integration test. The map inserts station
text using `textContent`, not unescaped station HTML.

The major remaining limitation is geographic certainty: 90.25% city matching is
useful for an explicitly approximate assessment demonstration but is not station
access validation. Detour consumption can make a mathematically feasible plan
infeasible on the road. The API prominently discloses this. Reviewed station
entrances and routed detours are the highest-value next improvements.

## Assessment self-review: 90/100

| Category | Score | Evidence / deduction |
|---|---:|---|
| API correctness and validation | 15/15 | Typed inputs, structured errors, automated integration and three live routes |
| Fuel optimization and range | 18/20 | Exhaustive reference agreement; real detour feasibility is unverified |
| Data processing and geolocation | 11/15 | Actual dataset imported and traceable; only city fallback coordinates available |
| Routing efficiency and performance | 14/15 | One call/cold and zero/warm measured live; no concurrent load measurements |
| Code and architecture | 9/10 | Modular services and clean checks; per-process cache remains a scaling limit |
| Automated tests | 9/10 | 70 tests, 97% statement coverage and live smoke checks; no PostgreSQL run |
| Map and usability | 5/5 | Real road geometry, numbered fuel markers, purchase amounts and warnings rendered |
| Documentation | 5/5 | Reproducible setup, sources, accounting, limitations and evidence |
| Submission materials | 4/5 | Private repo, Postman and Loom script; actual recording not completed |

This is not a claim of a hiring-team grade. Missing exact station evidence and
unmeasured road detours prevent an honest 95+/100 claim.

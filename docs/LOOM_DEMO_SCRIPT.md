# Walkthrough — target 4 minutes 45 seconds

Record only after `scripts/live_smoke.py` succeeds with the real ORS key and
assessment CSV. If live routing is blocked, say so and show the mocked test suite;
do not present a synthetic geometry as a driving route.

**0:00–0:25 — What it does**

“This API takes two US locations and estimates fuel purchases along the driving
route returned by openrouteservice. The defaults are a 500-mile range, 10 miles
per gallon, and a full 50-gallon tank. I kept the web layer small and separated
data import, station matching, and fuel optimization.”

**0:25–1:20 — API and map**

Open the Postman collection. Send the health check, then Chicago to Denver.
Show the actual distance, GeoJSON, stop list, and `metrics`. Enter the same route
in the map preview. Open a numbered fuel marker and show the purchase amount.

“These stops come from the imported price file. The location precision is included
for each stop. With approximate mode enabled, a city coordinate is only a fallback;
it does not establish the station entrance or its road access.”

Use the long-route request to show multiple stops, **after verifying that this
specific route has a feasible plan with the current data**. If it does not, show
the actionable failure and use the multi-stop automated test to explain the logic.

**1:20–2:15 — Why these purchases**

Open `routes/services/optimizer.py` and the multi-stop test.

“At each station, the planner looks for a cheaper station ahead. If it is reachable,
it buys only enough to get there. Otherwise, it fills only as far as useful for the
remaining journey. The algorithm minimizes purchase cost along this fixed route
under the zero-detour model; it does not search for the cheapest road route.”

Show the 1,300-mile synthetic test: $290 purchases, 80 gallons purchased, 130 consumed.
With $4 starting fuel, total consumed-fuel cost is $490. Label this example synthetic.
Explain that no initial price means a null total cost, not free initial fuel.

**2:15–3:10 — Import and geometry**

Show the import report and enrichment coverage. Explain maximum conflicting price,
row traceability, US filtering, and unresolved stations. Show the STRtree segment
matching, projected progress, and rejection of ambiguous double-back projections.

“Off-route distance is geometric, not a measured road detour. This is why the API
returns warnings and calls the fueling plan an estimate.”

**3:10–3:50 — Calls and performance**

Repeat the Postman request and show zero directions calls on the cache hit.
Show `docs/BENCHMARK_RESULTS.json`, identifying it as a local synthetic benchmark
with the provider mocked. Do not compare these times to live-network performance.

**3:50–4:45 — Verification and limitations**

Run the test suite. Show the independent dynamic-programming reference test and
provider error tests. Mention geographic approximations, stale prices, local
per-process caching, and the need for reviewed exact coordinates and measured
detours before real operational use. Finish on the private GitHub repository.

## Recording checklist

- Keep `.env`, provider dashboard, and API keys out of the recording.
- Confirm real CSV imported and coordinate coverage understood.
- Explicitly opt into city approximation, or import reviewed exact coordinates.
- Run migrations, tests, and live smoke first.
- Import the Postman environment; set its base URL.
- Confirm short and long routes before recording; do not improvise a successful result.
- Keep browser internet access available for Leaflet and map tiles.
- Keep the repository private until its owner approves public visibility.

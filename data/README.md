# Fuel data and coordinate evidence

Place the supplied `fuel-prices-for-be-assessment.csv` in `data/private/`.
That directory, the SQLite database, and downloaded geographic data are ignored by Git.
The assessment CSV is not redistributed because no redistribution license was supplied.

Import a complete snapshot, then enrich it:

```sh
python manage.py import_fuel_prices data/private/fuel-prices-for-be-assessment.csv
python scripts/setup_geography.py
python manage.py enrich_stations --coordinates data/private/station-coordinates.csv
```

The coordinate CSV must have these columns:

```csv
source_id,latitude,longitude,source,precision,confidence
```

Use the station's actual OPIS identifier. `source` must identify the evidence/provider
and preferably a retrieval date or review reference. `precision` is `station` or
`city`; `confidence` is `high`, `medium`, or `low`. Station precision is an assertion
by the data curator, not an accuracy guarantee made by the importer. Coordinates
must be finite and inside the CSV's state. Duplicate and unknown identifiers are
rejected atomically. Acquire and use enrichment data under its provider's license.

For an explicit approximate assessment demonstration:

```sh
python manage.py enrich_stations --allow-city-fallback
```

Also set `ALLOW_APPROXIMATE_STATIONS=true` in `.env`. Both steps are deliberate:
enrichment alone does not enable city centroids in the planner. GeoNames place
coverage includes populated places with at least 500 inhabitants; missing and
ambiguous names remain unresolved. No coordinates are invented. No station
geocoding calls occur in route requests. Reviewed exact coordinates take precedence.

Imports preserve source row numbers (header is row 1), rack identifiers, and all
observed prices. Exact duplicates are collapsed. For a repeated identifier with
the same normalized address, the **maximum observed price** is selected
conservatively; it is not asserted to be the newest. Identifiers with conflicting
locations are quarantined. Import reports count exact duplicate rows and conflicting
price groups separately; those diagnostic counts can overlap. A new file replaces
the active snapshot atomically and removes absent stations. Empty/invalid snapshots
do not replace data. Coordinates survive only while the normalized address is unchanged.

Every successful data or enrichment change rotates the cache version. Reimporting
identical bytes is a no-op. Reapplying a reviewed coordinate file safely rotates the
version even if values are unchanged; city-fallback-only reruns are no-ops.

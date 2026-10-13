# Data sources and licenses

- Fuel prices: supplied Spotter assessment CSV. No timestamps or redistribution
  license were supplied. Keep it in `data/private/`; do not commit it.
- City coordinates: [GeoNames](https://www.geonames.org/export/), distributed by
  the pinned `geonamescache` package. GeoNames data is licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). We match US primary
  place names plus state, record the GeoNames identifier, and label results as
  city-level, low-confidence station approximations.
- US boundaries: [US Census Bureau cartographic boundary files](https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html),
  2024, 1:500,000 state polygons. Downloaded from the Census HTTPS server by
  `scripts/setup_geography.py`. Federal government geographic data; attribution:
  U.S. Census Bureau. Cartographic boundaries are generalized and can reject
  legitimate shoreline/border points. They are not cadastral or navigational data.
  NAD83 coordinates are treated as WGS84 at this application's kilometer-scale
  matching resolution; meter-scale datum differences are below that precision.
- Driving routes: [openrouteservice by HeiGIT](https://openrouteservice.org/),
  based on OpenStreetMap. Respect provider terms and quotas.
- Preview tiles: OpenStreetMap contributors, [ODbL attribution](https://www.openstreetmap.org/copyright).
  Follow the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
  The preview is for interactive demonstrations, not bulk downloading.

No station coordinates in automated test fixtures represent verified real fuel
stations. Synthetic fixtures are labeled in the test and demonstration scripts.

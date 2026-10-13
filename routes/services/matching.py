from decimal import Decimal

import numpy as np
import shapely
from pyproj import CRS, Geod, Transformer
from shapely.geometry import LineString
from shapely.strtree import STRtree

from routes.models import Station
from routes.services.optimizer import FuelPoint
from routes.services.provider import METERS_PER_MILE, RoadRoute

GEOD = Geod(ellps="WGS84")


def match_stations(
    route: RoadRoute, corridor_miles: float, allow_approximate: bool
) -> tuple[list[FuelPoint], dict, list[str]]:
    coords = route.coordinates
    lons, lats = zip(*coords, strict=True)
    # US requests, including Alaska/Hawaii, use a route-centered local projection.
    projection = CRS.from_proj4(
        f"+proj=aeqd +lat_0={sum(lats) / len(lats)} +lon_0={sum(lons) / len(lons)} +datum=WGS84 +units=m"
    )
    transform = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
    xy = [transform.transform(*c) for c in coords]
    segments, cumulative, lengths = [], [], []
    total = 0.0
    for i in range(len(coords) - 1):
        length = GEOD.inv(*coords[i], *coords[i + 1])[2]
        if length <= 0:
            continue
        segment = LineString([xy[i], xy[i + 1]])
        segments.append(segment)
        cumulative.append(total)
        lengths.append(length)
        total += length
    if not segments:
        return [], {}, []
    tree = STRtree(segments)
    radius = corridor_miles * float(METERS_PER_MILE)
    # Conservative bounding-box prefilter; exact projected filtering follows.
    queryset = Station.objects.filter(
        latitude__gte=min(lats) - 1,
        latitude__lte=max(lats) + 1,
        longitude__gte=min(lons) - 3,
        longitude__lte=max(lons) + 3,
    )
    queryset = queryset.filter(
        precision__in=["station", "city"] if allow_approximate else ["station"]
    )
    points, metadata, ambiguous = [], {}, 0
    queryset = queryset.filter(longitude__isnull=False).only(
        "source_id",
        "name",
        "city",
        "state",
        "latitude",
        "longitude",
        "price",
        "precision",
        "confidence",
        "coordinate_source",
    )
    stations = list(queryset)
    if not stations:
        return [], {}, []
    x, y = transform.transform([s.longitude for s in stations], [s.latitude for s in stations])
    station_points = shapely.points(x, y)
    nearest_indices, nearest_offsets = tree.query_nearest(
        station_points, max_distance=radius, return_distance=True, all_matches=False
    )
    if nearest_indices.size == 0:
        return [], {}, []
    matched_ids = nearest_indices[0]
    # Run geometry operations in GEOS batches. Only near-ties can change a match;
    # projecting every segment in the full corridor is much more expensive.
    local_ids, segment_ids = tree.query(
        station_points[matched_ids],
        predicate="dwithin",
        distance=np.minimum(radius, nearest_offsets + 100),
    )
    candidate_segments = tree.geometries[segment_ids]
    candidate_points = station_points[matched_ids[local_ids]]
    offsets = shapely.distance(candidate_segments, candidate_points)
    fractions = shapely.line_locate_point(candidate_segments, candidate_points, normalized=True)
    progresses = (
        np.asarray(cumulative)[segment_ids] + np.asarray(lengths)[segment_ids] * fractions
    ) / total
    matches = [[] for _ in matched_ids]
    for local_id, offset, progress in zip(local_ids, offsets, progresses, strict=True):
        matches[local_id].append((float(offset), float(progress)))
    for station_id, hits in zip(matched_ids, matches, strict=True):
        station = stations[station_id]
        # Nearby parallel roads and returning segments cannot establish road access.
        # Reject projections with materially different progress instead of guessing.
        best_offset, progress = min(hits)
        plausible = [p for offset, p in hits if offset <= best_offset + 100]
        if (max(plausible) - min(plausible)) * float(route.distance_miles) > 2:
            ambiguous += 1
            continue
        mile = route.distance_miles * Decimal(str(progress))
        if mile >= route.distance_miles:
            continue
        points.append(FuelPoint(station.source_id, mile, station.price))
        metadata[station.source_id] = {
            "source_id": station.source_id,
            "name": station.name,
            "city": station.city,
            "state": station.state,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "price_per_gallon": str(station.price),
            "precision": station.precision,
            "confidence": station.confidence,
            "coordinate_source": station.coordinate_source,
            "off_route_miles": round(best_offset / float(METERS_PER_MILE), 3),
        }
    warnings = (
        [f"Excluded {ambiguous} stations with ambiguous route projections."] if ambiguous else []
    )
    return points, metadata, warnings

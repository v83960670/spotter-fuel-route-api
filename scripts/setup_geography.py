"""Download Census cartographic boundaries once, outside the request pipeline."""

import io
import json
import zipfile
from pathlib import Path

import httpx
import shapefile

URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip"
ROOT = Path(__file__).resolve().parent.parent
STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def main():
    response = httpx.get(URL, timeout=120, follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:

        def part(extension):
            name = next(n for n in archive.namelist() if n.endswith(extension))
            return io.BytesIO(archive.read(name))

        reader = shapefile.Reader(shp=part(".shp"), shx=part(".shx"), dbf=part(".dbf"))
        features = []
        for record in reader.iterShapeRecords():
            state = record.record.as_dict()["STUSPS"]
            if state in STATES:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"state": state},
                        "geometry": record.shape.__geo_interface__,
                    }
                )
    if len(features) != 51:
        raise RuntimeError("Expected 50 states and DC; refusing incomplete boundary data.")
    target = ROOT / "data/us_states.geojson"
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"type": "FeatureCollection", "source": URL, "features": features},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(target)
    print(f"Installed {len(features)} state boundaries ({target.stat().st_size:,} bytes).")


if __name__ == "__main__":
    main()

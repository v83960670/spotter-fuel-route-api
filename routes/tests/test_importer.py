import csv
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from routes.models import Dataset, Station
from routes.services.importer import COLUMNS, import_prices

pytestmark = pytest.mark.django_db


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(identifier="1", **updates):
    return {
        "OPIS Truckstop ID": identifier,
        "Truckstop Name": " Demo Fuel ",
        "Address": "1 Main St",
        "City": " CHICAGO ",
        "State": " il ",
        "Rack ID": "A",
        "Retail Price": "3.12345",
        **updates,
    }


def test_normalization_conflicts_exclusions_and_traceability(tmp_path):
    path = write_csv(
        tmp_path / "fuel.csv",
        [
            row(),
            row(),
            row(**{"Retail Price": "4.0"}),
            row("2", State="ON"),
            row("3", **{"Retail Price": "-1"}),
            row("4", **{"Retail Price": "NaN"}),
        ],
    )
    report = import_prices(path)
    assert {
        k: report[k]
        for k in [
            "rows",
            "imported",
            "filtered",
            "rejected",
            "exact_duplicates",
            "conflicting_prices",
        ]
    } == dict(rows=6, imported=1, filtered=1, rejected=2, exact_duplicates=1, conflicting_prices=1)
    station = Station.objects.get()
    assert (station.city, station.state, station.price) == ("Chicago", "IL", Decimal("4.0"))
    assert [r["row"] for r in station.source_rows] == [2, 3, 4]
    version = Dataset.objects.get().version
    assert import_prices(path)["unchanged"]
    assert Dataset.objects.get().version == version


def test_bad_snapshot_does_not_destroy_existing_data(tmp_path):
    import_prices(write_csv(tmp_path / "good.csv", [row()]))
    with pytest.raises(ValueError):
        import_prices(write_csv(tmp_path / "bad.csv", [row(State="ON")]))
    assert Station.objects.count() == 1
    (tmp_path / "bad.csv").write_text("Wrong,Header\n1,2\n")
    with pytest.raises(ValueError, match="Missing CSV columns"):
        import_prices(tmp_path / "bad.csv")


def test_location_conflicts_quarantined(tmp_path):
    report = import_prices(
        write_csv(tmp_path / "fuel.csv", [row(), row(Address="different"), row("2")])
    )
    assert report["ambiguous_ids"] == 1
    assert list(Station.objects.values_list("source_id", flat=True)) == ["2"]


def test_snapshot_removes_stale_stations_and_preserves_valid_coordinates(tmp_path):
    path = write_csv(tmp_path / "fuel.csv", [row(), row("2")])
    import_prices(path)
    Station.objects.filter(source_id="1").update(
        latitude=41.85, longitude=-87.65, precision="station"
    )
    old_version = Dataset.objects.get().version
    write_csv(path, [row(**{"Retail Price": "4"})])
    import_prices(path)
    assert Station.objects.get().latitude == 41.85
    assert Dataset.objects.get().version != old_version
    write_csv(path, [row(Address="new address")])
    import_prices(path)
    assert Station.objects.get().latitude is None


def test_offline_city_enrichment_is_explicit_and_idempotent(tmp_path):
    import_prices(write_csv(tmp_path / "fuel.csv", [row(), row("2", City="UnfindableCity")]))
    call_command("enrich_stations")
    assert Station.objects.filter(latitude__isnull=False).count() == 0
    call_command("enrich_stations", allow_city_fallback=True)
    station = Station.objects.get(source_id="1")
    assert station.precision == "city" and station.confidence == "low"
    assert station.coordinate_source.startswith("GeoNames:")
    assert Station.objects.get(source_id="2").precision == "unresolved"
    version = Dataset.objects.get().version
    call_command("enrich_stations", allow_city_fallback=True)
    assert Dataset.objects.get().version == version


def test_enrichment_without_data_errors():
    with pytest.raises(CommandError):
        call_command("enrich_stations")


def test_eight_decimal_prices_from_assessment_are_preserved(tmp_path):
    import_prices(write_csv(tmp_path / "fuel.csv", [row(**{"Retail Price": "3.00733333"})]))
    assert Station.objects.get().price == Decimal("3.00733333")


def test_management_command_and_report(tmp_path):
    path = write_csv(tmp_path / "fuel.csv", [row()])
    report = tmp_path / "report.json"
    call_command("import_fuel_prices", str(path), report=report)
    assert report.exists()
    with pytest.raises(CommandError):
        call_command("import_fuel_prices", str(tmp_path / "missing.csv"))


def test_reviewed_coordinate_file_and_atomic_rejection(tmp_path, monkeypatch):
    import_prices(write_csv(tmp_path / "fuel.csv", [row(), row("2")]))
    monkeypatch.setattr(
        "routes.management.commands.enrich_stations.state_at", lambda lat, lon: "IL"
    )
    path = tmp_path / "coordinates.csv"
    header = "source_id,latitude,longitude,source,precision,confidence\n"
    path.write_text(header + "1,41.85,-87.65,review-fixture,station,high\n")
    call_command("enrich_stations", coordinates=str(path))
    assert Station.objects.get(source_id="1").precision == "station"
    path.write_text(
        header + "2,41.85,-87.65,review-fixture,station,high\nmissing,41,-87,fixture,station,high\n"
    )
    with pytest.raises(CommandError):
        call_command("enrich_stations", coordinates=str(path))
    assert Station.objects.get(source_id="2").latitude is None

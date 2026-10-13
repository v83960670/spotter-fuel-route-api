import csv
import hashlib
import io
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from routes.models import Dataset, Station
from routes.services.locations import US_STATES, normalize

COLUMNS = {
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
}


def import_prices(path: Path) -> dict:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not COLUMNS.issubset(reader.fieldnames or []):
        raise ValueError(
            f"Missing CSV columns: {', '.join(sorted(COLUMNS - set(reader.fieldnames or [])))}"
        )
    report = {
        "importer_version": 2,
        "rows": 0,
        "imported": 0,
        "filtered": 0,
        "rejected": 0,
        "exact_duplicates": 0,
        "conflicting_prices": 0,
        "ambiguous_ids": 0,
        "rejected_rows": [],
    }
    groups = {}
    fingerprints = set()
    for number, raw in enumerate(reader, start=2):
        report["rows"] += 1
        row = {k: " ".join((raw.get(k) or "").split()) for k in COLUMNS}
        row["State"] = row["State"].upper()
        if row["State"] not in US_STATES:
            report["filtered"] += 1
            continue
        try:
            price = Decimal(row["Retail Price"])
            if (
                not price.is_finite()
                or price <= 0
                or price >= 100
                or price.as_tuple().exponent < -8
            ):
                raise ValueError("Price must be positive, below 100, with at most eight decimals.")
            for key, limit in [
                ("OPIS Truckstop ID", 64),
                ("Truckstop Name", 255),
                ("Address", 500),
                ("City", 128),
            ]:
                if not row[key] or len(row[key]) > limit:
                    raise ValueError(f"Invalid {key}.")
        except (InvalidOperation, ValueError) as exc:
            report["rejected"] += 1
            report["rejected_rows"].append({"row": number, "reason": str(exc)})
            continue
        fingerprint = tuple(normalize(row[k]) for k in sorted(COLUMNS))
        if fingerprint in fingerprints:
            report["exact_duplicates"] += 1
        fingerprints.add(fingerprint)
        groups.setdefault(row["OPIS Truckstop ID"], []).append((number, row, price))
    records = []
    for source_id, entries in sorted(groups.items()):
        addresses = {
            (normalize(r["Address"]), normalize(r["City"]), r["State"]) for _, r, _ in entries
        }
        if len(addresses) != 1:
            report["ambiguous_ids"] += 1
            report["rejected"] += len(entries)
            report["rejected_rows"].extend(
                {"row": n, "reason": "Identifier has conflicting locations."} for n, _, _ in entries
            )
            continue
        if len({p for _, _, p in entries}) > 1:
            report["conflicting_prices"] += 1
        # No timestamps exist. The maximum observed price is conservative, not 'latest'.
        _, chosen, price = max(entries, key=lambda entry: (entry[2], -entry[0]))
        records.append(
            Station(
                source_id=source_id,
                name=chosen["Truckstop Name"],
                address=chosen["Address"],
                city=chosen["City"].title(),
                state=chosen["State"],
                price=price,
                source_rows=[
                    {"row": n, "rack_id": r["Rack ID"], "price": str(p)} for n, r, p in entries
                ],
            )
        )
    report["imported"] = len(records)
    if not records:
        raise ValueError("No valid US stations; active dataset was not replaced.")
    with transaction.atomic():
        dataset, _ = Dataset.objects.select_for_update().get_or_create(
            id=1, defaults={"source_sha256": ""}
        )
        if dataset.source_sha256 == digest and dataset.report.get("importer_version") == 2:
            return {**dataset.report, "unchanged": True}
        existing = {s.source_id: s for s in Station.objects.all()}
        for station in records:
            old = existing.get(station.source_id)
            if old and (normalize(old.address), normalize(old.city), old.state) == (
                normalize(station.address),
                normalize(station.city),
                station.state,
            ):
                for field in (
                    "latitude",
                    "longitude",
                    "coordinate_source",
                    "precision",
                    "confidence",
                ):
                    setattr(station, field, getattr(old, field))
        Station.objects.all().delete()
        Station.objects.bulk_create(records, batch_size=500)
        dataset.source_sha256, dataset.version, dataset.report = digest, uuid.uuid4(), report
        dataset.save()
    return report

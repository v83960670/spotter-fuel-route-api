import uuid

from django.db import models


class Dataset(models.Model):
    """The single active price snapshot; imports swap it atomically."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    version = models.UUIDField(default=uuid.uuid4)
    source_sha256 = models.CharField(max_length=64)
    report = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class Station(models.Model):
    source_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=8)
    source_rows = models.JSONField(default=list)
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    coordinate_source = models.CharField(max_length=500, blank=True)
    precision = models.CharField(max_length=20, default="unresolved")
    confidence = models.CharField(max_length=20, default="unknown")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gt=0), name="positive_station_price")
        ]

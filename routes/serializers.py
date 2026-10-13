from decimal import Decimal

from rest_framework import serializers


class CoordinatesSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)

    def validate(self, attrs):
        import math

        if set(self.initial_data) != {"latitude", "longitude"} or any(
            isinstance(v, bool) for v in self.initial_data.values()
        ):
            raise serializers.ValidationError("Supply only numeric latitude and longitude.")
        if not all(math.isfinite(v) for v in attrs.values()):
            raise serializers.ValidationError("Coordinates must be finite.")
        return attrs


class LocationField(serializers.Field):
    def to_internal_value(self, value):
        if isinstance(value, str) and 1 <= len(value.strip()) <= 200:
            return " ".join(value.split())
        if isinstance(value, dict):
            serializer = CoordinatesSerializer(data=value)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        raise serializers.ValidationError("Use 'City, ST' or {latitude, longitude}.")


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField()
    finish = LocationField()
    mpg = serializers.DecimalField(
        max_digits=7,
        decimal_places=3,
        min_value=Decimal("0.1"),
        max_value=Decimal("100"),
        default=Decimal("10"),
    )
    max_range_miles = serializers.DecimalField(
        max_digits=8,
        decimal_places=3,
        min_value=Decimal("1"),
        max_value=Decimal("2000"),
        default=Decimal("500"),
    )
    initial_fuel_gallons = serializers.DecimalField(
        max_digits=10, decimal_places=4, min_value=Decimal("0"), required=False
    )
    initial_fuel_price = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=Decimal("100"),
        required=False,
    )

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
        capacity = attrs["max_range_miles"] / attrs["mpg"]
        attrs.setdefault("initial_fuel_gallons", capacity)
        if attrs["initial_fuel_gallons"] > capacity:
            raise serializers.ValidationError({"initial_fuel_gallons": "Exceeds tank capacity."})
        return attrs


class RouteResponseSerializer(serializers.Serializer):
    start = serializers.DictField()
    finish = serializers.DictField()
    distance_miles = serializers.CharField()
    duration_seconds = serializers.FloatField()
    geometry = serializers.JSONField()
    fuel_stops = serializers.ListField(child=serializers.DictField())
    fuel = serializers.DictField()
    optimization = serializers.DictField()
    warnings = serializers.ListField(child=serializers.CharField())
    dataset_version = serializers.CharField()
    metrics = serializers.DictField()
    map_preview_url = serializers.CharField()

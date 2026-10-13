from django.urls import path

from routes.api.views import health, map_preview, optimize

urlpatterns = [
    path("api/v1/health/", health),
    path("api/v1/routes/optimize/", optimize),
    path("", map_preview, name="map-preview"),
]

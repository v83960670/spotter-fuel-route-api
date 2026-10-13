import os

os.environ.setdefault("DJANGO_DEBUG", "true")

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clean_cache(settings):
    cache.clear()
    settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": "10000/min"}
    yield
    cache.clear()

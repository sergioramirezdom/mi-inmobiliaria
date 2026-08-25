"""Regression test: Mobilia scraper must not stamp a fake
`fecha_publicacion` — the field is now authoritative for the real
publication date; a scrape-time value would defeat the listing-date
resolver (app/listing_date.py)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.mobilia_scraper import MobiliaScraper

DETAIL_URL = "https://www.mobiliagestion.es/ficha/piso/123456/"

MINIMAL_HTML = """
<html><head><title>Piso en venta</title></head>
<body>
  <span class="IDPrecioBig">150.000 €</span>
</body></html>
"""


@pytest.mark.asyncio
async def test_scrape_property_details_does_not_set_fecha_publicacion():
    scraper = MobiliaScraper()
    scraper.fetch_content = AsyncMock(return_value=MINIMAL_HTML)
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["titulo"] == "Piso en venta"
    assert "fecha_publicacion" not in data

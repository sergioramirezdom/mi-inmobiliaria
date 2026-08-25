"""Regression test: Puerto Inmobiliaria scraper must not stamp a fake
`fecha_publicacion` — the field is now authoritative for the real
publication date; a scrape-time value would defeat the listing-date
resolver (app/listing_date.py)."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.puerto_inmobiliaria import PuertoInmobiliariaScraper

DETAIL_URL = "https://www.puertoinmobiliaria.es/ficha/piso/123456/es/"

MINIMAL_FICHA_HTML = """
<html><body>
  <h1>Piso en venta</h1>
  <div class="fichapropiedad-precio">150.000 €</div>
  <section id="fichapropiedad-bloquedescripcion">Bonito piso.</section>
</body></html>
"""


@pytest.mark.asyncio
async def test_scrape_property_details_does_not_set_fecha_publicacion():
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(return_value=(MINIMAL_FICHA_HTML, DETAIL_URL))
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["titulo"] == "Piso en venta"
    assert "fecha_publicacion" not in data

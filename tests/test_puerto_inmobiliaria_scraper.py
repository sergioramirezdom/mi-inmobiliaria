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


@pytest.mark.asyncio
async def test_homepage_redirect_does_not_force_immediate_deactivation():
    """Regression for the 2026-08-26 incident: 12 unrelated listings redirected
    to the homepage in one sold-check run (site rate-limiting/anti-bot), and
    were deactivated immediately since GONE skips the strike counter. All 12
    were confirmed still live by hand. The redirect is now an inferred signal
    (EMPTY-shaped return, no "activa" key) so classify_check_outcome() routes
    it through the same 2-strike confirmation as a no-data scrape result."""
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(
        return_value=("<html><body>Home</body></html>", "https://www.puertoinmobiliaria.es")
    )
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert "activa" not in data
    assert not data.get("titulo")
    assert not data.get("precio")


@pytest.mark.asyncio
async def test_page_without_ficha_markers_does_not_force_immediate_deactivation():
    """Same protection as the homepage-redirect case above, for the sibling
    heuristic: a 200 response whose HTML has none of the known ficha selectors."""
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(
        return_value=("<html><body>Not a listing page</body></html>", DETAIL_URL)
    )
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert "activa" not in data
    assert not data.get("titulo")
    assert not data.get("precio")

"""Regression test: Mobilia scraper must not stamp a fake
`fecha_publicacion` — the field is now authoritative for the real
publication date; a scrape-time value would defeat the listing-date
resolver (app/listing_date.py)."""
import os
import sys
from pathlib import Path
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


FICHA_HTML = (Path(__file__).parent / "fixtures" / "mobilia_ficha.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_scrape_property_details_reads_price_and_areas_containing_a_two():
    scraper = MobiliaScraper()
    scraper.fetch_content = AsyncMock(return_value=FICHA_HTML)
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["precio"] == 225000.0
    assert data["superficie_m2"] == 72.5
    assert data["superficie_util_m2"] == 62.0
    assert data["habitaciones"] == 3
    assert data["banos"] == 2


@pytest.mark.asyncio
async def test_scrape_property_details_keeps_price_without_a_two():
    scraper = MobiliaScraper()
    scraper.fetch_content = AsyncMock(return_value=MINIMAL_HTML)
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["precio"] == 150000.0


@pytest.mark.parametrize(
    "text, expected",
    [
        ("150.000", 150000.0),
        ("225.000", 225000.0),
        ("220.000", 220000.0),
        ("120.000", 120000.0),
        ("72,5", 72.5),
        ("82", 82.0),
        ("1.234,5", 1234.5),
        ("72 m²", 72.0),
    ],
)
def test_parse_float_keeps_every_digit(text, expected):
    assert MobiliaScraper()._parse_float(text) == expected

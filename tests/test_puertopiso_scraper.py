"""PuertoPiso detail scraper: area, price, amenity and description extraction
(respx-mocked; coordinates are covered in test_puertopiso_coords.py)."""
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.puertopiso_scraper import PuertoPisoScraper

DETAIL_URL = "https://www.puertopiso.com/buscador/inmueble.php?id=29183740"
FICHA_HTML = (Path(__file__).parent / "fixtures" / "puertopiso_ficha.html").read_text(encoding="utf-8")

_PAGE = """
<html><body>
  <div class="uno"><h4>Piso en El Puerto</h4><h4>{price}</h4></div>
  <div class="column_attr">{body}</div>
</body></html>
"""


def _page(body: str = "", price: str = "150.000€") -> str:
    return _PAGE.format(body=body, price=price)


async def _scrape(html: str) -> dict:
    with respx.mock:
        respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=html))
        return await PuertoPisoScraper().scrape_property_details(DETAIL_URL)


@pytest.mark.asyncio
async def test_fixture_ficha_extracts_price_areas_rooms_and_amenities():
    data = await _scrape(FICHA_HTML)

    assert data["precio"] == 1250000.0
    assert data["superficie_m2"] == 1200.0
    assert data["superficie_util_m2"] == 980.0
    assert data["habitaciones"] == 5
    assert data["banos"] == 3
    assert data["tipo_propiedad"] == "casa"
    assert data["piscina"] is True
    assert "ascensor" not in data
    assert data["descripcion"].startswith("Espectacular casa")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Superficie: 1.200 m2", 1200.0),
        ("Superficie: 69,84 m2", 69.84),
        ("Superficie: 69,84 m²", 69.84),
        ("Superficie: 85 m2", 85.0),
    ],
)
async def test_built_area_parses_thousands_decimals_and_superscript(text, expected):
    data = await _scrape(_page(f"<p>{text}</p>"))

    assert data["superficie_m2"] == expected


@pytest.mark.asyncio
async def test_built_area_is_preferred_over_useful_area():
    data = await _scrape(_page("<p>Superficie útil: 75 m2</p><p>Superficie: 90 m2</p>"))

    assert data["superficie_m2"] == 90.0
    assert data["superficie_util_m2"] == 75.0


@pytest.mark.asyncio
async def test_useful_area_alone_never_becomes_built_area():
    data = await _scrape(_page("<p>Superficie útil: 75 m2</p>"))

    assert "superficie_m2" not in data
    assert data["superficie_util_m2"] == 75.0


@pytest.mark.asyncio
async def test_area_without_digits_is_ignored():
    data = await _scrape(_page("<p>Superficie: , m2</p>"))

    assert "superficie_m2" not in data


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["155.000\xa0€", "155.000 €", "155.000€", "155.000&nbsp;€"])
async def test_price_parses_with_any_kind_of_space(price):
    data = await _scrape(_page(price=price))

    assert data["precio"] == 155000.0


@pytest.mark.asyncio
async def test_price_is_found_when_it_is_not_the_second_h4():
    html = (
        '<html><body><div class="uno"><h4>Piso en El Puerto</h4>'
        "<h4>Ref. 1234</h4><h4>225.000 €</h4></div></body></html>"
    )
    data = await _scrape(html)

    assert data["titulo"] == "Piso en El Puerto"
    assert data["precio"] == 225000.0


@pytest.mark.asyncio
async def test_price_missing_stays_unset():
    html = '<html><body><div class="uno"><h4>Piso</h4><h4>Consultar</h4></div></body></html>'
    data = await _scrape(html)

    assert "precio" not in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        "<p>Sin ascensor</p>",
        "<p>Edificio sin ascensor y sin trastero.</p>",
        "<p>No dispone de ascensor</p>",
        "<p>Vivienda sin plaza de garaje</p>",
    ],
)
async def test_negated_amenities_are_not_set(body):
    data = await _scrape(_page(body))

    for field in ("ascensor", "garaje", "trastero"):
        assert field not in data


@pytest.mark.asyncio
async def test_affirmed_amenities_are_set():
    data = await _scrape(_page("<p>Edificio con ascensor, garaje y terraza. Piscina comunitaria.</p>"))

    assert data["ascensor"] is True
    assert data["garaje"] is True
    assert data["terraza"] is True
    assert data["piscina"] is True


@pytest.mark.asyncio
async def test_mixed_affirmed_and_negated_mention_stays_unset():
    data = await _scrape(_page("<p>Sin ascensor. Cerca hay un edificio con ascensor.</p>"))

    assert "ascensor" not in data


@pytest.mark.asyncio
async def test_description_without_justify_style_is_used_as_fallback():
    text = "Coqueto piso reformado recientemente, con mucha luz natural y a pocos minutos de la playa y del centro."
    data = await _scrape(_page(f"<p>{text}</p>"))

    assert data["descripcion"] == text

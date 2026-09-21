"""Regression test: Puerto Inmobiliaria scraper must not stamp a fake
`fecha_publicacion` — the field is now authoritative for the real
publication date; a scrape-time value would defeat the listing-date
resolver (app/listing_date.py)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from bs4 import BeautifulSoup

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
async def test_scrape_extracts_approximate_coordinates_from_apinmo_blob():
    html = MINIMAL_FICHA_HTML.replace(
        "</body>",
        '<script>var ficha = {"ref":"1355V","latitud":36.576477825,'
        '"altitud":-6.225324919,"precioinmo":390000};</script></body>',
    )
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(return_value=(html, DETAIL_URL))
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["latitud"] == 36.576477825
    assert data["longitud"] == -6.225324919
    assert data["ubicacion_aproximada"] is True


@pytest.mark.asyncio
async def test_scrape_without_coordinates_leaves_location_unset():
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(return_value=(MINIMAL_FICHA_HTML, DETAIL_URL))
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert "latitud" not in data
    assert "ubicacion_aproximada" not in data


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


FICHA_FIXTURE = Path(__file__).parent / "fixtures" / "puerto_inmobiliaria_ficha.html"


def _characteristics(html: str) -> dict:
    scraper = PuertoInmobiliariaScraper()
    return scraper._extract_characteristics(BeautifulSoup(html, "html.parser"))


def _old_structure(*rows: tuple) -> str:
    items = "".join(
        f'<li><span class="caracteristica">{label}</span><span class="valor">{valor}</span></li>'
        for label, valor in rows
    )
    return f'<ul class="fichapropiedad-listadatos">{items}</ul>'


def test_characteristics_fixture_keeps_built_and_useful_area_apart():
    ch = _characteristics(FICHA_FIXTURE.read_text(encoding="utf-8"))

    assert ch["superficie_m2"] == 90.0
    assert ch["superficie_util_m2"] == 75.0
    assert ch["habitaciones"] == 3
    assert ch["banos"] == 2
    assert ch["estado"] == "Buen estado"
    assert ch["precio_comunidad"] == 45.0


def test_plot_area_does_not_overwrite_built_area():
    html = _old_structure(
        ("Superficie construida", "90 m²"),
        ("Superficie parcela", "300 m²"),
    )
    ch = _characteristics(html)

    assert ch["superficie_m2"] == 90.0
    assert "superficie_util_m2" not in ch


def test_useful_area_row_never_lands_in_built_area():
    ch = _characteristics(_old_structure(("Superficie útil", "75 m²")))

    assert ch["superficie_util_m2"] == 75.0
    assert "superficie_m2" not in ch


def test_english_labels_map_to_the_same_fields():
    html = _old_structure(("Built Surface", "90 m²"), ("Net Internal Area", "75 m²"))
    ch = _characteristics(html)

    assert ch["superficie_m2"] == 90.0
    assert ch["superficie_util_m2"] == 75.0


def test_bare_superficie_is_a_fallback_only_when_no_built_area():
    only_generic = _characteristics(_old_structure(("Superficie", "88 m²")))
    with_built = _characteristics(
        _old_structure(("Superficie", "88 m²"), ("Superficie construida", "90 m²"))
    )

    assert only_generic["superficie_m2"] == 88.0
    assert with_built["superficie_m2"] == 90.0


def test_price_per_m2_row_is_not_an_area():
    ch = _characteristics(_old_structure(("Precio m²", "1.294 €"), ("Habitaciones", "2")))

    assert "superficie_m2" not in ch


def test_area_with_thousands_separator_is_parsed():
    ch = _characteristics(_old_structure(("Superficie parcela", "1.200 m²"), ("Superficie construida", "1.200 m²")))

    assert ch["superficie_m2"] == 1200.0


@pytest.mark.asyncio
async def test_scrape_property_details_returns_both_areas_from_fixture():
    scraper = PuertoInmobiliariaScraper()
    scraper.fetch_content = AsyncMock(
        return_value=(FICHA_FIXTURE.read_text(encoding="utf-8"), DETAIL_URL)
    )
    data = await scraper.scrape_property_details(DETAIL_URL)

    assert data["precio"] == 116500.0
    assert data["superficie_m2"] == 90.0
    assert data["superficie_util_m2"] == 75.0

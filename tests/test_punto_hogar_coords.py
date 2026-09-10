"""PuntoHogar detail scraper: exact coordinate extraction (respx-mocked)."""
import os
import sys

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.punto_hogar_scraper import PuntoHogarScraper

DETAIL_URL = "https://www.puntohogarinmobiliaria.com/buscador/inmueble.php?id=2372252"

_BASE_HTML = """
<html><body>
  <span class="precio-destacado">150.000 €</span>
  <div class="detalle-item"><span class="detalle-label">Tipo</span>
    <span class="detalle-valor">Piso</span></div>
  {maps}
</body></html>
"""


def _page(maps: str) -> str:
    return _BASE_HTML.format(maps=maps)


@respx.mock
@pytest.mark.asyncio
async def test_extracts_exact_coordinates_from_leaflet_marker():
    html = _page(
        "<script>var marker = L.marker([36.578221570278,-6.2230599455122])"
        ".addTo(map);</script>"
    )
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=html))

    data = await PuntoHogarScraper().scrape_property_details(DETAIL_URL)

    assert data["latitud"] == 36.578221570278
    assert data["longitud"] == -6.2230599455122
    # PuntoHogar's marker is the real point -> no approximate flag
    assert "ubicacion_aproximada" not in data


@respx.mock
@pytest.mark.asyncio
async def test_extracts_approximate_coordinates_from_leaflet_circle():
    html = _page(
        "<script>var map = L.map('map').setView([36.6121453, -6.2508307], 15);"
        "coords = [36.6121453, -6.2508307];"
        "var circle = L.circle(coords, {color:'#FF0000', radius: 250}).addTo(map);"
        "</script>"
    )
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=html))

    data = await PuntoHogarScraper().scrape_property_details(DETAIL_URL)

    assert data["latitud"] == 36.6121453
    assert data["longitud"] == -6.2508307
    assert data["ubicacion_aproximada"] is True
    assert data["radio_m"] == 250


@respx.mock
@pytest.mark.asyncio
async def test_marker_wins_over_circle_when_both_present():
    html = _page(
        "<script>var marker = L.marker([36.5782, -6.2230]).addTo(map);"
        "coords = [36.6121, -6.2508];"
        "var circle = L.circle(coords, {radius: 250}).addTo(map);</script>"
    )
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=html))

    data = await PuntoHogarScraper().scrape_property_details(DETAIL_URL)

    assert data["latitud"] == 36.5782
    assert "ubicacion_aproximada" not in data


@respx.mock
@pytest.mark.asyncio
async def test_no_marker_leaves_location_unset():
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=_page("")))

    data = await PuntoHogarScraper().scrape_property_details(DETAIL_URL)

    assert "latitud" not in data

"""Approximate coordinate extraction for the InmoServer-family detail scrapers
(Jimenez Ruiz, Samper, Tular) — same `cargar_mapa_ubicacion_aproximada(...)`
JS as UriaHomes/Alonsaga. respx-mocked HTTP.
"""
import os
import sys

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.jimenezruiz_scraper import JimenezRuizScraper
from scraper.samper_scraper import SamperScraper
from scraper.tular_scraper import TularScraper

CASES = [
    (
        JimenezRuizScraper,
        "https://www.jimenezruiz.com/Venta-Piso-El-Puerto-de-Santa-Maria-Crevillet-4747",
    ),
    (
        SamperScraper,
        "https://www.sampergestionesinmobiliarias.es/Venta-Piso-El-Puerto-de-Santa-Maria-Centro-34",
    ),
    (
        TularScraper,
        "https://www.tular.es/Venta-Piso-El-Puerto-de-Santa-Maria-Centro-661",
    ),
]

_MAP_JS = (
    '<script>cargar_mapa_ubicacion_aproximada("map2", 36.6016703, -6.2526514, '
    '"La posición en el mapa es aproximada por deseo del anunciante");</script>'
)


def _page(body: str) -> str:
    return f"<html><body><h1>Piso en venta</h1><p>180.000 €</p>{body}</body></html>"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_cls,url", CASES)
async def test_extracts_approximate_coordinates(scraper_cls, url):
    respx.get(url).mock(return_value=httpx.Response(200, text=_page(_MAP_JS)))

    data = await scraper_cls().scrape_property_details(url)

    assert data["latitud"] == 36.6016703
    assert data["longitud"] == -6.2526514
    assert data["ubicacion_aproximada"] is True


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_cls,url", CASES)
async def test_no_map_leaves_location_unset(scraper_cls, url):
    respx.get(url).mock(return_value=httpx.Response(200, text=_page("")))

    data = await scraper_cls().scrape_property_details(url)

    assert "latitud" not in data
    assert "ubicacion_aproximada" not in data

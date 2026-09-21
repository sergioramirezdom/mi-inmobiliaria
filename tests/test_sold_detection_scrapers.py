"""Per-scraper sold detection on live vs sold fichas (issue #40).

Live fichas carry text that merely contains the status words (footer
"Todos los derechos reservados", a garage "reservada", an investment sale
"alquilada", a "similares" card marked Vendido) and must stay active; a real
status ribbon must still deactivate the listing with `estado` set.
"""
import os
import sys

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.alonsaga_scraper import AlonsagaScraper
from scraper.guadalete_scraper import GuadaleteScraper
from scraper.jimenezruiz_scraper import JimenezRuizScraper
from scraper.puertopiso_scraper import PuertoPisoScraper
from scraper.punto_hogar_scraper import PuntoHogarScraper
from scraper.samper_scraper import SamperScraper
from scraper.tular_scraper import TularScraper
from scraper.uriahomes_scraper import UriaHomesScraper

CASES = [
    (AlonsagaScraper, "https://www.alonsaga.com/inmueble/piso/el-puerto/12345/"),
    (GuadaleteScraper, "https://www.inmobiliariaguadalete.com/inmuebles/pisos/piso-centro-ig1234"),
    (JimenezRuizScraper, "https://www.jimenezruiz.com/Venta-Piso-El-Puerto-de-Santa-Maria-Crevillet-4747"),
    (PuertoPisoScraper, "https://www.puertopiso.com/buscador/inmueble.php?id=29183740"),
    (PuntoHogarScraper, "https://www.puntohogarinmobiliaria.com/buscador/inmueble.php?id=2372252"),
    (SamperScraper, "https://www.sampergestionesinmobiliarias.es/Venta-Piso-El-Puerto-de-Santa-Maria-Centro-34"),
    (TularScraper, "https://www.tular.es/Venta-Piso-El-Puerto-de-Santa-Maria-Centro-661"),
    (UriaHomesScraper, "https://www.uriahomesinmobiliaria.com/Venta-Piso-El-Puerto-de-Santa-Maria-Centro-9"),
]
IDS = [cls.__name__ for cls, _ in CASES]

_LIVE_BODY = (
    "<nav><a href='/vendidos'>Vendido</a></nav>"
    "<h1>Piso en venta en El Puerto</h1>"
    "<p class='precio-destacado'>180.000 €</p>"
    "<div id='descripcion'><p>Piso con plaza de garaje reservada. Vivienda "
    "actualmente alquilada, ideal inversión.</p></div>"
    "<div class='inmuebles_similares'><span class='estado'>Vendido</span></div>"
    "<footer><p>© 2026 Todos los derechos reservados</p></footer>"
)


def _page(body: str) -> str:
    return f"<html><body>{body}</body></html>"


async def _scrape(scraper_cls, url, html):
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    return await scraper_cls().scrape_property_details(url)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_cls,url", CASES, ids=IDS)
async def test_live_ficha_with_status_words_in_text_stays_active(scraper_cls, url):
    data = await _scrape(scraper_cls, url, _page(_LIVE_BODY))

    assert data.get("activa") is True
    assert "estado" not in data


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_cls,url", CASES, ids=IDS)
async def test_ficha_with_sold_ribbon_is_deactivated(scraper_cls, url):
    body = "<div class='ribbon'>Vendido</div>" + _LIVE_BODY
    data = await _scrape(scraper_cls, url, _page(body))

    assert data["activa"] is False
    assert data["estado"] == "Vendido"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_cls,url", CASES, ids=IDS)
async def test_ficha_with_reserved_ribbon_keeps_reservado_estado(scraper_cls, url):
    body = "<span class='estado-inmueble'>Reservado</span>" + _LIVE_BODY
    data = await _scrape(scraper_cls, url, _page(body))

    assert data["activa"] is False
    assert data["estado"] == "Reservado"


@respx.mock
@pytest.mark.asyncio
async def test_uriahomes_english_sold_ribbon_is_detected():
    url = CASES[-1][1]
    html = _page("<div class='ribbon'>Sold</div><h1>Flat in El Puerto</h1>")
    data = await _scrape(UriaHomesScraper, url, html)

    assert data["activa"] is False
    assert data["estado"] == "Vendido"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scraper_cls,url",
    [c for c in CASES if c[0] in (GuadaleteScraper, SamperScraper, TularScraper, UriaHomesScraper)],
    ids=["Guadalete", "Samper", "Tular", "UriaHomes"],
)
async def test_rented_ribbon_deactivates_where_rented_was_already_detected(scraper_cls, url):
    data = await _scrape(scraper_cls, url, _page("<div class='ribbon'>Alquilado</div>" + _LIVE_BODY))

    assert data["activa"] is False
    assert data["estado"] == "Alquilado"

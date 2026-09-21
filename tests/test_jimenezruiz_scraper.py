"""Jiménez Ruiz detail scraper: extraction is scoped to the main ficha, so the
"similares" widget, menus and footer cannot leak price, photos or amenities
(respx-mocked; coordinates are covered in test_inmoserver_coords.py)."""
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.jimenezruiz_scraper import JimenezRuizScraper

URL = "https://www.jimenezruiz.com/Venta-Piso-El-Puerto-de-Santa-Maria-Crevillet-4747"
FICHA_HTML = (Path(__file__).parent / "fixtures" / "jimenezruiz_ficha.html").read_text(encoding="utf-8")


async def _scrape(html: str, url: str = URL) -> dict:
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, text=html))
        return await JimenezRuizScraper().scrape_property_details(url)


def _page(body: str) -> str:
    return f'<html><body><div id="inmueble2">{body}</div></body></html>'


@pytest.mark.asyncio
async def test_price_survives_related_listing_with_the_same_price():
    data = await _scrape(FICHA_HTML)

    assert data["precio"] == 200000.0


@pytest.mark.asyncio
async def test_cheap_garage_keeps_its_price():
    data = await _scrape(_page('<h1>Venta de garaje</h1><h5 id="inmueble2_precio">8.000 €</h5>'))

    assert data["precio"] == 8000.0


@pytest.mark.asyncio
async def test_price_without_dedicated_element_is_first_bare_price_in_ficha():
    data = await _scrape(_page("<h1>Piso</h1><p>95.000 €</p><p>Cuota desde 450 €</p>"))

    assert data["precio"] == 95000.0


@pytest.mark.asyncio
async def test_unparseable_price_is_left_unset():
    data = await _scrape(_page('<h1>Piso</h1><h5 id="inmueble2_precio">Consultar</h5>'))

    assert "precio" not in data


@pytest.mark.asyncio
async def test_fotos_are_only_this_propertys_and_deduplicated():
    data = await _scrape(FICHA_HTML)

    assert data["fotos"] == [
        "https://www.inmoserver.com/fotos/0412/nwm/4747_aaa111.jpg",
        "https://www.inmoserver.com/fotos/0412/nwm/4747_bbb222.jpg",
    ]


@pytest.mark.asyncio
async def test_relative_fotos_are_made_absolute():
    html = _page('<img src="/fotos/0412/nwm/4747_aaa111.jpg"><img src="/fotos/0412/nwm/4747_bbb222.jpg">')

    data = await _scrape(html)

    assert data["fotos"] == [
        "https://www.jimenezruiz.com/fotos/0412/nwm/4747_aaa111.jpg",
        "https://www.jimenezruiz.com/fotos/0412/nwm/4747_bbb222.jpg",
    ]


@pytest.mark.asyncio
async def test_no_photo_of_this_property_leaves_fotos_unset():
    html = _page('<img src="https://www.inmoserver.com/fotos/0412/nwm/9999_zzz.jpg">')

    data = await _scrape(html)

    assert "fotos" not in data


@pytest.mark.asyncio
async def test_amenities_come_from_the_features_list_only():
    data = await _scrape(FICHA_HTML)

    assert data["ascensor"] is True
    assert data["terraza"] is True
    # Only mentioned in the menu / similares widget / footer
    for field in ("garaje", "piscina"):
        assert field not in data
    # Negated in the features list ("Sin trastero"): never True
    assert "trastero" not in data


@pytest.mark.asyncio
async def test_garaje_mentioned_only_in_menu_stays_unset():
    html = (
        '<html><body><nav><ul><li><a href="/g">Garajes</a></li></ul></nav>'
        + _page("<h1>Piso</h1><ul><li>96 M2</li><li>3 Dormitorios</li></ul>")
        + "</body></html>"
    )

    data = await _scrape(html)

    assert "garaje" not in data


@pytest.mark.asyncio
async def test_titulo_is_the_ficha_h1():
    data = await _scrape(FICHA_HTML)

    assert data["titulo"] == "Venta de piso en El Puerto de Santa María, CREVILLET"


@pytest.mark.asyncio
async def test_features_rooms_area_and_planta_baja():
    data = await _scrape(FICHA_HTML)

    assert data["superficie_m2"] == 96.0
    assert data["habitaciones"] == 3
    assert data["banos"] == 2
    assert data["planta"] == 0


@pytest.mark.asyncio
async def test_numbered_planta_is_still_parsed():
    data = await _scrape(_page("<h1>Piso</h1><ul><li>2 Baños</li><li>Planta 3</li></ul>"))

    assert data["planta"] == 3


@pytest.mark.asyncio
async def test_year_built_is_not_returned_because_it_is_not_a_column():
    data = await _scrape(FICHA_HTML)

    assert "year_built" not in data


@pytest.mark.asyncio
async def test_description_comes_from_the_ficha():
    data = await _scrape(FICHA_HTML)

    assert data["descripcion"].startswith("Luminoso piso ubicado en Crevillet")

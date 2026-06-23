"""Smoke tests: zona_utils wired into each scraper — pure logic, no HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from unittest.mock import AsyncMock, patch
import pytest


@pytest.mark.asyncio
async def test_alonsaga_extracts_barrio_from_url():
    from scraper.alonsaga_scraper import AlonsagaScraper

    fake_html = """<html><body>
        <h1>Piso en venta</h1>
        <p>180.000 €</p>
    </body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = AlonsagaScraper()
        result = await s.scrape_property_details(
            "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/123/"
        )
    assert result.get("barrio") == "Pinar Alto Crevillet Menesteo"


@pytest.mark.asyncio
async def test_puertopiso_extracts_barrio_from_html():
    from scraper.puertopiso_scraper import PuertoPisoScraper

    fake_html = """<html><head><title>Piso en Vistahermosa - El Puerto de Santa María</title></head>
        <body><h1>Fantástico piso</h1><p>200.000 €</p></body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = PuertoPisoScraper()
        result = await s.scrape_property_details("https://puertopiso.com/buscador/inmueble.php?id=123")
    assert result.get("barrio") == "Vistahermosa"


@pytest.mark.asyncio
async def test_punto_hogar_extracts_barrio_from_html():
    from scraper.punto_hogar_scraper import PuntoHogarScraper

    fake_html = """<html><body>
        <h1>Piso</h1>
        <p>Zona: El Buzo, precio 150.000€</p>
        <div class="precio-destacado">150.000€</div>
    </body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = PuntoHogarScraper()
        result = await s.scrape_property_details("https://www.puntohogarinmobiliaria.com/venta/piso/el-puerto/123")
    assert result.get("barrio") == "El Buzo"

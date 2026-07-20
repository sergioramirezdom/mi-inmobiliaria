"""Smoke tests: zona_utils wired into each scraper — pure logic, no HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from unittest.mock import MagicMock, patch
import pytest

# Python 3.7 compatibility: AsyncMock is available in 3.8+
try:
    from unittest.mock import AsyncMock
except ImportError:
    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)


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


from scraper.base import ScraperBase
from scraper.config import ScraperConfig
from db.models import Fuente


class ScraperParaZonas(ScraperBase):
    """Implementación concreta mínima de ScraperBase, solo para test.

    Mismo patrón que ConcreteScraperForTesting en tests/test_scraper_base.py.
    """

    async def scrape(self, fuente: Fuente):
        return []

    def _parse_properties(self, content: str):
        return []

    def _extract_fields(self, element):
        return {}


def _normalizar_raw(raw_data: dict):
    scraper = ScraperParaZonas(ScraperConfig(timeout=30, retries=3,
                                             verify_ssl=True, auto_detect=True))
    fuente = Fuente(id=1, nombre="Test", url="https://ejemplo.com",
                    tipo_scraper="generic", activa=True, intervalo_horas=24)
    return scraper.normalize_property(raw_data, fuente)


def test_normalize_property_rellena_zona_normalizada():
    """Una propiedad scrapeada sale con la zona canónica resuelta."""
    prop = _normalizar_raw({
        "url_original": "https://ejemplo.com/piso/1",
        "titulo": "Piso luminoso",
        "barrio": "El Pinar Alto",
    })
    assert prop.barrio == "El Pinar Alto"  # el crudo NO se toca
    assert prop.zona_normalizada == "Pinar Alto"
    assert prop.zona_confianza == "exacta"


def test_normalize_property_deja_zona_none_si_no_hay_match():
    prop = _normalizar_raw({
        "url_original": "https://ejemplo.com/piso/2",
        "titulo": "Piso en Madrid",
        "barrio": "Chamberí",
    })
    assert prop.barrio == "Chamberí"
    assert prop.zona_normalizada is None
    assert prop.zona_confianza is None

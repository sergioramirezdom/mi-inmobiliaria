"""El respaldo genérico de fotos está conectado en los scrapers sin extractor propio."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from unittest.mock import MagicMock, patch

import pytest

try:
    from unittest.mock import AsyncMock
except ImportError:
    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)


HTML_CON_GALERIA = """
<html><body>
  <h1>Piso en venta</h1>
  <p>180.000 €</p>
  <img src="/fotos/anuncio/1.jpg">
  <img src="/fotos/anuncio/2.jpg">
  <img src="/fotos/anuncio/3.jpg">
  <img src="/img/logo.png">
</body></html>
"""

ESPERADAS = [
    "https://ejemplo.com/fotos/anuncio/1.jpg",
    "https://ejemplo.com/fotos/anuncio/2.jpg",
    "https://ejemplo.com/fotos/anuncio/3.jpg",
]


def test_url_extractor_emite_fotos():
    """Cubre manual_scraper y el diálogo 'añadir por URL'."""
    from scraper.url_extractor import _parse_html

    data = _parse_html(HTML_CON_GALERIA, url="https://ejemplo.com/piso/1")
    assert data.get("fotos") == ESPERADAS


def test_url_extractor_sin_fotos_no_pone_la_clave():
    from scraper.url_extractor import _parse_html

    data = _parse_html("<html><body><p>Piso</p></body></html>",
                       url="https://ejemplo.com/piso/1")
    assert "fotos" not in data or data["fotos"] == []


@pytest.mark.asyncio
async def test_punto_hogar_rellena_fotos_por_respaldo():
    from scraper.config import ScraperConfig
    from scraper.punto_hogar_scraper import PuntoHogarScraper

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = HTML_CON_GALERIA
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        scraper = PuntoHogarScraper(ScraperConfig())
        data = await scraper.scrape_property_details("https://ejemplo.com/piso/1")

    assert data.get("fotos") == ESPERADAS
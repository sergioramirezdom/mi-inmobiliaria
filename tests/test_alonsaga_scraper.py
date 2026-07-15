"""Unit tests for AlonsagaScraper — pure logic, no HTTP calls."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.alonsaga_scraper import (
    _parse_price_eu,
    _extract_tipo_from_url,
    _extract_property_id_from_url,
    _extract_fotos,
    _extract_room_count,
)
from bs4 import BeautifulSoup


def test_parse_price_eu_dot_thousands():
    assert _parse_price_eu("180.000") == 180000.0


def test_parse_price_eu_with_comma_decimal():
    assert _parse_price_eu("250.000,50") == 250000.5


def test_parse_price_eu_plain():
    assert _parse_price_eu("95000") == 95000.0


def test_parse_price_eu_invalid():
    assert _parse_price_eu("no price") is None


def test_extract_tipo_casa():
    url = "https://www.alonsaga.com/Venta-Casa-El-Puerto-de-Santa-María-crevillet-pinar-alto-5022"
    assert _extract_tipo_from_url(url) == "casa"


def test_extract_tipo_piso():
    url = "https://www.alonsaga.com/Venta-Piso-El-Puerto-de-Santa-María-Carretera-de-sanlucar-3991"
    assert _extract_tipo_from_url(url) == "piso"


def test_extract_tipo_with_trailing_slash():
    url = "https://www.alonsaga.com/Venta-Vivienda-El-Puerto-de-Santa-María-Vistahermosa-1234/"
    assert _extract_tipo_from_url(url) == "vivienda"


def test_extract_tipo_unknown():
    url = "https://www.alonsaga.com/encargo_venta"
    assert _extract_tipo_from_url(url) is None


def test_extract_property_id():
    url = "https://www.alonsaga.com/Venta-Casa-El-Puerto-de-Santa-María-crevillet-pinar-alto-5022"
    assert _extract_property_id_from_url(url) == "5022"


def test_extract_property_id_trailing_slash():
    url = "https://www.alonsaga.com/Venta-Piso-El-Puerto-de-Santa-María-Carretera-de-sanlucar-3991/"
    assert _extract_property_id_from_url(url) == "3991"


def test_extract_property_id_none_when_missing():
    url = "https://www.alonsaga.com/encargo_venta"
    assert _extract_property_id_from_url(url) is None


def test_extract_fotos_filters_by_property_id():
    html = """
    <html><body>
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg">
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_def456.jpg?auto=compress&cs=tinysrgb&h=650&w=940">
      <img src="https://www.inmoserver.com/fotos/1266/wm/3945_other.jpg">
      <img src="https://other.com/photo.jpg">
      <img src="/static/logo.png">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup, "5022")
    assert fotos == [
        "https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg",
        "https://www.inmoserver.com/fotos/1266/wm/5022_def456.jpg",
    ]


def test_extract_fotos_dedupes_compressed_variant():
    html = """
    <html><body>
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg">
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg?auto=compress&cs=tinysrgb&h=650&w=940">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup, "5022")
    assert fotos == ["https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg"]


def test_extract_fotos_empty_when_none():
    soup = BeautifulSoup("<html><body><p>no images</p></body></html>", "lxml")
    assert _extract_fotos(soup, "5022") == []


def test_extract_room_count_reads_icon_badge():
    html = """
    <html><body>
      <div id="inmueble2_caracteristicas">
        <div><i class='fas fa-bed'></i><span class='p-2'>5</span></div>
        <div><i class='fas fa-bath'></i><span class='p-2'>2</span></div>
        <div><i class='fas fa-warehouse'></i><span class='p-2'>1</span></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 5
    assert _extract_room_count(soup, "fa-bath") == 2


def test_extract_room_count_ignores_similares_widget():
    """The 'similares' carousel reuses fa-bed/fa-bath outside #inmueble2_caracteristicas — must be ignored."""
    html = """
    <html><body>
      <div id="inmueble2_caracteristicas">
        <div><i class='fas fa-bed'></i><span class='p-2'>5</span></div>
      </div>
      <div class="inmuebles_similares_habitaciones">
        <i class="fas fa-bed"></i><span class="p-2">99</span>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 5


def test_extract_room_count_none_when_container_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_room_count(soup, "fa-bed") is None


def test_extract_room_count_none_when_icon_missing():
    html = "<div id='inmueble2_caracteristicas'><div><i class='fas fa-bath'></i><span>2</span></div></div>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") is None


import asyncio
from unittest.mock import patch, MagicMock
from scraper.generic import GenericScraper
from scraper.config import ScraperConfig, SelectorsConfig


def test_generic_scraper_extracts_data_path_url():
    """GenericScraper._extract_field should extract URL from data-path attribute."""
    config = ScraperConfig(selectors=SelectorsConfig(property_container="div.card"))
    scraper = GenericScraper(config)
    scraper.base_url = "https://www.alonsaga.com"

    html = '<div class="card" data-path="/detalle/en_venta/piso/cadiz/123/">Piso</div>'
    soup = BeautifulSoup(html, "lxml")
    element = soup.select_one("div.card")

    url = scraper._extract_field(element, "link")
    assert url == "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/123/"

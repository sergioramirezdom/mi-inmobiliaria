"""Unit tests for AlonsagaScraper — pure logic, no HTTP calls."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.alonsaga_scraper import (
    _parse_price_eu,
    _extract_tipo_from_url,
    _extract_property_id_from_url,
    _extract_fotos,
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


def test_extract_fotos_filters_by_domain():
    html = """
    <html><body>
      <img src="https://fotoshs.imghs.net/path/photo1.jpg">
      <img src="https://other.com/photo.jpg">
      <img src="https://fotoshs.imghs.net/path/photo2.jpg">
      <img src="/static/logo.png">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup)
    assert fotos == [
        "https://fotoshs.imghs.net/path/photo1.jpg",
        "https://fotoshs.imghs.net/path/photo2.jpg",
    ]


def test_extract_fotos_empty_when_none():
    soup = BeautifulSoup("<html><body><p>no images</p></body></html>", "lxml")
    assert _extract_fotos(soup) == []


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

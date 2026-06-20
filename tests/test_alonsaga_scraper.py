"""Unit tests for AlonsagaScraper — pure logic, no HTTP calls."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.alonsaga_scraper import (
    _parse_price_eu,
    _extract_tipo_from_url,
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


def test_extract_tipo_piso():
    url = "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto/123/"
    assert _extract_tipo_from_url(url) == "piso"


def test_extract_tipo_chalet():
    url = "https://www.alonsaga.com/detalle/en_venta/chalet/cadiz/el_puerto/zona/456/"
    assert _extract_tipo_from_url(url) == "chalet"


def test_extract_tipo_unknown():
    url = "https://www.alonsaga.com/detalle/en_venta/cadiz/el_puerto/"
    assert _extract_tipo_from_url(url) is None


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

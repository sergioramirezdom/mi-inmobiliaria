import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.url_extractor import _parse_html, _parse_price, _parse_float


def test_parse_price_european_thousands():
    assert _parse_price("195.000") == 195000.0

def test_parse_price_with_comma_decimal():
    assert _parse_price("195.000,50") == 195000.50

def test_parse_price_plain():
    assert _parse_price("195000") == 195000.0

def test_parse_price_invalid():
    assert _parse_price("no-price") is None

def test_parse_float_comma():
    assert _parse_float("69,84") == 69.84

def test_parse_float_dot():
    assert _parse_float("69.84") == 69.84


def test_parse_html_price_from_meta():
    html = '''<html><head>
        <meta property="og:price:amount" content="195000">
    </head><body></body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_price_from_text():
    html = '''<html><body>
        <p>Precio de venta: 195.000 €</p>
    </body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_price_below_10k_ignored():
    html = '''<html><body><p>Gastos comunidad: 80 €. Precio: 195.000 €</p></body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_title_from_og():
    html = '''<html><head>
        <meta property="og:title" content="Magnífico piso en El Puerto">
    </head><body><h1>Otro título</h1></body></html>'''
    data = _parse_html(html)
    assert data["titulo"] == "Magnífico piso en El Puerto"


def test_parse_html_title_from_h1():
    html = '''<html><body><h1>Piso en venta en El Puerto</h1></body></html>'''
    data = _parse_html(html)
    assert data["titulo"] == "Piso en venta en El Puerto"


def test_parse_html_surface():
    html = '''<html><body><p>120 m² construidos, 3 habitaciones</p></body></html>'''
    data = _parse_html(html)
    assert data["superficie_m2"] == 120.0


def test_parse_html_rooms_and_baths():
    html = '''<html><body><p>3 habitaciones, 2 baños</p></body></html>'''
    data = _parse_html(html)
    assert data["habitaciones"] == 3
    assert data["banos"] == 2


def test_parse_html_rooms_dormitorios():
    html = '''<html><body><p>4 dormitorios y 2 baños</p></body></html>'''
    data = _parse_html(html)
    assert data["habitaciones"] == 4


def test_parse_html_sold_keyword_vendida():
    html = '''<html><body><p>Esta propiedad está vendida.</p><p>Precio: 195.000 €</p></body></html>'''
    data = _parse_html(html)
    assert data["activa"] is False
    assert data["estado"] == "Vendida"


def test_parse_html_sold_keyword_reservado():
    html = '''<html><body><p>RESERVADO. Contacte para más info.</p></body></html>'''
    data = _parse_html(html)
    assert data["activa"] is False


def test_parse_html_surface_over_2000_ignored():
    html = '''<html><body><p>Finca de 5000 m², 3 habitaciones</p></body></html>'''
    data = _parse_html(html)
    assert "superficie_m2" not in data

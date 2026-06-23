"""Unit tests for zona_utils — pure logic, no HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.zona_utils import extract_from_url, extract_from_html
from bs4 import BeautifulSoup


# --- extract_from_url ---

def test_extract_from_url_alonsaga():
    url = "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/64234783889.265000/"
    assert extract_from_url(url) == "Pinar Alto Crevillet Menesteo"

def test_extract_from_url_generic_zona_after_municipio():
    url = "https://example.com/venta/piso/el_puerto_de_santa_maria/centro/12345/"
    assert extract_from_url(url) == "Centro"

def test_extract_from_url_no_municipio_returns_none():
    url = "https://www.guadalete.com/inmuebles/pisos/ig1234"
    assert extract_from_url(url) is None

def test_extract_from_url_only_tipo_after_municipio_returns_none():
    url = "https://example.com/venta/el_puerto_de_santa_maria/piso/12345"
    assert extract_from_url(url) is None

def test_extract_from_url_empty_returns_none():
    assert extract_from_url("") is None


# --- extract_from_html ---

def test_extract_from_html_zona_label():
    text = "Superficie 80m² Zona: Pinar Alto, Precio 180.000€"
    assert extract_from_html(text) == "Pinar Alto"

def test_extract_from_html_barrio_label():
    text = "Barrio: El Centro, municipio El Puerto"
    assert extract_from_html(text) == "El Centro"

def test_extract_from_html_title_en_pattern():
    text = "Terreno rural en Pedanías Este - Jerez de la Frontera"
    assert extract_from_html(text) == "Pedanías Este"

def test_extract_from_html_no_zona_returns_none():
    text = "Piso de 3 habitaciones, 2 baños, 90m². Precio 200.000€."
    assert extract_from_html(text) is None

def test_extract_from_html_soup_h1_used():
    html = '<html><body><h1>Piso en Vistahermosa - El Puerto de Santa María</h1></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    result = extract_from_html("Sin zona en texto.", soup)
    assert result == "Vistahermosa"

def test_extract_from_html_result_max_60_chars():
    long_zona = "A" * 70
    text = f"Zona: {long_zona}, Precio 100€"
    result = extract_from_html(text)
    assert result is not None
    assert len(result) <= 60

def test_extract_from_html_none_returns_none():
    assert extract_from_html(None) is None

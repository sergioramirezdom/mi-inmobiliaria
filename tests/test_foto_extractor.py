"""Tests del extractor genérico de fotos — lógica pura, sin HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from scraper.foto_extractor import _carpeta, _descartable, _es_imagen, _sin_query


@pytest.mark.parametrize("entrada,esperado", [
    ("https://p.com/f/a.jpg?w=800", "https://p.com/f/a.jpg"),
    ("https://p.com/f/a.jpg", "https://p.com/f/a.jpg"),
    ("https://p.com/f/a.jpg?w=1200&h=600", "https://p.com/f/a.jpg"),
])
def test_sin_query(entrada, esperado):
    assert _sin_query(entrada) == esperado


def test_carpeta_agrupa_por_directorio():
    assert _carpeta("https://p.com/fotos/2024/a.jpg") == "p.com/fotos/2024"
    assert _carpeta("https://p.com/fotos/2024/b.jpg") == "p.com/fotos/2024"
    assert _carpeta("https://p.com/otro/c.jpg") != _carpeta("https://p.com/fotos/2024/a.jpg")


def test_carpeta_incluye_dominio():
    """Dos CDNs distintos con la misma ruta no deben agruparse juntos."""
    assert _carpeta("https://a.com/f/x.jpg") != _carpeta("https://b.com/f/x.jpg")


@pytest.mark.parametrize("url,esperado", [
    ("https://p.com/a.jpg", True),
    ("https://p.com/a.jpeg", True),
    ("https://p.com/a.png", True),
    ("https://p.com/a.webp", True),
    ("https://p.com/a.JPG", True),
    ("https://p.com/a.jpg?w=800", True),   # el query no debe estorbar
    ("https://p.com/a.svg", False),
    ("https://p.com/pagina.html", False),
    ("https://p.com/sinextension", False),
])
def test_es_imagen(url, esperado):
    assert _es_imagen(url) is esperado


@pytest.mark.parametrize("url", [
    "https://p.com/img/logo.png",
    "https://p.com/banner-home.jpg",
    "https://p.com/icons/mail.png",
    "https://p.com/f/thumb_a.jpg",
    "https://p.com/f/small_a.jpg",
    "https://p.com/avatar.jpg",
    "https://p.com/sprite.png",
    "https://p.com/placeholder.jpg",
    "https://p.com/blank.png",
    "https://p.com/a.svg",
    "https://p.com/a.gif",
    "https://p.com/a.ico",
])
def test_descartable_true(url):
    assert _descartable(url) is True


@pytest.mark.parametrize("url", [
    "https://p.com/fotos/casa-salon.jpg",
    "https://p.com/media/2024/01/piso.jpeg",
    "https://p.com/f/a.png",
])
def test_descartable_false(url):
    assert _descartable(url) is False


# ── Task 2: algoritmo extraer_fotos ──────────────────────────────────────

from scraper.foto_extractor import extraer_fotos

BASE = "https://portal.com/piso/1"


def test_galeria_normal():
    html = '<img src="/f/a.jpg"><img src="/f/b.jpg"><img src="/f/c.jpg">'
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/f/a.jpg",
        "https://portal.com/f/b.jpg",
        "https://portal.com/f/c.jpg",
    ]


def test_descarta_svg_y_gif():
    html = '<img src="/f/a.jpg"><img src="/x.svg"><img src="/y.gif">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_descarta_logo_y_thumb():
    html = ('<img src="/f/a.jpg"><img src="/img/logo.png">'
            '<img src="/f/thumb_b.jpg">')
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_lee_data_src_de_carga_diferida():
    html = '<img data-src="/f/a.jpg"><img data-src="/f/b.jpg">'
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/f/a.jpg",
        "https://portal.com/f/b.jpg",
    ]


def test_coge_la_foto_grande_del_enlace():
    """Patrón de puertopiso: la miniatura va en <img>, la grande en <a href>."""
    html = '<a href="/f/big1.jpg"><img src="/f/small1.jpg"></a>'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/big1.jpg"]


def test_resuelve_urls_relativas():
    html = '<img src="fotos/a.jpg">'
    assert extraer_fotos(html, "https://portal.com/piso/1/") == [
        "https://portal.com/piso/1/fotos/a.jpg"
    ]


def test_deduplica_por_query_string():
    html = '<img src="/f/a.jpg?w=800"><img src="/f/a.jpg?w=1200">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_gana_la_carpeta_con_mas_fotos():
    """La galería del anuncio contra adornos dispersos de la plantilla."""
    html = ('<img src="/g/1.jpg"><img src="/g/2.jpg"><img src="/g/3.jpg">'
            '<img src="/g/4.jpg"><img src="/otro/x.jpg"><img src="/mas/y.jpg">')
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/g/1.jpg",
        "https://portal.com/g/2.jpg",
        "https://portal.com/g/3.jpg",
        "https://portal.com/g/4.jpg",
    ]


def test_fallback_a_og_image():
    html = ('<meta property="og:image" content="/f/principal.jpg">'
            '<img src="/logo.png">')
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/principal.jpg"]


def test_descarta_imagenes_con_dimension_declarada_pequena():
    html = '<img src="/f/a.jpg" width="50"><img src="/f/b.jpg" width="800">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/b.jpg"]


def test_html_vacio():
    assert extraer_fotos("", BASE) == []


def test_html_sin_imagenes():
    assert extraer_fotos("<p>hola</p>", BASE) == []
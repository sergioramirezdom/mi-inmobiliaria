"""Tests for the pure HTML card builder of Propiedades 2.0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from ui.property_card import card_html, fmt_eur


def _p(**kwargs):
    base = {
        "id": 1,
        "titulo": "Piso céntrico",
        "precio": 189_000.0,
        "bajada": None,
        "precio_m2": 1853,
        "superficie": 102.0,
        "habitaciones": 3,
        "banos": 2,
        "tipo": "piso",
        "barrio": "Centro",
        "municipio": "El Puerto de Santa María",
        "chips": ["Ascensor", "Terraza"],
        "fotos": ["https://img.example.com/1.jpg"],
        "url": "https://example.com/1",
        "origen": "example.com",
        "dias": 2,
        "es_manual": False,
        "activa": True,
        "estado": None,
        "vista": False,
        "favorita": False,
        "descartada": False,
    }
    base.update(kwargs)
    return base


def test_fmt_eur_spanish_thousands():
    assert fmt_eur(189_000) == "189.000 €"
    assert fmt_eur(1_500) == "1.500 €"


def test_card_shows_price_and_m2():
    html = card_html(_p())
    assert "189.000 €" in html
    assert "1.853 €/m²" in html


def test_card_bajada_only_when_present():
    assert "↓" not in card_html(_p())
    html = card_html(_p(bajada=6_000))
    assert "↓" in html and "6.000 €" in html


def test_card_photo_and_placeholder():
    html = card_html(_p())
    assert '<img src="https://img.example.com/1.jpg"' in html
    html_sin = card_html(_p(fotos=[]))
    assert "<img" not in html_sin
    assert "🏠" in html_sin


def test_card_chips_and_location():
    html = card_html(_p())
    assert "Ascensor" in html and "Terraza" in html
    assert "Centro, El Puerto de Santa María" in html


def test_card_escapes_title_html():
    html = card_html(_p(titulo='<script>alert("x")</script>'))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_card_inactive_strikethrough():
    html = card_html(_p(activa=False, estado="Vendida"))
    assert "<s>" in html and "Vendida" in html


def test_card_missing_data_degrades():
    html = card_html(_p(precio=None, precio_m2=None, superficie=None, habitaciones=None, banos=None, dias=None))
    assert "Precio N/D" in html
    assert "€/m²" not in html


def test_card_manual_badge():
    assert "📌 Manual" in card_html(_p(es_manual=True))
    assert "📌 Manual" not in card_html(_p())

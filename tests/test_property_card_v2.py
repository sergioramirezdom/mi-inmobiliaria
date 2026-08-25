"""Tests for the pure HTML card builder of Propiedades 2.0 (v2 grid)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from ui.property_card_v2 import card_html


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
        "activa": False,
        "estado": "Vendida",
        "vista": False,
        "favorita": False,
        "descartada": False,
        "excluida": False,
    }
    base.update(kwargs)
    return base


# ── 2.9 — "⚠️ Excluida" badge on manually-excluded properties ───────────


def test_card_html_shows_excluida_badge_when_flagged():
    html = card_html(_p(excluida=True))
    assert "Excluida" in html


def test_card_html_omits_excluida_badge_when_not_flagged():
    html = card_html(_p(excluida=False))
    assert "⚠️ Excluida" not in html


def test_card_html_never_renders_fecha_baja_derived_value():
    # `fecha_baja` is not passed to card_html at all — the card dict never
    # carries it (see property_queries.prop_to_dict) — so an excluded row's
    # untrustworthy fecha_baja can't leak into the vendidas-tab card.
    html_excluded = card_html(_p(excluida=True))
    html_normal = card_html(_p(excluida=False))
    assert "fecha_baja" not in html_excluded
    assert "fecha_baja" not in html_normal

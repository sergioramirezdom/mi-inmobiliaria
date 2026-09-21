"""Tests for extract_suggestions in description_enricher (#49)."""
import sys, os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from scraper.description_enricher import extract_suggestions


def _prop(descripcion, titulo="Piso en venta", **overrides):
    fields = dict(
        titulo=titulo, descripcion=descripcion, ascensor=None, garaje=None,
        terraza=None, balcon=None, piscina=None, trastero=None,
        aire_acondicionado=None, habitaciones=None, banos=None,
        superficie_m2=None, barrio=None, direccion=None, url_original=None,
        zona_confianza="exacta",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ── ascensor ─────────────────────────────────────────────────────────────────

def test_sin_ascensor_suggests_false():
    assert extract_suggestions(_prop("Tercero sin ascensor"))["ascensor"][0] is False


def test_sin_ascensor_needs_word_boundary():
    # "casin" ends in "sin": must not be read as the negation "sin"
    assert "ascensor" in extract_suggestions(_prop("Zona casin ascensor nuevo"))
    assert extract_suggestions(_prop("Zona casin ascensor nuevo"))["ascensor"][0] is True


@pytest.mark.parametrize("texto", [
    "Posibilidad de instalar ascensor en la comunidad",
    "Edificio con opcion de colocar ascensor",
])
def test_speculative_ascensor_is_not_suggested(texto):
    assert "ascensor" not in extract_suggestions(_prop(texto))


def test_plain_ascensor_suggests_true():
    assert extract_suggestions(_prop("Edificio con ascensor"))["ascensor"][0] is True


# ── amenities: proximity and longer negation window ──────────────────────────

def test_nearby_piscina_is_not_a_piscina():
    assert "piscina" not in extract_suggestions(_prop("Situado cerca de la piscina municipal"))


def test_own_piscina_still_suggested():
    assert extract_suggestions(_prop("Urbanizacion con piscina comunitaria"))["piscina"][0] is True


def test_negation_allows_a_few_intervening_words():
    s = extract_suggestions(_prop("No tiene ni balcon"))
    assert s["balcon"][0] is False
    s = extract_suggestions(_prop("Vivienda sin ninguna clase de terraza"))
    assert s["terraza"][0] is False


def test_negation_does_not_cross_clauses():
    s = extract_suggestions(_prop("Sin garaje, con terraza amplia"))
    assert s["terraza"][0] is True


# ── superficie ───────────────────────────────────────────────────────────────

def test_superficie_prefers_vivienda_over_parcela():
    s = extract_suggestions(_prop("Parcela de 500 m2 con vivienda de 90 m2 construidos"))
    assert s["superficie_m2"][0] == 90


def test_superficie_prefers_construidos_over_first_match():
    s = extract_suggestions(_prop("Terraza de 40 m2. Piso de 85 m2 construidos"))
    assert s["superficie_m2"][0] == 85


def test_superficie_single_value_still_works():
    assert extract_suggestions(_prop("Piso de 72 m2"))["superficie_m2"][0] == 72


# ── banos ────────────────────────────────────────────────────────────────────

def test_aseo_is_not_counted_as_bano():
    assert "banos" not in extract_suggestions(_prop("Piso con 1 aseo"))
    assert extract_suggestions(_prop("Piso con 2 banos y 1 aseo"))["banos"][0] == 2


# ── barrio (single source with extract_barrio_from_text) ─────────────────────

def test_generic_zone_phrase_is_not_suggested_as_barrio():
    assert "barrio" not in extract_suggestions(_prop("Piso en zona residencial tranquila, cerca de todo"))


def test_catalogue_zone_suggested_as_barrio():
    assert extract_suggestions(_prop("Situado en zona Pinar Alto, con vistas"))["barrio"][0] == "Pinar Alto"

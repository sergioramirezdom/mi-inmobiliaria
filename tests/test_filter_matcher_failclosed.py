"""FilterMatcher fails CLOSED: a corrupt, unknown or unevaluable criteria set
matches nothing, favourites-only alerts never match new listings, and a
property missing a field never raises out of the matching round."""
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import FiltroAlerta, Propiedad
from notifications.alert_routing import TIPO_BAJADAS_FAVORITAS
from notifications.filter_matcher import FilterMatcher


def _prop(**kw):
    base = dict(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="test",
        titulo="t", precio=100000.0, tipo_operacion="venta",
    )
    base.update(kw)
    return Propiedad(**base)


def _filtro(criterios=None, tipo_alerta="nuevas", raw=None):
    return FiltroAlerta(
        nombre="f",
        tipo_alerta=tipo_alerta,
        criterios_json=raw if raw is not None else (
            json.dumps(criterios) if criterios is not None else None
        ),
    )


# ── favourites-only alerts never match new listings ─────────────────────────


def test_bajadas_favoritas_alert_matches_no_new_listing():
    filtro = _filtro(tipo_alerta=TIPO_BAJADAS_FAVORITAS)
    assert FilterMatcher.get_matching_properties([_prop()], filtro) == []


def test_bajadas_favoritas_alert_ignores_criteria_too():
    filtro = _filtro({"precio_max": 999999}, tipo_alerta=TIPO_BAJADAS_FAVORITAS)
    assert FilterMatcher.get_matching_properties([_prop()], filtro) == []


# ── invalid / empty criteria fail closed ────────────────────────────────────


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]", '"text"', "5", "null"])
def test_corrupt_or_non_object_criteria_match_nothing(raw):
    filtro = _filtro(raw=raw)
    assert FilterMatcher.get_matching_properties([_prop()], filtro) == []


def test_corrupt_criteria_is_logged_at_error(caplog):
    with caplog.at_level(logging.ERROR):
        FilterMatcher.get_matching_properties([_prop()], _filtro(raw="{oops"))
    assert any("criterios" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_criteria_on_a_nuevas_alert_matches_nothing(raw):
    filtro = FiltroAlerta(nombre="legacy", criterios_json=raw, precio_max=1.0)
    assert FilterMatcher.get_matching_properties([_prop()], filtro) == []


def test_explicit_empty_object_still_means_all_new_listings():
    """The UI stores '{}' for a deliberate 'no criteria' alert."""
    filtro = _filtro({})
    prop = _prop()
    assert FilterMatcher.get_matching_properties([prop], filtro) == [prop]


def test_parse_criteria_stays_lenient_for_display():
    assert FilterMatcher.parse_criteria("{oops") == {}
    assert FilterMatcher.parse_criteria(None) == {}


# ── unknown criterion keys fail closed ──────────────────────────────────────


def test_unknown_criterion_key_matches_nothing():
    assert FilterMatcher.match_property(_prop(), {"colour": "red"}) is False


def test_unknown_criterion_key_is_logged(caplog):
    with caplog.at_level(logging.ERROR):
        FilterMatcher.match_property(_prop(), {"colour": "red"})
    assert any("colour" in r.getMessage() for r in caplog.records)


def test_unknown_criterion_with_empty_value_is_still_skipped():
    assert FilterMatcher.match_property(_prop(), {"colour": ""}) is True


def test_false_boolean_criterion_is_skipped_not_unknown():
    assert FilterMatcher.match_property(_prop(ascensor=False), {"ascensor": False}) is True


# ── never raise out of a round ──────────────────────────────────────────────


def test_year_built_criterion_does_not_raise_and_does_not_match():
    prop = _prop()
    assert FilterMatcher.match_property(prop, {"año_construccion_min": 2000}) is False


def test_uncoercible_value_does_not_raise():
    assert FilterMatcher.match_property(_prop(), {"precio_max": "abc"}) is False


def test_one_bad_property_does_not_hide_the_others():
    good = _prop(precio=90000.0)
    filtro = _filtro({"precio_max": 100000, "año_construccion_min": 2000})
    assert FilterMatcher.get_matching_properties([good], filtro) == []
    filtro2 = _filtro({"precio_max": 100000})
    assert FilterMatcher.get_matching_properties([good], filtro2) == [good]


# ── tipo_operacion criterion ────────────────────────────────────────────────


def test_tipo_operacion_venta_excludes_rentals():
    venta = _prop(tipo_operacion="venta")
    alquiler = _prop(tipo_operacion="alquiler")
    filtro = _filtro({"tipo_operacion": "venta"})
    assert FilterMatcher.get_matching_properties([venta, alquiler], filtro) == [venta]


def test_tipo_operacion_is_case_insensitive():
    assert FilterMatcher.match_property(_prop(tipo_operacion="Venta"), {"tipo_operacion": "venta"}) is True


def test_tipo_operacion_unknown_on_property_does_not_match():
    assert FilterMatcher.match_property(_prop(tipo_operacion=None), {"tipo_operacion": "venta"}) is False


def test_create_criteria_dict_supports_tipo_operacion():
    assert FilterMatcher.create_criteria_dict(tipo_operacion="alquiler") == {
        "tipo_operacion": "alquiler"
    }


def test_format_criteria_mentions_tipo_operacion():
    assert "alquiler" in FilterMatcher.format_criteria({"tipo_operacion": "alquiler"})

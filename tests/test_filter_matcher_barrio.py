"""Tests for FilterMatcher's barrio (zona) OR-matching."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from notifications.filter_matcher import FilterMatcher
from db.models import Propiedad


def _propiedad(barrio):
    return Propiedad(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="test",
        titulo="t", barrio=barrio,
    )


def test_barrio_single_legacy_value_still_matches():
    """Backward compat: old alerts stored a single value with no commas."""
    prop = _propiedad("Valdelagrana")
    assert FilterMatcher._match_criterion(prop, "barrio", "valdelagrana") is True


def test_barrio_matches_any_of_several_zones():
    prop = _propiedad("Crevillet-Pinar Alto")
    value = "vistahermosa, crevillet, menesteo"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True


def test_barrio_no_match_when_none_of_the_zones_present():
    prop = _propiedad("Vistahermosa")
    value = "crevillet, pinar alto, menesteo"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is False


def test_barrio_accepts_real_list_not_just_string():
    prop = _propiedad("Pago de la Alhaja")
    value = ["crevillet", "pago de la alhaja"]
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True


def test_barrio_none_when_property_has_no_barrio():
    prop = _propiedad(None)
    assert FilterMatcher._match_criterion(prop, "barrio", "crevillet") is False


def test_barrio_ignores_blank_entries_in_list():
    prop = _propiedad("Crevillet")
    value = "crevillet, , pinar alto"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True

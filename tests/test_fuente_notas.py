"""Fuente `notas` handling behind the admin Fuentes page (#46).

The Streamlit page cannot be imported in tests, so the option list, config
templates and the save-time merge live in app/admin/fuente_notas.py.
Saving an edit must never overwrite a scraper config the form cannot represent.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import add_neopolis_fuente as seed
from admin.fuente_notas import (
    DETAIL_SCRAPER_OPTIONS,
    SCRAPER_CONFIG_TEMPLATES,
    build_notas,
    detail_options_for,
    merge_notas,
    parse_notas,
)
from scraper.detail_factory import DETAIL_SCRAPERS

NEOPOLIS_NOTAS = json.dumps(seed.NOTAS_CONFIG)


def _cfg(notas):
    return json.loads(notas)


def test_every_detail_scraper_is_selectable_in_the_ui():
    option_values = {value for _, value in DETAIL_SCRAPER_OPTIONS}

    missing = set(DETAIL_SCRAPERS) - {"manual_auto"} - option_values

    assert not missing


def test_neopolis_template_is_the_seed_config():
    assert SCRAPER_CONFIG_TEMPLATES["neopolis"] == seed.NOTAS_CONFIG


def test_editing_name_or_interval_only_leaves_neopolis_notas_untouched():
    # The form hands back the current type and the current max_pages.
    result = merge_notas(NEOPOLIS_NOTAS, "neopolis", seed.NOTAS_CONFIG["max_pages"])

    assert result == NEOPOLIS_NOTAS


def test_neopolis_keeps_selectors_and_type_when_max_pages_changes():
    result = _cfg(merge_notas(NEOPOLIS_NOTAS, "neopolis", 3))

    assert result["max_pages"] == 3
    assert result["detail_scraper_type"] == "neopolis"
    assert result["selectors"]["link_href_contains"] == "ficha/"
    assert result["pagination_param"] == "pag"


def test_max_pages_zero_removes_only_the_limit():
    result = _cfg(merge_notas(NEOPOLIS_NOTAS, "neopolis", 0))

    assert "max_pages" not in result
    assert result["selectors"]["link_href_contains"] == "ficha/"


def test_custom_fields_survive_an_edit_of_a_type_that_has_a_template():
    custom = json.dumps({**SCRAPER_CONFIG_TEMPLATES["puertopiso"], "municipio_filter": "Otro", "timeout": 99})

    result = _cfg(merge_notas(custom, "puertopiso", 10))

    assert result["municipio_filter"] == "Otro"
    assert result["timeout"] == 99


def test_unknown_detail_type_is_preserved_when_the_form_keeps_it():
    notas = json.dumps({"detail_scraper_type": "futuro", "selectors": {"link_href_contains": "x/"}})
    options = detail_options_for("futuro")

    assert ("futuro (personalizado, se conserva)", "futuro") in options
    assert merge_notas(notas, "futuro", 0) == notas


def test_known_or_missing_detail_type_adds_no_extra_option():
    assert detail_options_for("neopolis") == DETAIL_SCRAPER_OPTIONS
    assert detail_options_for(None) == DETAIL_SCRAPER_OPTIONS


def test_explicitly_switching_to_a_templated_type_applies_its_template():
    result = _cfg(merge_notas(NEOPOLIS_NOTAS, "guadalete", None))

    assert result == SCRAPER_CONFIG_TEMPLATES["guadalete"]


def test_switching_to_a_type_without_template_only_changes_the_type():
    result = _cfg(merge_notas(NEOPOLIS_NOTAS, "uriahomes", None))

    assert result["detail_scraper_type"] == "uriahomes"
    assert result["selectors"] == seed.NOTAS_CONFIG["selectors"]


def test_switching_to_generic_drops_only_the_type_key():
    result = _cfg(merge_notas(NEOPOLIS_NOTAS, None, None))

    assert "detail_scraper_type" not in result
    assert result["selectors"]["link_href_contains"] == "ficha/"


def test_free_text_notas_survive_a_generic_save():
    assert merge_notas("llamar el lunes", None, 0) == "llamar el lunes"


def test_empty_notas_with_generic_stays_empty():
    assert merge_notas(None, None, 0) is None


def test_new_fuente_gets_the_template_config():
    assert _cfg(build_notas("guadalete", None)) == SCRAPER_CONFIG_TEMPLATES["guadalete"]
    assert _cfg(build_notas("guadalete", 5))["max_pages"] == 5
    assert "max_pages" not in _cfg(build_notas("guadalete", 0))


def test_new_fuente_of_a_type_without_template_still_records_the_type():
    assert _cfg(build_notas("uriahomes", 0)) == {"detail_scraper_type": "uriahomes"}
    assert build_notas(None, 5) is None


def test_parse_notas_returns_empty_dict_for_non_config_values():
    assert parse_notas(None) == {}
    assert parse_notas("texto libre") == {}
    assert parse_notas("[1, 2]") == {}
    assert parse_notas(NEOPOLIS_NOTAS)["detail_scraper_type"] == "neopolis"

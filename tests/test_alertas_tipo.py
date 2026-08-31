"""tipo_alerta handling in the alerts page: criteria are cleared for a
`bajadas_favoritas` alert and switching back does not restore them.

Uses the importlib pattern from tests/test_alertas_criteria.py — full widget
behaviour needs a live Streamlit runtime (verified manually).
"""
import sys
from pathlib import Path

import importlib.util

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "pages"))

spec = importlib.util.spec_from_file_location(
    "alertas_page", str(Path(__file__).parent.parent / "app" / "pages" / "3_alertas.py")
)
alertas_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alertas_page)

resolve_criterios_json = alertas_page.resolve_criterios_json


def test_bajadas_favoritas_stores_no_criteria():
    assert resolve_criterios_json("bajadas_favoritas", {"precio_max": 200000}) is None


def test_nuevas_serializes_criteria_as_json():
    out = resolve_criterios_json("nuevas", {"precio_max": 200000})
    assert '"precio_max": 200000' in out


def test_switch_nuevas_to_favoritas_clears_existing_criteria():
    existing = {"precio_max": 150000, "barrio": "centro"}
    # user edits an existing "nuevas" alert and switches it to favoritas
    assert resolve_criterios_json("bajadas_favoritas", existing) is None


def test_switch_back_to_nuevas_does_not_restore_prior_criteria():
    # after the clear, the form criteria are empty; switching back keeps them empty
    assert resolve_criterios_json("nuevas", {}) == "{}"

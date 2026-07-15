"""Tests for build_criteria's zona (barrio) list handling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "pages"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "alertas_page", str(Path(__file__).parent.parent / "app" / "pages" / "3_alertas.py")
)
alertas_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alertas_page)

build_criteria = alertas_page.build_criteria


def _call(barrio):
    return build_criteria(
        precio_min=0, precio_max=0, m2_min=0, m2_max=0, habitaciones=0, banos=0,
        barrio=barrio, tipo_propiedad=None, estado=None, amenidades=[],
        ascensor=False, garaje=False, terraza=False, piscina=False,
    )


def test_build_criteria_joins_multiple_zones():
    criteria = _call(["crevillet", "pinar alto", "menesteo"])
    assert criteria["barrio"] == "crevillet, pinar alto, menesteo"


def test_build_criteria_single_zone():
    criteria = _call(["crevillet"])
    assert criteria["barrio"] == "crevillet"


def test_build_criteria_empty_list_is_none():
    criteria = _call([])
    assert criteria.get("barrio") is None

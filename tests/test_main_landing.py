"""Tests for the scraper-admin landing in app/main.py.

app/main.py is a top-level Streamlit script that executes on import (page config,
DB boot guard, st.stop on failure), so it cannot be imported in isolation without
a live database. These tests assert on its source text instead: the landing must
present scraper-administration framing and must preserve the cached init_db()
boot guard.
"""
import re
from pathlib import Path

MAIN_PY = Path(__file__).parent.parent / "app" / "main.py"


def _source() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


def test_landing_references_admin_sections():
    src = _source().lower()
    assert "fuentes" in src
    assert "ejecuciones" in src
    assert "alertas" in src


def test_landing_drops_consumer_framing():
    src = _source().lower()
    for banned in ("ver propiedades", "buscar vivienda", "calculadora", "estadísticas", "estadisticas"):
        assert banned not in src, f"consumer framing still present: {banned!r}"


def test_landing_has_no_property_search_pitch():
    src = _source().lower()
    # The old sidebar pitched "filtra propiedades según tus preferencias" as the
    # product. The admin portal orients around running scrapers, not home search.
    assert "filtra propiedades según tus preferencias" not in src
    assert "explora todas las propiedades" not in src


def test_db_boot_guard_preserved():
    src = _source()
    # init_database is defined once, cached, and invoked exactly once.
    assert src.count("def init_database(") == 1
    assert "@st.cache_resource" in src
    assert len(re.findall(r"^\s*db_ready = init_database\(\)", src, re.MULTILINE)) == 1
    # SELECT 1 connectivity probe and the hard stop on failure remain.
    assert 'text("SELECT 1")' in src
    assert "st.stop()" in src
    # A DB failure still surfaces a visible error to the operator.
    assert "st.error(" in src


def test_getting_started_is_scraper_oriented():
    src = _source().lower()
    # Steps should walk an operator through configuring a Fuente and watching runs,
    # not through setting home-search filters.
    assert "fuente" in src
    assert "scraper" in src or "scrape" in src

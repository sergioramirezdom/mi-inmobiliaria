"""Tests that 'samper' detail_scraper_type is wired consistently across
sold_checker, the shared factory, and the admin UI (app/pages/1_fuentes.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.sold_checker import _get_scraper
from scraper.samper_scraper import SamperScraper
from scraper.config import ScraperConfig


def test_sold_checker_routes_samper():
    config = ScraperConfig(detail_scraper_type="samper")
    scraper = _get_scraper("samper", config)
    assert isinstance(scraper, SamperScraper)


def _load_fuentes_page_module():
    """Import app/pages/1_fuentes.py constants without running the Streamlit page.

    Mirrors the module-level dicts directly rather than executing the whole
    Streamlit script (which needs a live DB connection).
    """
    import ast

    source = (Path(__file__).parent.parent / "app" / "pages" / "1_fuentes.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    namespace = {"str": str, "json": json}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("DETAIL_SCRAPER_OPTIONS", "SCRAPER_CONFIG_TEMPLATES")
            for t in node.targets
        ):
            code = compile(ast.Module(body=[node], type_ignores=[]), "<fuentes>", "exec")
            exec(code, namespace)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_notas":
            code = compile(ast.Module(body=[node], type_ignores=[]), "<fuentes>", "exec")
            exec(code, namespace)
    return namespace


def test_samper_in_detail_scraper_options():
    ns = _load_fuentes_page_module()
    values = [v for _, v in ns["DETAIL_SCRAPER_OPTIONS"]]
    assert "samper" in values


def test_samper_in_scraper_config_templates():
    ns = _load_fuentes_page_module()
    assert "samper" in ns["SCRAPER_CONFIG_TEMPLATES"]
    template = ns["SCRAPER_CONFIG_TEMPLATES"]["samper"]
    assert template["detail_scraper_type"] == "samper"
    assert template["selectors"]["link_href_contains"] == "/Venta-"
    assert template["use_results_per_page"] is False


def test_build_notas_round_trips_for_samper():
    ns = _load_fuentes_page_module()
    ns["SCRAPER_CONFIG_TEMPLATES"] = ns["SCRAPER_CONFIG_TEMPLATES"]
    notas_json = ns["_build_notas"]("samper")
    assert notas_json is not None
    parsed = json.loads(notas_json)
    assert parsed["detail_scraper_type"] == "samper"

    config = ScraperConfig.from_fuente_notas(notas_json)
    assert config.detail_scraper_type == "samper"


def test_link_href_contains_is_ascii_only():
    ns = _load_fuentes_page_module()
    template = ns["SCRAPER_CONFIG_TEMPLATES"]["samper"]
    assert template["selectors"]["link_href_contains"].isascii()

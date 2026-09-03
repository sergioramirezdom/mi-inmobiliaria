"""Tests that 'tular' detail_scraper_type is wired consistently across
sold_checker, the shared factory, the admin UI (app/pages/1_fuentes.py) and
the one-off seed script (scripts/add_tular_fuente.py).

Also guards bug #43: NO ``municipio_filter`` key may appear in the Tular
notas template or seed config — in ``link_href_contains``-only mode the
listing title is always a placeholder, so a municipio filter would silently
drop 100% of results before the detail scraper runs.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.sold_checker import _get_scraper
from scraper.tular_scraper import TularScraper
from scraper.config import ScraperConfig
from scraper.generic import GenericScraper

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_sold_checker_routes_tular():
    config = ScraperConfig(detail_scraper_type="tular")
    scraper = _get_scraper("tular", config)
    assert isinstance(scraper, TularScraper)


def _load_fuentes_page_module():
    """Import app/pages/1_fuentes.py constants without running the Streamlit page."""
    import ast

    source = (Path(__file__).parent.parent / "app" / "pages" / "1_fuentes.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    namespace = {"str": str, "json": json}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name)
            and t.id in ("DETAIL_SCRAPER_OPTIONS", "SCRAPER_CONFIG_TEMPLATES")
            for t in node.targets
        ):
            code = compile(ast.Module(body=[node], type_ignores=[]), "<fuentes>", "exec")
            exec(code, namespace)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_notas":
            code = compile(ast.Module(body=[node], type_ignores=[]), "<fuentes>", "exec")
            exec(code, namespace)
    return namespace


def test_tular_in_detail_scraper_options():
    ns = _load_fuentes_page_module()
    values = [v for _, v in ns["DETAIL_SCRAPER_OPTIONS"]]
    assert "tular" in values


def test_tular_in_scraper_config_templates():
    ns = _load_fuentes_page_module()
    assert "tular" in ns["SCRAPER_CONFIG_TEMPLATES"]
    template = ns["SCRAPER_CONFIG_TEMPLATES"]["tular"]
    assert template["detail_scraper_type"] == "tular"
    assert template["selectors"]["link_href_contains"] == "/Venta-"
    assert template["use_results_per_page"] is False
    assert template["pagination_param"] == "pag"
    assert template["max_pages"] == 1


def test_tular_template_has_no_municipio_filter():
    ns = _load_fuentes_page_module()
    assert "municipio_filter" not in ns["SCRAPER_CONFIG_TEMPLATES"]["tular"]


def test_build_notas_round_trips_for_tular():
    ns = _load_fuentes_page_module()
    notas_json = ns["_build_notas"]("tular")
    assert notas_json is not None
    parsed = json.loads(notas_json)
    assert parsed["detail_scraper_type"] == "tular"
    assert "municipio_filter" not in parsed

    config = ScraperConfig.from_fuente_notas(notas_json)
    assert config.detail_scraper_type == "tular"


def test_link_href_contains_is_ascii_only():
    ns = _load_fuentes_page_module()
    template = ns["SCRAPER_CONFIG_TEMPLATES"]["tular"]
    value = template["selectors"]["link_href_contains"]
    assert value == "/Venta-"
    assert value.isascii()


# ── task 2.11 — listing-page detail URL discovery (accent-safe) ──────────────


def test_generic_scraper_finds_venta_links_under_both_href_spellings():
    """GenericScraper must collect tular detail URLs whether the href carries
    a literal accent (María) or the percent-encoded form (%C3%ADa)."""
    listing_html = """
    <html><body>
      <a href="/Venta-Piso-El-Puerto-de-Santa-María-CREVILLET-811">literal accent</a>
      <a href="/Venta-Piso-El-Puerto-de-Santa-Mar%C3%ADa-CENTRO-798">percent-encoded</a>
      <a href="/nosotros">unrelated</a>
      <a href="#">pagination</a>
    </body></html>
    """
    config = ScraperConfig.from_dict({"selectors": {"link_href_contains": "/Venta-"}})
    scraper = GenericScraper(config)
    elements = scraper._parse_properties(listing_html)
    hrefs = {el.get("href") for el in elements}
    assert hrefs == {
        "/Venta-Piso-El-Puerto-de-Santa-María-CREVILLET-811",
        "/Venta-Piso-El-Puerto-de-Santa-Mar%C3%ADa-CENTRO-798",
    }


def test_generic_scraper_finds_venta_links_in_real_fixture():
    listing_html = (FIXTURES_DIR / "tular_listado.html").read_text(encoding="utf-8")
    config = ScraperConfig.from_dict({"selectors": {"link_href_contains": "/Venta-"}})
    scraper = GenericScraper(config)
    elements = scraper._parse_properties(listing_html)
    assert len(elements) >= 5
    assert all("/Venta-" in el.get("href") for el in elements)


# ── task 4.2 — seed script parity ──────────────────────────────────────────


def _load_seed_script():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import add_tular_fuente

    return add_tular_fuente


def test_seed_script_notas_has_no_municipio_filter():
    mod = _load_seed_script()
    assert "municipio_filter" not in mod.NOTAS_CONFIG


def test_seed_script_notas_matches_ui_template():
    mod = _load_seed_script()
    ns = _load_fuentes_page_module()
    assert mod.NOTAS_CONFIG == ns["SCRAPER_CONFIG_TEMPLATES"]["tular"]


def test_seed_script_fuente_kwargs():
    mod = _load_seed_script()
    assert mod.TULAR_URL.startswith("https://www.tular.es/buscar.php?")
    assert "check_tipo_inmueble%5B%5D=Vivienda" in mod.TULAR_URL
    assert "po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa" in mod.TULAR_URL

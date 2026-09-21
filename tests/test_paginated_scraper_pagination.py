"""PaginatedScraper pagination loop: visible failures and safe termination (#47)."""
import ast
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import scraper.paginated_scraper as pag_mod
from scraper.config import ScraperConfig, SelectorsConfig
from scraper.paginated_scraper import PaginatedScraper
from db.models import Fuente

SAFETY_LIMIT = 120  # fake site gives up here so a regression fails instead of hanging


class FakeDBSession:
    """No existing rows; records added objects."""

    def __init__(self):
        self.added = []

    def exec(self, stmt):
        result = MagicMock()
        result.first.return_value = None
        return result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeDetailScraper:
    async def scrape_property_details(self, url):
        return {}


def _fuente(url="http://example.com/venta"):
    return Fuente(id=1, nombre="Test", url=url, tipo_scraper="generic", activa=True, intervalo_horas=6)


def _item(n=1):
    return {"url_original": f"http://example.com/venta/piso-en-venta-{n}", "titulo": "Piso en venta", "precio": 100000}


def _paginated(monkeypatch, config=None, scrape=None):
    config = config or ScraperConfig(use_results_per_page=False)
    paginated = PaginatedScraper(db_session=FakeDBSession(), config=config)
    if scrape is not None:
        monkeypatch.setattr(paginated.generic_scraper, "scrape", scrape)
    monkeypatch.setattr(pag_mod, "get_detail_scraper", lambda t, c: FakeDetailScraper())
    return paginated


class CountingSite:
    """Fake generic_scraper.scrape: counts calls, raises past SAFETY_LIMIT."""

    def __init__(self, pages):
        self.pages = pages  # callable(call_number) -> list of raw dicts
        self.calls = 0
        self.urls = []

    async def __call__(self, temp_fuente):
        self.calls += 1
        self.urls.append(temp_fuente.url)
        if self.calls > SAFETY_LIMIT:
            raise RuntimeError("runaway pagination")
        return self.pages(self.calls)


# ── failures must be visible ─────────────────────────────────────────────────

async def test_fetch_error_on_page_1_sets_stats_error(monkeypatch):
    site = AsyncMock(side_effect=RuntimeError("HTTP 403"))
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente())

    assert stats["error"]
    assert "403" in stats["error"]
    assert stats["urls_encontradas"] == 0


async def test_fetch_error_after_partial_results_keeps_them_but_flags_run(monkeypatch):
    site = AsyncMock(side_effect=[[_item(1)], RuntimeError("timeout")])
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente())

    assert stats["nuevas"] == 1
    assert stats["error"]


async def test_selector_matching_nothing_on_page_1_is_flagged(monkeypatch):
    config = ScraperConfig(
        use_results_per_page=False,
        selectors=SelectorsConfig(property_container=".listing-card"),
    )
    paginated = _paginated(monkeypatch, config=config)
    monkeypatch.setattr(
        paginated.generic_scraper, "fetch_content",
        AsyncMock(return_value="<html><body><p>redesigned site</p></body></html>"),
    )

    stats = await paginated.scrape_all_pages(_fuente())

    assert stats["urls_encontradas"] == 0
    assert stats["error"]
    assert "Page 1" in stats["error"]


async def test_healthy_run_has_no_error(monkeypatch):
    site = CountingSite(lambda n: [_item(n)] if n == 1 else [])
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente())

    assert stats.get("error") is None
    assert stats["nuevas"] == 1


# ── termination ──────────────────────────────────────────────────────────────

async def test_identical_page_for_any_pag_terminates(monkeypatch):
    site = CountingSite(lambda n: [_item(1)])
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente())

    assert site.calls <= 3
    assert stats["nuevas"] == 1
    assert stats.get("error") is None


@pytest.mark.parametrize("max_pages", [None, 0])
async def test_unbounded_max_pages_still_terminates_via_default_cap(monkeypatch, max_pages):
    site = CountingSite(lambda n: [_item(n)])  # always-new URLs, never-ending site
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente(), max_pages=max_pages)

    assert site.calls == pag_mod.DEFAULT_MAX_PAGES
    assert stats["paginas_procesadas"] == pag_mod.DEFAULT_MAX_PAGES


async def test_explicit_max_pages_is_respected(monkeypatch):
    site = CountingSite(lambda n: [_item(n)])
    await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente(), max_pages=3)

    assert site.calls == 3


# ── URL building ─────────────────────────────────────────────────────────────

async def test_res_param_uses_question_mark_when_url_has_no_query(monkeypatch):
    config = ScraperConfig(use_results_per_page=True, pagination_skip_first=True)
    site = CountingSite(lambda n: [_item(n)] if n == 1 else [])
    await _paginated(monkeypatch, config=config, scrape=site).scrape_all_pages(
        _fuente("http://example.com/venta")
    )

    assert site.urls[0] == "http://example.com/venta?res=48"


# ── no silent swallowing ─────────────────────────────────────────────────────

def test_no_bare_except_exception_pass_in_module():
    tree = ast.parse(Path(pag_mod.__file__).read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    ]
    assert offenders == []


async def test_failed_reenrich_is_counted_not_hidden(monkeypatch):
    from datetime import datetime

    existing = MagicMock()
    existing.activa = True
    existing.precio = None  # triggers the re-enrich block
    existing.fecha_scraping = datetime.utcnow()
    existing.titulo = "Piso"

    class Session(FakeDBSession):
        def exec(self, stmt):
            result = MagicMock()
            result.first.return_value = existing
            return result

    class Boom:
        async def scrape_property_details(self, url):
            raise RuntimeError("detail page down")

    site = CountingSite(lambda n: [_item(1)] if n == 1 else [])
    paginated = PaginatedScraper(db_session=Session(), config=ScraperConfig(use_results_per_page=False))
    monkeypatch.setattr(paginated.generic_scraper, "scrape", site)
    monkeypatch.setattr(pag_mod, "get_detail_scraper", lambda t, c: Boom())

    stats = await paginated.scrape_all_pages(_fuente())

    assert stats["duplicadas"] == 1
    assert stats["detalle_fallido"] == 1


# ── per-reason counters ──────────────────────────────────────────────────────

async def test_skip_reason_counters_always_present(monkeypatch):
    site = CountingSite(lambda n: [_item(1)] if n == 1 else [])
    stats = await _paginated(monkeypatch, scrape=site).scrape_all_pages(_fuente())

    for key in ("filtradas_municipio", "alquileres", "garajes", "vendidas"):
        assert stats[key] == 0

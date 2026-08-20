"""Tests for paginated_scraper.py's 3-day duplicate re-check routed through
classify_check_outcome()/apply_check_outcome() (T5) — same shared strike
counter (`Propiedad.intentos_fallidos`) used by sold_checker.py.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import scraper.paginated_scraper as pag_mod
from scraper.paginated_scraper import PaginatedScraper
from db.models import Fuente


class FakeDBSession:
    """Always returns the preset `existing` row for any select(); records writes."""

    def __init__(self, existing):
        self.existing = existing
        self.added = []
        self.commits = 0

    def exec(self, stmt):
        result = MagicMock()
        result.first.return_value = self.existing
        return result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


class FakeDetailScraper:
    """No `canonicalize_url` attribute — avoids the hasattr() branch in
    paginated_scraper.py, unlike a bare MagicMock which auto-creates attrs."""

    def __init__(self, fetch):
        self._fetch = fetch

    async def scrape_property_details(self, url):
        return await self._fetch(url)


def _existing(intentos_fallidos=0, activa=True, precio=100000, prop_id=1):
    existing = MagicMock()
    existing.id = prop_id
    existing.activa = activa
    existing.precio = precio
    existing.precio_anterior = None
    existing.updated_at = None
    existing.estado = None
    existing.fecha_baja = None
    existing.fecha_scraping = datetime.utcnow() - timedelta(days=5)
    existing.intentos_fallidos = intentos_fallidos
    existing.titulo = "Piso en venta"
    existing.url_original = "http://example.com/prop/1"
    return existing


def _fuente():
    return Fuente(id=1, nombre="Test", url="http://example.com", activa=True, intervalo_horas=6)


async def _run(monkeypatch, existing, fetch):
    session = FakeDBSession(existing)
    paginated = PaginatedScraper(db_session=session)

    async def scrape_side_effect(temp_fuente):
        return [{"url_original": existing.url_original, "titulo": "Piso en venta"}]

    monkeypatch.setattr(paginated.generic_scraper, "scrape", AsyncMock(
        side_effect=[await scrape_side_effect(None), []]
    ))
    monkeypatch.setattr(
        pag_mod, "get_detail_scraper",
        lambda detail_type, config: FakeDetailScraper(fetch),
    )

    stats = await paginated.scrape_all_pages(_fuente())
    return stats, session


async def test_gone_outcome_deactivates_immediately_no_strike(monkeypatch):
    existing = _existing(intentos_fallidos=0)

    async def fetch(url):
        return {"activa": False, "estado": "Vendida"}

    stats, session = await _run(monkeypatch, existing, fetch)

    assert existing.activa is False
    assert existing.intentos_fallidos == 0
    assert stats.get("vendidas", 0) == 1


async def test_empty_on_strike_zero_leaves_active_and_does_not_count_as_vendida(monkeypatch):
    existing = _existing(intentos_fallidos=0)

    async def fetch(url):
        return {}

    stats, session = await _run(monkeypatch, existing, fetch)

    assert existing.activa is True
    assert existing.intentos_fallidos == 1
    assert stats.get("vendidas", 0) == 0


async def test_empty_on_strike_one_deactivates_and_counts_as_vendida(monkeypatch):
    """Cross-module shared counter: a strike issued earlier (e.g. by
    sold_checker) is honored here and this run's EMPTY confirms it."""
    existing = _existing(intentos_fallidos=1)

    async def fetch(url):
        return {}

    stats, session = await _run(monkeypatch, existing, fetch)

    assert existing.activa is False
    assert existing.intentos_fallidos == 0
    assert stats.get("vendidas", 0) == 1


async def test_fetch_exception_leaves_counter_and_activa_untouched(monkeypatch):
    existing = _existing(intentos_fallidos=1)

    async def fetch(url):
        raise Exception("Timeout")

    stats, session = await _run(monkeypatch, existing, fetch)

    assert existing.activa is True
    assert existing.intentos_fallidos == 1
    assert stats.get("vendidas", 0) == 0


async def test_price_change_logic_fires_only_on_alive(monkeypatch):
    existing = _existing(intentos_fallidos=0, precio=100000)

    async def fetch(url):
        return {"titulo": "Piso en venta", "precio": 90000}

    stats, session = await _run(monkeypatch, existing, fetch)

    assert existing.activa is True
    assert existing.precio == 90000
    assert existing.precio_anterior == 100000
    assert len(stats.get("bajadas_precio", [])) == 1

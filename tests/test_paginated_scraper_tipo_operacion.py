"""PaginatedScraper must persist an explicit tipo_operacion for new listings (#48)."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import scraper.paginated_scraper as pag_mod
from scraper.paginated_scraper import PaginatedScraper
from db.models import Fuente


class FakeDBSession:
    """No existing rows; records every added object."""

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


def _fuente():
    return Fuente(id=1, nombre="Test", url="http://example.com/venta", activa=True, intervalo_horas=6)


async def _run(monkeypatch, listing):
    session = FakeDBSession()
    paginated = PaginatedScraper(db_session=session)
    monkeypatch.setattr(paginated.generic_scraper, "scrape", AsyncMock(side_effect=[[listing], []]))
    monkeypatch.setattr(pag_mod, "get_detail_scraper", lambda t, c: FakeDetailScraper())
    stats = await paginated.scrape_all_pages(_fuente())
    saved = [o for o in session.added if hasattr(o, "tipo_operacion")]
    return stats, saved


@pytest.mark.parametrize("url,titulo,expected", [
    # detector positively says venta (keyword in title/URL)
    ("http://example.com/piso-en-venta/1", "Piso en venta", "venta"),
    # detector uncertain -> defaults to venta
    ("http://example.com/prop/2", "Piso luminoso", "venta"),
])
async def test_new_property_gets_explicit_tipo_operacion(monkeypatch, url, titulo, expected):
    stats, saved = await _run(monkeypatch, {"url_original": url, "titulo": titulo, "precio": 150000})

    assert stats["nuevas"] == 1
    assert saved[0].tipo_operacion == expected

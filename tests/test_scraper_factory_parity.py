"""Regression tests for the Aug 20 incident: sold_checker and paginated_scraper
must resolve detail scrapers through the SAME shared factory
(app/scraper/detail_factory.py), so a `detail_scraper_type` supported by one
call site cannot silently fall through to the generic default on the other.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pytest

from scraper.sold_checker import _get_scraper
from scraper.config import ScraperConfig
from scraper.uriahomes_scraper import UriaHomesScraper
from scraper.jimenezruiz_scraper import JimenezRuizScraper
from scraper.puerto_inmobiliaria import PuertoInmobiliariaScraper
from scraper.paginated_scraper import PaginatedScraper


def test_sold_checker_resolves_uriahomes_via_shared_factory():
    """The exact Aug 20 regression: uriahomes must NOT fall back to the
    generic PuertoInmobiliariaScraper inside sold_checker's own call path."""
    scraper = _get_scraper("uriahomes", ScraperConfig())
    assert isinstance(scraper, UriaHomesScraper)
    assert not isinstance(scraper, PuertoInmobiliariaScraper)


def test_sold_checker_resolves_jimenezruiz_via_shared_factory():
    """jimenezruiz was ALSO missing from sold_checker's old inline chain."""
    scraper = _get_scraper("jimenezruiz", ScraperConfig())
    assert isinstance(scraper, JimenezRuizScraper)


@pytest.mark.parametrize(
    "detail_type,expected_class",
    [
        ("uriahomes", UriaHomesScraper),
        ("jimenezruiz", JimenezRuizScraper),
    ],
)
async def test_paginated_scraper_resolves_same_class_as_sold_checker(
    monkeypatch, detail_type, expected_class
):
    """Parity check: both call sites must pick the SAME class for the same
    detail_scraper_type, proving they route through one shared registry."""
    from db.models import Fuente

    sold_checker_scraper = _get_scraper(detail_type, ScraperConfig())
    assert isinstance(sold_checker_scraper, expected_class)

    paginated = PaginatedScraper(db_session=None)
    fuente = Fuente(
        id=1,
        nombre="Test",
        url="http://example.com",
        notas=f'{{"detail_scraper_type": "{detail_type}"}}',
    )
    # Force pagination to exit immediately after resolving the detail scraper.
    monkeypatch.setattr(
        paginated.generic_scraper, "scrape", AsyncMock(return_value=[])
    )

    await paginated.scrape_all_pages(fuente)

    assert isinstance(paginated.detail_scraper, expected_class)

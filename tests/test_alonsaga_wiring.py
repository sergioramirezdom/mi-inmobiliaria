"""Tests that 'alonsaga' detail_scraper_type routes to AlonsagaScraper."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.sold_checker import _get_scraper
from scraper.alonsaga_scraper import AlonsagaScraper
from scraper.config import ScraperConfig


def test_sold_checker_routes_alonsaga():
    config = ScraperConfig(detail_scraper_type="alonsaga")
    scraper = _get_scraper("alonsaga", config)
    assert isinstance(scraper, AlonsagaScraper)

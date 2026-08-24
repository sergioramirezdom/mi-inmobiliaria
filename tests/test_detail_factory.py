"""Tests for the shared detail-scraper factory (parity fix)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.config import ScraperConfig
from scraper.detail_factory import DETAIL_SCRAPERS, get_detail_scraper
from scraper.mobilia_scraper import MobiliaScraper
from scraper.punto_hogar_scraper import PuntoHogarScraper
from scraper.guadalete_scraper import GuadaleteScraper
from scraper.jimenezruiz_scraper import JimenezRuizScraper
from scraper.puertopiso_scraper import PuertoPisoScraper
from scraper.manual_scraper import ManualScraper
from scraper.alonsaga_scraper import AlonsagaScraper
from scraper.uriahomes_scraper import UriaHomesScraper
from scraper.neopolis_scraper import NeopolisScraper
from scraper.samper_scraper import SamperScraper
from scraper.puerto_inmobiliaria import PuertoInmobiliariaScraper


# The exact set of keys currently branched on in paginated_scraper.py's
# if/elif chain (lines ~78-96) — the parity source of truth per design.
EXPECTED_KEYS_TO_CLASSES = {
    "mobilia": MobiliaScraper,
    "puntohogar": PuntoHogarScraper,
    "guadalete": GuadaleteScraper,
    "jimenezruiz": JimenezRuizScraper,
    "puertopiso": PuertoPisoScraper,
    "manual_auto": ManualScraper,
    "alonsaga": AlonsagaScraper,
    "uriahomes": UriaHomesScraper,
    "neopolis": NeopolisScraper,
    "samper": SamperScraper,
}


def test_registry_contains_exact_paginated_scraper_keys():
    assert set(DETAIL_SCRAPERS.keys()) == set(EXPECTED_KEYS_TO_CLASSES.keys())


def test_registry_maps_each_key_to_expected_class():
    for key, expected_class in EXPECTED_KEYS_TO_CLASSES.items():
        assert DETAIL_SCRAPERS[key] is expected_class


def test_get_detail_scraper_returns_uriahomes_scraper():
    scraper = get_detail_scraper("uriahomes", ScraperConfig())
    assert isinstance(scraper, UriaHomesScraper)


def test_get_detail_scraper_returns_jimenezruiz_scraper():
    scraper = get_detail_scraper("jimenezruiz", ScraperConfig())
    assert isinstance(scraper, JimenezRuizScraper)


def test_get_detail_scraper_returns_samper_scraper():
    scraper = get_detail_scraper("samper", ScraperConfig())
    assert isinstance(scraper, SamperScraper)


def test_get_detail_scraper_none_returns_default():
    scraper = get_detail_scraper(None, ScraperConfig())
    assert isinstance(scraper, PuertoInmobiliariaScraper)


def test_get_detail_scraper_unknown_returns_default():
    scraper = get_detail_scraper("unknown-type", ScraperConfig())
    assert isinstance(scraper, PuertoInmobiliariaScraper)

"""Tests for scripts/add_neopolis_fuente.py — verifies the seed script builds
a NEOPOLIS `Fuente` whose `notas` JSON round-trips correctly, without ever
touching a live database (session is a MagicMock, matching the existing
RegistroEjecucionCRUD test convention).
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.models import Fuente
from scraper.config import ScraperConfig

import add_neopolis_fuente as seed


def test_neopolis_url_stored_verbatim():
    assert "limtipos=" in seed.NEOPOLIS_URL
    assert "areas=" in seed.NEOPOLIS_URL
    assert seed.NEOPOLIS_URL.startswith("https://www.neopolis.es/index.php?")


def test_notas_config_round_trips_into_scraper_config():
    notas_json = json.dumps(seed.NOTAS_CONFIG)
    config = ScraperConfig.from_fuente_notas(notas_json)

    assert config.detail_scraper_type == "neopolis"
    assert config.pagination_param == "pag"
    assert config.use_results_per_page is False
    assert config.selectors.link_href_contains == "ficha/"
    assert config.max_pages == 10


def test_main_creates_inactive_fuente_when_absent(monkeypatch):
    session = MagicMock()
    session.exec.return_value.first.return_value = None
    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False

    monkeypatch.setattr(seed, "Session", MagicMock(return_value=session_ctx))

    seed.main()

    session.add.assert_called_once()
    created_fuente = session.add.call_args[0][0]
    assert isinstance(created_fuente, Fuente)
    assert created_fuente.nombre == "NEOPOLIS"
    assert created_fuente.url == seed.NEOPOLIS_URL
    assert created_fuente.tipo_scraper == "generic"
    assert created_fuente.activa is False
    session.commit.assert_called_once()


def test_main_skips_when_fuente_already_exists(monkeypatch):
    session = MagicMock()
    session.exec.return_value.first.return_value = Fuente(
        id=1, nombre="NEOPOLIS", url=seed.NEOPOLIS_URL, activa=False,
    )
    session_ctx = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False

    monkeypatch.setattr(seed, "Session", MagicMock(return_value=session_ctx))

    seed.main()

    session.add.assert_not_called()

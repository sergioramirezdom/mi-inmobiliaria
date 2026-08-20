"""Tests for ScraperScheduler._scrape_fuente() writing a RegistroEjecucion
run-log row after each scrape (T8)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import scraper.scheduler as scheduler_mod
from scraper.scheduler import ScraperScheduler
from db.models import Fuente


class _FakeSessionCtx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, fuente):
        self._fuente = fuente
        self.added = []
        self.commits = 0

    def get(self, model, obj_id):
        return self._fuente

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _fuente():
    return Fuente(id=1, nombre="Test Fuente", url="http://example.com", activa=True, intervalo_horas=6)


async def test_scrape_fuente_writes_registro_ejecucion_row(monkeypatch):
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    stats = {
        "nuevas": 3,
        "duplicadas": 5,
        "errores": 1,
        "paginas_procesadas": 2,
        "tiempo_segundos": 12.5,
    }

    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)

    created = MagicMock()
    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", created)

    scheduler = ScraperScheduler()
    await scheduler._scrape_fuente(fuente)

    created.assert_called_once()
    call_session, registro = created.call_args[0]
    assert call_session is fake_session
    assert registro.tipo == "scrape"
    assert registro.fuente_id == fuente.id
    assert registro.nuevas == 3
    assert registro.duplicadas == 5
    assert registro.errores == 1
    assert registro.total == 3 + 5 + 1
    assert registro.duracion_segundos == 12.5


async def test_scrape_fuente_log_write_failure_does_not_block_the_run(monkeypatch):
    """A run-log write failure must never block notification sending / the run."""
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    stats = {"nuevas": 0, "duplicadas": 0, "errores": 0, "paginas_procesadas": 1, "tiempo_segundos": 1.0}

    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)

    def _boom(session, registro):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", _boom)

    scheduler = ScraperScheduler()
    # Must not raise.
    await scheduler._scrape_fuente(fuente)

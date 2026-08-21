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


async def test_scrape_fuente_passes_run_id_through_to_registro_ejecucion(monkeypatch):
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    stats = {"nuevas": 0, "duplicadas": 0, "errores": 0, "paginas_procesadas": 1, "tiempo_segundos": 1.0}

    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)

    created = MagicMock()
    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", created)

    scheduler = ScraperScheduler()
    await scheduler._scrape_fuente(fuente, run_id="fixed-run-id")

    call_session, registro = created.call_args[0]
    assert registro.run_id == "fixed-run-id"


async def test_check_and_scrape_shares_one_run_id_across_all_fuentes(monkeypatch):
    fuente_a = Fuente(id=1, nombre="A", url="http://example.com/a", activa=True, intervalo_horas=6, ultima_ejecucion=None)
    fuente_b = Fuente(id=2, nombre="B", url="http://example.com/b", activa=True, intervalo_horas=6, ultima_ejecucion=None)

    class _FuenteListSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def exec(self, stmt):
            result = MagicMock()
            result.all.return_value = [fuente_a, fuente_b]
            return result

    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FuenteListSession())

    seen_run_ids = []

    async def fake_scrape_fuente(self, fuente, run_id=None):
        seen_run_ids.append(run_id)

    monkeypatch.setattr(scheduler_mod.ScraperScheduler, "_scrape_fuente", fake_scrape_fuente)

    scheduler = ScraperScheduler()
    await scheduler.check_and_scrape()

    assert len(seen_run_ids) == 2
    assert seen_run_ids[0] is not None
    assert seen_run_ids[0] == seen_run_ids[1]

    first_run_id = seen_run_ids[0]

    seen_run_ids.clear()
    await scheduler.check_and_scrape()
    second_run_id = seen_run_ids[0]

    assert second_run_id is not None
    assert second_run_id != first_run_id


async def test_force_scrape_all_shares_one_run_id_across_all_fuentes(monkeypatch):
    fuente_a = Fuente(id=1, nombre="A", url="http://example.com/a", activa=True, intervalo_horas=6)
    fuente_b = Fuente(id=2, nombre="B", url="http://example.com/b", activa=True, intervalo_horas=6)

    class _FuenteListSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def exec(self, stmt):
            result = MagicMock()
            result.all.return_value = [fuente_a, fuente_b]
            return result

    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FuenteListSession())

    seen_run_ids = []

    async def fake_scrape_fuente(self, fuente, run_id=None):
        seen_run_ids.append(run_id)

    monkeypatch.setattr(scheduler_mod.ScraperScheduler, "_scrape_fuente", fake_scrape_fuente)

    scheduler = ScraperScheduler()
    await scheduler.force_scrape_all()

    assert len(seen_run_ids) == 2
    assert seen_run_ids[0] is not None
    assert seen_run_ids[0] == seen_run_ids[1]


async def test_force_scrape_all_generates_different_run_id_per_call(monkeypatch):
    fuente_a = Fuente(id=1, nombre="A", url="http://example.com/a", activa=True, intervalo_horas=6)

    class _FuenteListSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def exec(self, stmt):
            result = MagicMock()
            result.all.return_value = [fuente_a]
            return result

    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FuenteListSession())

    seen_run_ids = []

    async def fake_scrape_fuente(self, fuente, run_id=None):
        seen_run_ids.append(run_id)

    monkeypatch.setattr(scheduler_mod.ScraperScheduler, "_scrape_fuente", fake_scrape_fuente)

    scheduler = ScraperScheduler()
    await scheduler.force_scrape_all()
    await scheduler.force_scrape_all()

    assert seen_run_ids[0] != seen_run_ids[1]


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

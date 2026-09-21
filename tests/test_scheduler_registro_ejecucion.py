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


async def test_scrape_fuente_persists_encontradas_from_urls_encontradas(monkeypatch):
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    stats = {
        "nuevas": 3,
        "duplicadas": 5,
        "errores": 0,
        "urls_encontradas": 17,
        "paginas_procesadas": 2,
        "tiempo_segundos": 9.0,
    }

    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)

    created = MagicMock()
    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", created)

    scheduler = ScraperScheduler()
    await scheduler._scrape_fuente(fuente)

    _, registro = created.call_args[0]
    assert registro.encontradas == 17


async def test_scrape_fuente_writes_none_encontradas_on_whole_run_failure(monkeypatch):
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    # runner.run_paginated_scraper crash path: urls_encontradas=0 + an error key
    stats = {
        "nuevas": 0,
        "duplicadas": 0,
        "errores": 0,
        "urls_encontradas": 0,
        "paginas_procesadas": 0,
        "tiempo_segundos": 0.1,
        "error": "boom",
    }

    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)

    created = MagicMock()
    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", created)

    scheduler = ScraperScheduler()
    await scheduler._scrape_fuente(fuente)

    _, registro = created.call_args[0]
    assert registro.encontradas is None


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


# --- Issue #50: whole-run failures must look like failures ------------------


def _failing_stats(error="boom"):
    # runner.run_paginated_scraper crash shape: errores=0 plus an "error" key.
    return {
        "nuevas": 0,
        "duplicadas": 0,
        "errores": 0,
        "urls_encontradas": 0,
        "paginas_procesadas": 0,
        "tiempo_segundos": 0.1,
        "error": error,
    }


def _wire_scrape(monkeypatch, fuente, stats):
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))
    fake_runner = MagicMock()
    fake_runner.run_paginated_scraper = AsyncMock(return_value=stats)
    monkeypatch.setattr(scheduler_mod, "ScraperRunner", lambda session: fake_runner)
    created = MagicMock()
    monkeypatch.setattr(scheduler_mod.RegistroEjecucionCRUD, "create", created)
    return fake_session, created


async def test_scrape_fuente_whole_run_failure_records_errores_and_error_text(monkeypatch):
    fuente = _fuente()
    _, created = _wire_scrape(monkeypatch, fuente, _failing_stats("network down"))

    await ScraperScheduler()._scrape_fuente(fuente)

    _, registro = created.call_args[0]
    assert registro.errores >= 1
    assert registro.encontradas is None
    assert registro.error_mensaje == "network down"


async def test_scrape_fuente_whole_run_failure_derives_failing_health(monkeypatch):
    from admin.health import derive_health

    fuente = _fuente()
    _, created = _wire_scrape(monkeypatch, fuente, _failing_stats())

    await ScraperScheduler()._scrape_fuente(fuente)

    _, registro = created.call_args[0]
    status, _reason = derive_health(fuente, [registro])
    assert status == "FAILING"


async def test_scrape_fuente_whole_run_failure_does_not_advance_ultima_ejecucion(monkeypatch):
    fuente = _fuente()
    fuente.ultima_ejecucion = None
    _wire_scrape(monkeypatch, fuente, _failing_stats())

    error = await ScraperScheduler()._scrape_fuente(fuente)

    assert fuente.ultima_ejecucion is None
    assert error == "boom"


async def test_scrape_fuente_success_still_advances_ultima_ejecucion_and_returns_none(monkeypatch):
    fuente = _fuente()
    fuente.ultima_ejecucion = None
    stats = {"nuevas": 0, "duplicadas": 0, "errores": 0, "paginas_procesadas": 1, "tiempo_segundos": 1.0}
    _wire_scrape(monkeypatch, fuente, stats)

    error = await ScraperScheduler()._scrape_fuente(fuente)

    assert fuente.ultima_ejecucion is not None
    assert error is None


async def test_scrape_fuente_unexpected_exception_is_returned_as_error(monkeypatch):
    fuente = _fuente()
    fake_session = FakeSession(fuente)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(fake_session))

    def _boom(session):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(scheduler_mod, "ScraperRunner", _boom)

    error = await ScraperScheduler()._scrape_fuente(fuente)

    assert "db unreachable" in error


class _FuenteListSession:
    def __init__(self, fuentes):
        self._fuentes = fuentes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec(self, stmt):
        result = MagicMock()
        result.all.return_value = self._fuentes
        return result


async def test_force_scrape_all_summary_lists_failed_fuentes(monkeypatch):
    fuente_a = Fuente(id=1, nombre="A", url="http://example.com/a", activa=True, intervalo_horas=6)
    fuente_b = Fuente(id=2, nombre="B", url="http://example.com/b", activa=True, intervalo_horas=6)
    monkeypatch.setattr(
        scheduler_mod, "Session", lambda engine: _FuenteListSession([fuente_a, fuente_b])
    )

    async def fake_scrape_fuente(self, fuente, run_id=None):
        return "boom" if fuente.nombre == "B" else None

    monkeypatch.setattr(scheduler_mod.ScraperScheduler, "_scrape_fuente", fake_scrape_fuente)

    summary = await ScraperScheduler().force_scrape_all()

    assert summary.ok is False
    assert summary.failed == ["B: boom"]
    assert summary.fatal_error is None


async def test_check_and_scrape_summary_is_ok_when_every_fuente_succeeds(monkeypatch):
    fuente_a = Fuente(id=1, nombre="A", url="http://example.com/a", activa=True, intervalo_horas=6)
    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FuenteListSession([fuente_a]))

    async def fake_scrape_fuente(self, fuente, run_id=None):
        return None

    monkeypatch.setattr(scheduler_mod.ScraperScheduler, "_scrape_fuente", fake_scrape_fuente)

    summary = await ScraperScheduler().check_and_scrape()

    assert summary.ok is True


async def test_check_and_scrape_top_level_exception_is_fatal_in_summary(monkeypatch):
    def _unreachable(engine):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(scheduler_mod, "Session", _unreachable)

    summary = await ScraperScheduler().check_and_scrape()

    assert summary.ok is False
    assert "db unreachable" in summary.fatal_error


async def test_force_scrape_all_top_level_exception_is_fatal_in_summary(monkeypatch):
    def _unreachable(engine):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(scheduler_mod, "Session", _unreachable)

    summary = await ScraperScheduler().force_scrape_all()

    assert summary.ok is False
    assert "db unreachable" in summary.fatal_error


async def test_run_sold_check_top_level_exception_is_fatal_in_summary(monkeypatch):
    async def _boom(session, **kwargs):
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(MagicMock()))
    monkeypatch.setattr(scheduler_mod, "check_sold_properties", _boom)

    summary = await ScraperScheduler().run_sold_check()

    assert summary.ok is False
    assert "db unreachable" in summary.fatal_error


async def test_run_sold_check_summary_lists_fuentes_that_looked_broken(monkeypatch):
    async def fake_check(session, **kwargs):
        return {
            "vendidas_lista": [],
            "bajadas_precio": [],
            "fuentes_fallidas": {7: "9/10 listings returned no data"},
        }

    monkeypatch.setattr(scheduler_mod, "Session", lambda engine: _FakeSessionCtx(MagicMock()))
    monkeypatch.setattr(scheduler_mod, "check_sold_properties", fake_check)

    summary = await ScraperScheduler().run_sold_check()

    assert summary.ok is False
    assert summary.failed == ["fuente 7: 9/10 listings returned no data"]

"""Tests for app/admin/manual_run.py — Streamlit-free manual per-fuente runner
(slice S5).

Spec: sdd/scraper-admin-console/spec — "Manual Per-Fuente Scrape & Sold-Check
Triggers". A manual scrape writes exactly one ``tipo="scrape"``
``RegistroEjecucion`` row with a ``manual-`` ``run_id`` and the scheduler's
counter fields; a manual sold-check delegates to the scoped
``check_sold_properties`` and writes no extra row itself.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Fuente, RegistroEjecucion  # noqa: E402
from admin import manual_run as manual_run_mod  # noqa: E402
from admin.manual_run import run_manual_scrape, run_manual_sold_check  # noqa: E402


class FakeSession:
    """Minimal stand-in for a SQLModel Session — records added rows so the
    RegistroEjecucionCRUD.create(add/commit/refresh) path can be asserted."""

    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


class StubRunner:
    """Stubs ScraperRunner.run_paginated_scraper with a canned stats dict or an
    exception to raise."""

    def __init__(self, stats=None, raises=None):
        self._stats = stats or {}
        self._raises = raises
        self.calls = []

    async def run_paginated_scraper(self, fuente, *args, **kwargs):
        self.calls.append(fuente)
        if self._raises is not None:
            raise self._raises
        return dict(self._stats)


def _fuente(fuente_id: int = 42) -> Fuente:
    return Fuente(
        id=fuente_id,
        nombre="Fuente Manual",
        url="http://example.test/manual",
        intervalo_horas=24,
        activa=True,
    )


@pytest.mark.asyncio
async def test_run_manual_scrape_writes_single_scrape_registro_with_manual_run_id():
    session = FakeSession()
    fuente = _fuente(42)
    stub = StubRunner(
        stats={
            "fuente_id": 42,
            "nombre": "Fuente Manual",
            "nuevas": 7,
            "duplicadas": 3,
            "errores": 1,
            "paginas_procesadas": 2,
            "tiempo_segundos": 12.5,
        }
    )

    result = await run_manual_scrape(session, fuente, runner=stub)

    registros = [r for r in session.added if isinstance(r, RegistroEjecucion)]
    assert len(registros) == 1
    row = registros[0]
    assert row.fuente_id == 42
    assert row.tipo == "scrape"
    assert row.nuevas == 7
    assert row.duplicadas == 3
    assert row.errores == 1
    assert row.total == 11
    assert row.duracion_segundos == 12.5
    assert row.run_id is not None and row.run_id.startswith("manual-")

    # returned stats are the scrape stats augmented with the run_id
    assert result["run_id"] == row.run_id
    assert result["nuevas"] == 7
    assert stub.calls == [fuente]


@pytest.mark.asyncio
async def test_run_manual_scrape_honours_explicit_run_id_and_now():
    session = FakeSession()
    fuente = _fuente(7)
    pinned = datetime(2026, 9, 4, 10, 30, 0)
    stub = StubRunner(
        stats={"nuevas": 0, "duplicadas": 5, "errores": 0, "tiempo_segundos": 4.0}
    )

    result = await run_manual_scrape(
        session, fuente, runner=stub, run_id="manual-fixed-123", now=pinned
    )

    row = [r for r in session.added if isinstance(r, RegistroEjecucion)][0]
    assert row.run_id == "manual-fixed-123"
    assert row.fecha == pinned
    assert row.nuevas == 0
    assert row.duplicadas == 5
    assert row.total == 5
    assert result["run_id"] == "manual-fixed-123"


@pytest.mark.asyncio
async def test_run_manual_scrape_records_row_on_mid_run_failure():
    session = FakeSession()
    fuente = _fuente(9)
    stub = StubRunner(raises=RuntimeError("boom mid scrape"))

    result = await run_manual_scrape(session, fuente, runner=stub)

    registros = [r for r in session.added if isinstance(r, RegistroEjecucion)]
    assert len(registros) == 1
    assert registros[0].tipo == "scrape"
    assert registros[0].fuente_id == 9
    assert registros[0].errores > 0
    assert result["run_id"].startswith("manual-")
    assert "boom mid scrape" in str(result.get("error", ""))


@pytest.mark.asyncio
async def test_run_manual_sold_check_delegates_scoped_and_writes_no_extra_row(monkeypatch):
    session = FakeSession()
    fuente = _fuente(55)
    seen = {}

    async def fake_check_sold_properties(sess, *args, **kwargs):
        seen["session"] = sess
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {"vendidas": 2, "activas": 8, "sin_datos": 1}

    monkeypatch.setattr(
        manual_run_mod, "check_sold_properties", fake_check_sold_properties
    )

    stats = await run_manual_sold_check(session, fuente)

    assert seen["session"] is session
    assert seen["kwargs"].get("fuente_id") == 55
    # manual_run must NOT write its own RegistroEjecucion — check_sold_properties
    # already writes exactly one scoped sold_check row.
    assert [r for r in session.added if isinstance(r, RegistroEjecucion)] == []
    assert stats == {"vendidas": 2, "activas": 8, "sin_datos": 1}


def test_manual_run_module_has_no_streamlit_import():
    source = (
        Path(__file__).parent.parent / "app" / "admin" / "manual_run.py"
    ).read_text()
    import_lines = [
        ln.strip()
        for ln in source.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    assert not any("streamlit" in ln for ln in import_lines)

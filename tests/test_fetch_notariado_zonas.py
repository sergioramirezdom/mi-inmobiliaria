"""Tests for scripts/fetch_notariado_zonas.py — nested zona x combo
orchestration, append-if-outcome-changed dedup, per-zona/per-combo failure
isolation, exit-code semantics, and RegistroEjecucion accounting.

Uses an in-memory SQLite engine (Fuente + RegistroEjecucion +
EstadisticaZonaNotarial tables only — avoids Propiedad's ARRAY column, same
pattern as tests/test_fetch_notariado_stats.py) and monkeypatches the
script's module-level `engine`, `fetch_price_avg`, `load_zona_geometry`, and
`ZONA_SLUGS` references. No live HTTP, no real DB.
"""
import json
import logging
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import EstadisticaZonaNotarial, Fuente, RegistroEjecucion  # noqa: E402
from scraper.notariado_client import ZONA_COMBOS, NotariadoPriceAvgError  # noqa: E402
from scraper.notariado_zonas import ZonaGeometryError  # noqa: E402

import scripts.fetch_notariado_zonas as fnz  # noqa: E402

GEOMETRY_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "notariado_zona_geometry.json").read_text()
)

WHERES = [where for _, _, where in ZONA_COMBOS]


def _memory_engine():
    engine = create_engine("sqlite:///:memory:")
    Fuente.__table__.create(bind=engine, checkfirst=True)
    RegistroEjecucion.__table__.create(bind=engine, checkfirst=True)
    EstadisticaZonaNotarial.__table__.create(bind=engine, checkfirst=True)
    return engine


@pytest.fixture()
def test_engine(monkeypatch):
    engine = _memory_engine()
    monkeypatch.setattr(fnz, "engine", engine)
    return engine


@pytest.fixture()
def stub_geometry(monkeypatch):
    """Return the fixture polygon for every registered slug."""
    monkeypatch.setattr(fnz, "load_zona_geometry", lambda slug: dict(GEOMETRY_FIXTURE))


def _price_stub(mapping, raises_for=()):
    def _stub(geometry, where, **kwargs):
        if where in raises_for:
            raise NotariadoPriceAvgError("price-avg failed with status 500")
        return mapping[where]

    return _stub


def _run_logs(engine):
    with Session(engine) as session:
        return session.exec(
            select(RegistroEjecucion).where(
                RegistroEjecucion.tipo == "notariado_zonas"
            )
        ).all()


def _rows(engine):
    with Session(engine) as session:
        return session.exec(select(EstadisticaZonaNotarial)).all()


def test_happy_all_combos_return_ints(test_engine, stub_geometry, monkeypatch):
    mapping = {where: 1000 + idx * 10 for idx, where in enumerate(WHERES)}
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(mapping))

    exit_code = fnz.main([])

    assert exit_code == 0
    rows = _rows(test_engine)
    assert len(rows) == 4
    for row in rows:
        assert row.zona == "crevillet"
        assert row.sin_datos is False
        assert row.price_avg == float(mapping[row.where_clause])
        assert row.where_clause in WHERES
    assert {row.where_clause for row in rows} == set(WHERES)

    logs = _run_logs(test_engine)
    assert len(logs) == 1
    assert logs[0].total == len(WHERES)
    assert logs[0].nuevas == 4
    assert logs[0].errores == 0
    assert logs[0].sin_datos == 0


def test_pav002_subset_writes_sin_datos_rows(test_engine, stub_geometry, monkeypatch):
    mapping = {WHERES[0]: None, WHERES[1]: None, WHERES[2]: 1500, WHERES[3]: 1600}
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(mapping))

    exit_code = fnz.main([])

    assert exit_code == 0
    rows = _rows(test_engine)
    assert len(rows) == 4
    no_data = [r for r in rows if r.sin_datos]
    assert len(no_data) == 2
    for row in no_data:
        assert row.price_avg is None
    with_data = [r for r in rows if not r.sin_datos]
    assert {r.price_avg for r in with_data} == {1500.0, 1600.0}

    logs = _run_logs(test_engine)
    assert logs[0].nuevas == 4
    assert logs[0].sin_datos == 2
    assert logs[0].errores == 0


def test_second_identical_run_inserts_nothing_but_still_logs(
    test_engine, stub_geometry, monkeypatch
):
    mapping = {where: 2000 + idx for idx, where in enumerate(WHERES)}
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(mapping))

    assert fnz.main([]) == 0
    assert fnz.main([]) == 0

    assert len(_rows(test_engine)) == 4
    logs = _run_logs(test_engine)
    assert len(logs) == 2
    assert logs[1].nuevas == 0
    assert logs[1].errores == 0


def test_null_value_transitions_both_directions(test_engine, stub_geometry, monkeypatch):
    base = {where: 3000 + idx for idx, where in enumerate(WHERES)}
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(base))
    assert fnz.main([]) == 0
    assert len(_rows(test_engine)) == 4

    # value -> None inserts a sin_datos row for combo 0 only.
    to_none = dict(base)
    to_none[WHERES[0]] = None
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(to_none))
    assert fnz.main([]) == 0
    rows = _rows(test_engine)
    assert len(rows) == 5
    latest0 = fnz.EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
        Session(test_engine), "crevillet", ZONA_COMBOS[0][0], ZONA_COMBOS[0][1]
    )
    assert latest0.sin_datos is True and latest0.price_avg is None

    # None -> value inserts a real row for combo 0 only.
    back_to_value = dict(base)
    back_to_value[WHERES[0]] = 9999
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(back_to_value))
    assert fnz.main([]) == 0
    rows = _rows(test_engine)
    assert len(rows) == 6
    latest0 = fnz.EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
        Session(test_engine), "crevillet", ZONA_COMBOS[0][0], ZONA_COMBOS[0][1]
    )
    assert latest0.sin_datos is False and latest0.price_avg == 9999.0


def test_one_combo_error_isolates_and_exits_nonzero(
    test_engine, stub_geometry, monkeypatch
):
    mapping = {where: 4000 + idx for idx, where in enumerate(WHERES)}
    monkeypatch.setattr(
        fnz, "fetch_price_avg", _price_stub(mapping, raises_for={WHERES[1]})
    )

    exit_code = fnz.main([])

    assert exit_code != 0
    rows = _rows(test_engine)
    assert len(rows) == 3
    assert WHERES[1] not in {r.where_clause for r in rows}
    logs = _run_logs(test_engine)
    assert len(logs) == 1
    assert logs[0].errores >= 1


def test_one_zona_geometry_missing_isolates_and_exits_nonzero(
    test_engine, monkeypatch
):
    monkeypatch.setattr(fnz, "ZONA_SLUGS", ["crevillet", "ghost"])

    def _load(slug):
        if slug == "ghost":
            raise ZonaGeometryError("zona geometry file not found: ghost.json")
        return dict(GEOMETRY_FIXTURE)

    monkeypatch.setattr(fnz, "load_zona_geometry", _load)
    mapping = {where: 5000 + idx for idx, where in enumerate(WHERES)}
    monkeypatch.setattr(fnz, "fetch_price_avg", _price_stub(mapping))

    exit_code = fnz.main([])

    assert exit_code != 0
    rows = _rows(test_engine)
    # crevillet's 4 combos still processed; ghost's combos skipped.
    assert len(rows) == 4
    assert {r.zona for r in rows} == {"crevillet"}
    logs = _run_logs(test_engine)
    assert len(logs) == 1
    assert logs[0].errores == 1
    assert logs[0].total == len(["crevillet", "ghost"]) * len(WHERES)


def test_all_pav002_exits_zero_with_warning(
    test_engine, stub_geometry, monkeypatch, caplog
):
    monkeypatch.setattr(
        fnz, "fetch_price_avg", _price_stub({where: None for where in WHERES})
    )

    with caplog.at_level(logging.WARNING, logger=fnz.logger.name):
        exit_code = fnz.main([])

    assert exit_code == 0
    logs = _run_logs(test_engine)
    assert logs[0].sin_datos == 4
    assert logs[0].errores == 0
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_sentinel_fuente_created_once_and_reused(test_engine, stub_geometry, monkeypatch):
    monkeypatch.setattr(
        fnz, "fetch_price_avg", _price_stub({where: 6000 for where in WHERES})
    )

    fnz.main([])
    fnz.main([])

    with Session(test_engine) as session:
        fuentes = session.exec(
            select(Fuente).where(Fuente.url == "internal://notariado-zonas")
        ).all()
    assert len(fuentes) == 1
    assert fuentes[0].tipo_scraper == "notariado_zonas"
    assert fuentes[0].activa is False

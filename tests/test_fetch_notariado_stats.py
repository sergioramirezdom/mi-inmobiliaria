"""Tests for scripts/fetch_notariado_stats.py — dedup, backfill, run-log,
exit code, and API quota logging.

Uses an in-memory SQLite engine (Fuente + RegistroEjecucion +
EstadisticaNotarial tables only — avoids Propiedad's ARRAY column, same
pattern as tests/test_registro_ejecucion.py) and monkeypatches the script's
module-level `engine`, `login`, `fetch_stats`, and `fetch_quota` references.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import EstadisticaNotarial, Fuente, RegistroEjecucion  # noqa: E402
from scraper.notariado_client import COMBOS, NotariadoAuthError  # noqa: E402

import scripts.fetch_notariado_stats as fns  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "notariado_stats_response.json"


def _load_fixture() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def _memory_engine():
    engine = create_engine("sqlite:///:memory:")
    Fuente.__table__.create(bind=engine, checkfirst=True)
    RegistroEjecucion.__table__.create(bind=engine, checkfirst=True)
    EstadisticaNotarial.__table__.create(bind=engine, checkfirst=True)
    return engine


@pytest.fixture()
def test_engine(monkeypatch):
    engine = _memory_engine()
    monkeypatch.setattr(fns, "engine", engine)
    return engine


@pytest.fixture()
def stub_auth(monkeypatch):
    monkeypatch.setattr(fns, "login", lambda *a, **k: "fake-token")
    monkeypatch.setattr(
        fns,
        "fetch_quota",
        lambda *a, **k: {"numberMonthlyQueries": 48, "numberExtraQueries": 0},
    )


def test_skips_insert_when_last_data_update_unchanged(test_engine, stub_auth, monkeypatch):
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)
    stats = fixture["data"]["statistics"]

    with Session(test_engine) as session:
        for property_type, construction_type in COMBOS:
            slug_p = fns._SLUG_BY_PROPERTY_CODE[property_type]
            slug_c = fns._SLUG_BY_CONSTRUCTION_CODE[construction_type]
            session.add(
                EstadisticaNotarial(
                    location_code=fns.LOCATION_CODE,
                    property_type=slug_p,
                    construction_type=slug_c,
                    last_data_update=fns._parse_datetime(stats["lastDataUpdate"]),
                    report_date=fns._parse_datetime(stats["reportDate"]),
                    raw_json=json.dumps(fixture),
                )
            )
        session.commit()

    exit_code = fns.main([])

    with Session(test_engine) as session:
        rows = session.exec(select(EstadisticaNotarial)).all()
        # 4 pre-seeded rows (one per combo) — no new inserts since
        # last_data_update is unchanged for every combo.
        assert len(rows) == len(COMBOS)

    assert exit_code == 0


def test_inserts_when_last_data_update_changed(test_engine, stub_auth, monkeypatch):
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)

    with Session(test_engine) as session:
        for property_type, construction_type in COMBOS:
            session.add(
                EstadisticaNotarial(
                    location_code=fns.LOCATION_CODE,
                    property_type=fns._SLUG_BY_PROPERTY_CODE[property_type],
                    construction_type=fns._SLUG_BY_CONSTRUCTION_CODE[construction_type],
                    last_data_update=datetime(2020, 1, 1),
                    report_date=datetime(2020, 1, 15),
                    raw_json="{}",
                )
            )
        session.commit()

    exit_code = fns.main([])

    with Session(test_engine) as session:
        rows = session.exec(select(EstadisticaNotarial)).all()
        # 4 old seeded rows + 4 freshly inserted rows (one per combo).
        assert len(rows) == len(COMBOS) * 2

    assert exit_code == 0


def test_backfill_flag_inserts_12month_price_per_sqm_series(
    test_engine, stub_auth, monkeypatch
):
    """--backfill maps `statistics.pricePerSqm.12months.metric[]` (the one
    bucket with real monthly legends and real values) into one historical
    row per non-zero month, on top of the current row. The fixture has 3
    non-zero months: Dic 2025, Ene 2026, Feb 2026."""
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)

    exit_code = fns.main(["--backfill"])

    with Session(test_engine) as session:
        rows = session.exec(select(EstadisticaNotarial)).all()
        # Per combo: 1 current row + 3 monthly price-per-sqm rows = 4.
        assert len(rows) == len(COMBOS) * 4

        historical = [r for r in rows if r.current_number_of_sales is None]
        assert len(historical) == len(COMBOS) * 3
        months = {r.last_data_update.strftime("%Y-%m") for r in historical}
        assert months == {"2025-12", "2026-01", "2026-02"}
        prices = sorted(r.current_price_per_sqm for r in historical[:3])
        assert prices == sorted([2101.41, 2421.36, 2205.84])

    assert exit_code == 0


def test_backfill_is_idempotent_for_unchanged_monthly_values(
    test_engine, stub_auth, monkeypatch
):
    """Running --backfill twice with the same fixture must not duplicate
    the monthly rows — only re-insert a month if its value changed."""
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)

    fns.main(["--backfill"])
    fns.main(["--backfill"])

    with Session(test_engine) as session:
        rows = session.exec(select(EstadisticaNotarial)).all()
        historical = [r for r in rows if r.current_number_of_sales is None]
        assert len(historical) == len(COMBOS) * 3


def test_run_logs_registro_ejecucion_on_success_and_failure(test_engine, stub_auth, monkeypatch):
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)

    fns.main([])

    with Session(test_engine) as session:
        registros = session.exec(
            select(RegistroEjecucion).where(RegistroEjecucion.tipo == "notariado_stats")
        ).all()
        assert len(registros) == 1
        assert registros[0].total == len(COMBOS)

    # Now force a failure path.
    def _raise_login(*a, **k):
        raise NotariadoAuthError("Notariado login failed with status 401")

    monkeypatch.setattr(fns, "login", _raise_login)

    fns.main([])

    with Session(test_engine) as session:
        registros = session.exec(
            select(RegistroEjecucion).where(RegistroEjecucion.tipo == "notariado_stats")
        ).all()
        assert len(registros) == 2
        assert registros[1].errores >= 1


def test_main_exits_nonzero_on_failure(test_engine, monkeypatch):
    def _raise_login(*a, **k):
        raise NotariadoAuthError("Notariado login failed with status 401")

    monkeypatch.setattr(fns, "login", _raise_login)

    exit_code = fns.main([])

    assert exit_code != 0


def test_logs_api_quota_after_run(test_engine, stub_auth, monkeypatch, caplog):
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)
    monkeypatch.setattr(
        fns,
        "fetch_quota",
        lambda *a, **k: {"numberMonthlyQueries": 48, "numberExtraQueries": 0},
    )

    with caplog.at_level(logging.INFO, logger=fns.logger.name):
        fns.main([])

    combined = "\n".join(record.message for record in caplog.records)
    assert "48" in combined
    assert "0" in combined

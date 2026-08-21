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


def _rows_for_combo(session, property_type: str, construction_type: str):
    return session.exec(
        select(EstadisticaNotarial).where(
            EstadisticaNotarial.property_type == property_type,
            EstadisticaNotarial.construction_type == construction_type,
        )
    ).all()


def test_backfill_flag_inserts_one_row_per_month_with_sales_data(
    test_engine, stub_auth, monkeypatch
):
    """--backfill is driven by numberOfSales.12months (real data every
    month, including legitimate zeros) — one row per month. pricePerSqm/
    averagePrice are attached only when that month has a real (non-zero,
    non-estimation-only) value; the fixture has real price/avg data for
    just 3 of the 12 months (Dic 2025, Ene 2026, Feb 2026)."""
    fixture = _load_fixture()
    monkeypatch.setattr(fns, "fetch_stats", lambda *a, **k: fixture)

    exit_code = fns.main(["--backfill"])

    with Session(test_engine) as session:
        rows = _rows_for_combo(session, "piso", "obra_nueva")
        # 1 current row + 12 monthly rows (numberOfSales has 12 months).
        assert len(rows) == 13

        by_month = {}
        for r in rows:
            by_month.setdefault(r.last_data_update.strftime("%Y-%m"), []).append(r)
        assert set(by_month) == {
            "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11",
            "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        }

        # Dic 2025 has real price + avg-price data.
        dec = next(r for r in by_month["2025-12"] if r.current_number_of_sales == 35)
        assert dec.current_price_per_sqm == 2101.41
        assert dec.current_average_price == 162190.96

        # Jun 2025 only has real sales data — price/avg-price are null,
        # not filled with the estimation.
        jun = next(r for r in by_month["2025-06"] if r.current_number_of_sales == 4)
        assert jun.current_price_per_sqm is None
        assert jun.current_average_price is None

        # Ago 2025 is a legitimate zero-sales month, still gets a row.
        ago = next(r for r in by_month["2025-08"] if r.current_number_of_sales == 0)
        assert ago.current_price_per_sqm is None

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
        rows = _rows_for_combo(session, "piso", "obra_nueva")
        assert len(rows) == 13


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

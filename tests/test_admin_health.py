"""Tests for app/admin/health.py — pure, Streamlit-free health derivation for
the run-history / health dashboard (slice S3).

Spec: sdd/scraper-admin-console/spec — "Derived Per-Fuente Health Status"
(states OK / STALE / FAILING / UNKNOWN; precedence FAILING > STALE > OK).
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Fuente, RegistroEjecucion  # noqa: E402
from admin.health import (  # noqa: E402
    STALENESS_FACTOR,
    derive_health,
    last_successful_scrape,
    summarize_fuente_runs,
)

NOW = datetime(2026, 9, 4, 12, 0, 0)


def _fuente(intervalo_horas: int = 24, activa: bool = True) -> Fuente:
    return Fuente(
        id=1,
        nombre="Fuente Test",
        url="http://example.test",
        intervalo_horas=intervalo_horas,
        activa=activa,
    )


def _run(
    tipo: str = "scrape",
    errores: int = 0,
    nuevas: int = 0,
    duplicadas: int = 0,
    age_hours: float = 1.0,
) -> RegistroEjecucion:
    return RegistroEjecucion(
        fuente_id=1,
        tipo=tipo,
        errores=errores,
        nuevas=nuevas,
        duplicadas=duplicadas,
        fecha=NOW - timedelta(hours=age_hours),
    )


def test_staleness_factor_is_a_named_constant():
    assert isinstance(STALENESS_FACTOR, (int, float))
    assert STALENESS_FACTOR >= 1


def test_unknown_when_no_runs():
    status, reason = derive_health(_fuente(), [], now=NOW)
    assert status == "UNKNOWN"
    assert reason


def test_unknown_when_only_sold_check_rows():
    rows = [_run(tipo="sold_check", errores=0, age_hours=2)]
    status, _ = derive_health(_fuente(), rows, now=NOW)
    assert status == "UNKNOWN"


def test_failing_when_latest_scrape_errored():
    rows = [_run(errores=3, nuevas=0, age_hours=1)]
    status, reason = derive_health(_fuente(intervalo_horas=24), rows, now=NOW)
    assert status == "FAILING"
    assert "3" in reason


def test_failing_regardless_of_recency_even_with_older_clean_scrape():
    rows = [
        _run(errores=2, age_hours=1),
        _run(errores=0, age_hours=100),
    ]
    status, _ = derive_health(_fuente(intervalo_horas=24), rows, now=NOW)
    assert status == "FAILING"


def test_stale_when_last_clean_scrape_older_than_window():
    # window = STALENESS_FACTOR(2) * 24h = 48h; run is 100h old
    rows = [_run(errores=0, age_hours=100)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "STALE"


def test_ok_when_recent_clean_scrape_within_window():
    rows = [_run(errores=0, nuevas=4, age_hours=10)]
    status, _ = derive_health(_fuente(intervalo_horas=24), rows, now=NOW)
    assert status == "OK"


def test_precedence_failing_beats_stale():
    # errored AND old -> FAILING wins over STALE
    rows = [_run(errores=1, age_hours=200)]
    status, _ = derive_health(_fuente(intervalo_horas=24), rows, now=NOW)
    assert status == "FAILING"


def test_last_successful_scrape_picks_most_recent_clean_scrape():
    errored = _run(errores=5, age_hours=1)
    clean_recent = _run(errores=0, age_hours=50)
    clean_old = _run(errores=0, age_hours=500)
    rows = [errored, clean_recent, clean_old]

    picked = last_successful_scrape(rows)

    assert picked is not None
    assert picked.fecha == NOW - timedelta(hours=50)


def test_last_successful_scrape_none_when_no_clean_scrape():
    rows = [_run(errores=1, age_hours=1), _run(tipo="sold_check", errores=0, age_hours=2)]
    assert last_successful_scrape(rows) is None


def test_summarize_reports_latest_counters_and_last_success():
    errored_latest = _run(errores=4, nuevas=0, duplicadas=1, age_hours=1)
    clean_earlier = _run(errores=0, nuevas=7, duplicadas=2, age_hours=30)
    rows = [errored_latest, clean_earlier]

    summary = summarize_fuente_runs(rows)

    assert summary.last_run_at == NOW - timedelta(hours=1)
    assert summary.last_tipo == "scrape"
    assert summary.last_nuevas == 0
    assert summary.last_duplicadas == 1
    assert summary.last_errores == 4
    assert summary.last_successful_scrape_at == NOW - timedelta(hours=30)


def test_summarize_empty_rows_is_all_none():
    summary = summarize_fuente_runs([])
    assert summary.last_run_at is None
    assert summary.last_successful_scrape_at is None
    assert summary.last_nuevas is None
    assert summary.last_errores is None

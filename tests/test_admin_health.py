"""Tests for app/admin/health.py — pure, Streamlit-free health derivation for
the run-history / health dashboard (slice S3).

Spec: sdd/scraper-admin-health-signals/spec — "Derived Per-Fuente Health Status"
(states OK / STALE / EMPTY / FAILING / UNKNOWN;
precedence UNKNOWN > FAILING > EMPTY > STALE > OK).
"""
import ast
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Fuente, RegistroEjecucion  # noqa: E402
from admin.health import (  # noqa: E402
    MIN_STALENESS_HOURS,
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
    encontradas: Optional[int] = 1,
    total: Optional[int] = None,
) -> RegistroEjecucion:
    kwargs = dict(
        fuente_id=1,
        tipo=tipo,
        errores=errores,
        nuevas=nuevas,
        duplicadas=duplicadas,
        fecha=NOW - timedelta(hours=age_hours),
        encontradas=encontradas,
    )
    if total is not None:
        kwargs["total"] = total
    return RegistroEjecucion(**kwargs)


def test_staleness_factor_is_a_named_constant():
    assert isinstance(STALENESS_FACTOR, (int, float))
    assert STALENESS_FACTOR >= 1


def test_min_staleness_hours_is_a_named_constant():
    assert isinstance(MIN_STALENESS_HOURS, (int, float))
    assert MIN_STALENESS_HOURS >= 1


@pytest.mark.parametrize(
    "age_hours, expected",
    [
        (13.0, "OK"),     # today's false-STALE case: window math gives 4h, floor lifts to 20h
        (19.9, "OK"),      # just inside the 20h floor
        (20.1, "STALE"),   # just past the 20h floor
        (25.0, "STALE"),   # well past the floor
    ],
)
def test_staleness_floor_governs_short_interval_fuente(age_hours, expected):
    # intervalo_horas=2 -> STALENESS_FACTOR*2 = 4h, but MIN_STALENESS_HOURS lifts the window to 20h
    rows = [_run(errores=0, nuevas=1, age_hours=age_hours)]
    status, _ = derive_health(_fuente(intervalo_horas=2, activa=True), rows, now=NOW)
    assert status == expected


@pytest.mark.parametrize(
    "age_hours, expected",
    [
        (30.0, "OK"),      # inside the 48h factor window
        (47.9, "OK"),
        (60.0, "STALE"),   # past the 48h window; the 20h floor never weakens it
    ],
)
def test_staleness_floor_does_not_weaken_long_interval_fuente(age_hours, expected):
    # intervalo_horas=24 -> STALENESS_FACTOR*24 = 48h > 20h floor, so the window stays 48h
    rows = [_run(errores=0, nuevas=1, age_hours=age_hours)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == expected


def test_stale_reason_names_both_the_floor_and_the_factor():
    rows = [_run(errores=0, age_hours=25)]
    status, reason = derive_health(_fuente(intervalo_horas=2, activa=True), rows, now=NOW)
    assert status == "STALE"
    assert "20" in reason              # the MIN_STALENESS_HOURS floor
    assert "floor" in reason
    assert "intervalo_horas" in reason


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


# --- S3: EMPTY state -------------------------------------------------------


def test_empty_when_latest_scrape_found_zero_listings():
    rows = [_run(errores=0, encontradas=0, age_hours=1)]
    status, reason = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "EMPTY"
    assert reason


def test_empty_via_legacy_fallback_total_zero():
    rows = [_run(errores=0, encontradas=None, total=0, age_hours=1)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "EMPTY"


def test_legacy_row_with_nonzero_total_is_ok_not_empty():
    rows = [_run(errores=0, encontradas=None, total=5, nuevas=5, age_hours=1)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "OK"


def test_not_empty_when_legacy_row_parsed_only_rentals_or_garages():
    # encontradas > 0 (listing parser worked) but total == 0 (all filtered out) -> NOT EMPTY
    rows = [_run(errores=0, encontradas=5, total=0, age_hours=1)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status != "EMPTY"
    assert status == "OK"


def test_failing_outranks_empty():
    rows = [_run(errores=2, encontradas=0, age_hours=1)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "FAILING"


def test_empty_outranks_stale():
    # scrape older than any staleness window, but it ran and parsed nothing
    rows = [_run(errores=0, encontradas=0, age_hours=100)]
    status, _ = derive_health(_fuente(intervalo_horas=2, activa=True), rows, now=NOW)
    assert status == "EMPTY"


def test_inactive_fuente_is_never_empty():
    rows = [_run(errores=0, encontradas=0, age_hours=1)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=False), rows, now=NOW)
    assert status != "EMPTY"
    assert status == "OK"


def test_inactive_fuente_is_not_stale():
    rows = [_run(errores=0, encontradas=1, age_hours=500)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=False), rows, now=NOW)
    assert status == "OK"


def test_normal_non_empty_scrape_is_ok():
    rows = [_run(errores=0, encontradas=40, nuevas=12, age_hours=5)]
    status, _ = derive_health(_fuente(intervalo_horas=24, activa=True), rows, now=NOW)
    assert status == "OK"


def test_empty_reason_differs_between_real_count_and_legacy_fallback():
    real_rows = [_run(errores=0, encontradas=0, age_hours=1)]
    legacy_rows = [_run(errores=0, encontradas=None, total=0, age_hours=1)]
    _, real_reason = derive_health(_fuente(activa=True), real_rows, now=NOW)
    _, legacy_reason = derive_health(_fuente(activa=True), legacy_rows, now=NOW)
    assert real_reason != legacy_reason
    assert "legacy" in legacy_reason
    assert "legacy" not in real_reason


def _load_health_badge_map():
    """Extract HEALTH_BADGE from app/pages/2_ejecuciones.py without running Streamlit."""
    source = (
        Path(__file__).parent.parent / "app" / "pages" / "2_ejecuciones.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "HEALTH_BADGE" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("HEALTH_BADGE not found in 2_ejecuciones.py")


def test_health_badge_covers_every_derivable_status():
    badge = _load_health_badge_map()
    assert {"OK", "STALE", "EMPTY", "FAILING", "UNKNOWN"} <= set(badge)
    assert "EMPTY" in badge["EMPTY"]

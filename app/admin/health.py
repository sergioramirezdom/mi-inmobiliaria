"""Pure, Streamlit-free derivation of per-`Fuente` scraper health.

`RegistroEjecucion` has no stored status column — only counters and a
timestamp — so the run-history / health dashboard (`app/pages/2_ejecuciones.py`)
derives a health verdict at read time from a fuente's run rows.

States (spec: sdd/scraper-admin-console/spec — "Derived Per-Fuente Health Status"):

* ``UNKNOWN``  — no scrape runs recorded for the fuente.
* ``FAILING``  — the most recent ``scrape`` row errored (``errores > 0``),
  regardless of recency.
* ``EMPTY``    — the latest ``scrape`` row ran cleanly (``errores == 0``), the
  fuente is ``activa``, and it parsed zero listing URLs. The real count is
  ``RegistroEjecucion.encontradas`` when set; legacy rows (``encontradas is
  None``) fall back to ``total == 0``. Judged on the latest scrape row
  regardless of its age — a scrape that ran and parsed nothing is a fault
  whether it ran an hour ago or a week ago.
* ``STALE``    — the fuente is ``activa`` and its last successful scrape is
  older than ``max(MIN_STALENESS_HOURS, STALENESS_FACTOR * intervalo_horas)``
  hours, while the latest scrape itself did not error. The
  ``MIN_STALENESS_HOURS`` floor absorbs the nightly CI blackout so
  short-``intervalo_horas`` fuentes stop flipping ``STALE`` every morning.
* ``OK``       — has runs, the latest scrape is clean, non-empty and recent enough.

Precedence when several conditions apply:
``UNKNOWN > FAILING > EMPTY > STALE > OK``. ``EMPTY`` outranks ``STALE``
because a scrape that ran and parsed nothing is sharper than "hasn't run
recently". ``UNKNOWN`` only when there are no scrape rows.

This module has no UI-framework dependency and never touches the database;
callers pass already-fetched rows (via
``RegistroEjecucionCRUD.get_by_fuente`` / ``get_recent``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

# A fuente is considered STALE once its last successful scrape is older than
# STALENESS_FACTOR times its configured `intervalo_horas`. The design pinned no
# explicit value, so 2x the interval is used: one missed cycle is tolerated,
# two consecutive missed cycles flag the fuente.
STALENESS_FACTOR = 2

# Absolute lower bound on the staleness window, regardless of `intervalo_horas`.
# `.github/workflows/scheduler.yml` only fires `0 6-18 * * *`, so there is a ~12h
# nightly blackout plus a few dropped GitHub Actions triggers at either end
# (~18h realistic healthy worst case). 20h = that worst case + a 2h margin, and
# still < 24h so a genuinely dead fuente is flagged within the same calendar day.
# Only binds when STALENESS_FACTOR * intervalo_horas < 20 (i.e. intervalo_horas <= 9).
MIN_STALENESS_HOURS = 20

SCRAPE = "scrape"

HealthStatus = str  # "OK" | "STALE" | "EMPTY" | "FAILING" | "UNKNOWN"


@dataclass(frozen=True)
class RunSummary:
    """Condensed view of one fuente's run rows for the dashboard."""

    last_run_at: Optional[datetime] = None
    last_tipo: Optional[str] = None
    last_nuevas: Optional[int] = None
    last_duplicadas: Optional[int] = None
    last_errores: Optional[int] = None
    last_successful_scrape_at: Optional[datetime] = None


def _sorted_desc(registros: Iterable) -> List:
    """Rows newest-first by `fecha` (defensive: callers may pass any order)."""
    return sorted(registros, key=lambda r: r.fecha, reverse=True)


def _scrape_rows_desc(registros: Iterable) -> List:
    return [r for r in _sorted_desc(registros) if r.tipo == SCRAPE]


def latest_scrape(registros: Iterable):
    """Most recent ``tipo == "scrape"`` row, or ``None``."""
    rows = _scrape_rows_desc(registros)
    return rows[0] if rows else None


def last_successful_scrape(registros: Iterable):
    """Most recent ``tipo == "scrape"`` row with ``errores == 0``, or ``None``."""
    for row in _scrape_rows_desc(registros):
        if (row.errores or 0) == 0:
            return row
    return None


def summarize_fuente_runs(registros: Iterable) -> RunSummary:
    """Reduce a fuente's run rows to the values the dashboard renders."""
    rows = _sorted_desc(registros)
    if not rows:
        return RunSummary()
    last = rows[0]
    success = last_successful_scrape(rows)
    return RunSummary(
        last_run_at=last.fecha,
        last_tipo=last.tipo,
        last_nuevas=last.nuevas,
        last_duplicadas=last.duplicadas,
        last_errores=last.errores,
        last_successful_scrape_at=success.fecha if success is not None else None,
    )


def _is_empty_scrape(row) -> bool:
    """True when a CLEAN scrape row parsed zero listing URLs.

    Prefers the persisted raw listing-URL count (``encontradas``); legacy rows
    written before that column fall back to ``total == 0``. ``getattr`` (not
    attribute access) so pre-column row objects and test doubles stay usable.
    """
    encontradas = getattr(row, "encontradas", None)
    if encontradas is not None:
        return int(encontradas) == 0
    return int(getattr(row, "total", 0) or 0) == 0


def _staleness_window(fuente) -> timedelta:
    hours = max(
        MIN_STALENESS_HOURS,
        STALENESS_FACTOR * max(1, int(fuente.intervalo_horas or 0)),
    )
    return timedelta(hours=hours)


def derive_health(
    fuente,
    registros: Iterable,
    now: Optional[datetime] = None,
) -> Tuple[HealthStatus, str]:
    """Return ``(status, reason)`` for one fuente given its run rows.

    ``now`` is injectable so staleness is testable; it defaults to
    ``datetime.utcnow()`` to match the naive UTC timestamps stored on
    ``RegistroEjecucion.fecha``.
    """
    now = now or datetime.utcnow()

    latest = latest_scrape(registros)
    if latest is None:
        return ("UNKNOWN", "no scrape runs recorded for this fuente")

    if (latest.errores or 0) > 0:
        return ("FAILING", f"latest scrape recorded {latest.errores} error(s)")

    # `latest` is clean here (FAILING already returned otherwise). EMPTY outranks
    # STALE and is judged on this row regardless of its age.
    if getattr(fuente, "activa", True) and _is_empty_scrape(latest):
        if getattr(latest, "encontradas", None) is not None:
            return ("EMPTY", "latest scrape found 0 listing URLs on the source pages")
        return (
            "EMPTY",
            "latest scrape recorded no results (legacy row, no encontradas)",
        )

    success = last_successful_scrape(registros)
    # `latest` is itself a clean scrape here, so `success` is never None.
    window = _staleness_window(fuente)
    age = now - success.fecha
    if getattr(fuente, "activa", True) and age > window:
        return (
            "STALE",
            f"last successful scrape {age} old exceeds the {window} staleness "
            f"window (max({MIN_STALENESS_HOURS}h floor, "
            f"{STALENESS_FACTOR}x intervalo_horas))",
        )

    return ("OK", "latest scrape is clean and within the staleness window")

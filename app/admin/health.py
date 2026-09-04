"""Pure, Streamlit-free derivation of per-`Fuente` scraper health.

`RegistroEjecucion` has no stored status column — only counters and a
timestamp — so the run-history / health dashboard (`app/pages/2_ejecuciones.py`)
derives a health verdict at read time from a fuente's run rows.

States (spec: sdd/scraper-admin-console/spec — "Derived Per-Fuente Health Status"):

* ``UNKNOWN``  — no scrape runs recorded for the fuente.
* ``FAILING``  — the most recent ``scrape`` row errored (``errores > 0``),
  regardless of recency.
* ``STALE``    — the fuente is ``activa`` and its last successful scrape is
  older than ``STALENESS_FACTOR * intervalo_horas``, while the latest scrape
  itself did not error.
* ``OK``       — has runs, the latest scrape is clean and recent enough.

Precedence when several conditions apply: ``FAILING > STALE > OK``.
``UNKNOWN`` only when there are no scrape rows.

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

SCRAPE = "scrape"

HealthStatus = str  # "OK" | "STALE" | "FAILING" | "UNKNOWN"


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


def _staleness_window(fuente) -> timedelta:
    return timedelta(hours=STALENESS_FACTOR * max(1, int(fuente.intervalo_horas or 0)))


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

    success = last_successful_scrape(registros)
    # `latest` is itself a clean scrape here, so `success` is never None.
    window = _staleness_window(fuente)
    age = now - success.fecha
    if getattr(fuente, "activa", True) and age > window:
        return (
            "STALE",
            f"last successful scrape {age} old exceeds "
            f"{STALENESS_FACTOR}x intervalo_horas ({window})",
        )

    return ("OK", "latest scrape is clean and within the staleness window")

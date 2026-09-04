"""Streamlit-free helpers for operator-triggered per-fuente runs (slice S5).

The Streamlit page (``app/pages/1_fuentes.py``) is only a thin shell: it calls
these coroutines with ``asyncio.run`` and renders the returned stats. All the
run-log bookkeeping lives here so it can be unit-tested with a fake session and
a stubbed scraper runner.

Design (sdd/scraper-admin-console/design, decisions D3 / D2):
  * ``run_manual_scrape`` calls the existing paginated scraper for one fuente
    and then writes ONE ``RegistroEjecucion`` row of ``tipo="scrape"`` itself,
    because ``ScraperRunner.run_paginated_scraper`` never writes one (only the
    scheduler does, after the call). Manual rows carry ``run_id`` of the form
    ``"manual-<uuid4>"`` so the run-history page can label them distinctly.
  * ``run_manual_sold_check`` just delegates to the fuente-scoped
    ``check_sold_properties`` (S4), which already writes exactly one scoped
    ``tipo="sold_check"`` row. No extra row is written here, and the row keeps
    that function's own generated ``run_id`` (not a ``manual-`` prefix).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from db.database import RegistroEjecucionCRUD
from db.models import Fuente, RegistroEjecucion
from scraper.runner import ScraperRunner
from scraper.sold_checker import check_sold_properties

MANUAL_RUN_ID_PREFIX = "manual-"


def _new_manual_run_id() -> str:
    return f"{MANUAL_RUN_ID_PREFIX}{uuid4()}"


async def run_manual_scrape(
    session,
    fuente: Fuente,
    *,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    runner: Optional[ScraperRunner] = None,
    results_per_page: int = 48,
) -> dict:
    """Run a full paginated scrape for one fuente and record it.

    Returns the scraper stats dict augmented with the ``run_id`` used for the
    written ``RegistroEjecucion`` row. A mid-run failure is still recorded: the
    row is written with ``errores > 0`` and the error message is surfaced in the
    returned stats.
    """
    run_id = run_id or _new_manual_run_id()
    runner = runner or ScraperRunner(session)

    try:
        stats: dict = dict(await runner.run_paginated_scraper(
            fuente, results_per_page=results_per_page
        ))
    except Exception as exc:  # noqa: BLE001 — surface, don't swallow
        stats = {
            "fuente_id": fuente.id,
            "nombre": getattr(fuente, "nombre", None),
            "nuevas": 0,
            "duplicadas": 0,
            "errores": 1,
            "paginas_procesadas": 0,
            "tiempo_segundos": 0.0,
            "error": str(exc),
        }

    nuevas = int(stats.get("nuevas") or 0)
    duplicadas = int(stats.get("duplicadas") or 0)
    errores = int(stats.get("errores") or 0)
    if stats.get("error") and errores == 0:
        # run_paginated_scraper reports a whole-run failure with errores=0;
        # the manual run-log row must still show the failure.
        errores = 1
        stats["errores"] = 1

    duracion = stats.get("tiempo_segundos")
    if duracion is None:
        duracion = stats.get("duracion_segundos")

    registro = RegistroEjecucion(
        fuente_id=fuente.id,
        tipo="scrape",
        total=nuevas + duplicadas + errores,
        nuevas=nuevas,
        duplicadas=duplicadas,
        errores=errores,
        duracion_segundos=duracion,
        run_id=run_id,
    )
    if now is not None:
        registro.fecha = now

    try:
        RegistroEjecucionCRUD.create(session, registro)
    except Exception:  # noqa: BLE001 — a log-write failure must not mask stats
        pass

    result = dict(stats)
    result["run_id"] = run_id
    return result


async def run_manual_sold_check(
    session,
    fuente: Fuente,
    *,
    run_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Run a fuente-scoped sold-check and return its stats.

    Thin delegate: ``check_sold_properties(session, fuente_id=fuente.id)`` writes
    its own single ``tipo="sold_check"`` ``RegistroEjecucion`` row (S4), so this
    helper never writes one. ``run_id`` is accepted for call-site symmetry but
    is not applied — the scoped sold-check row carries that function's own uuid.
    """
    return await check_sold_properties(session, limit=limit, fuente_id=fuente.id)

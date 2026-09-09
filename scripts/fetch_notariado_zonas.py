#!/usr/bin/env python3
"""
Weekly PUBLIC ingestion of penotariado's `price-avg` endpoint.

Additive sibling of `fetch_notariado_stats.py`: it shares only the combo
vocabulary and mirrors the run-log/exit-code conventions. It sends no
credentials and reads no secret. For every zona slug in `ZONA_SLUGS` it
loads that barrio's ArcGIS polygon once, then queries the 4 fixed
(property, construction) combos, applying an append-if-outcome-changed
dedup rule against the latest stored row per combo.

Since `RegistroEjecucion.fuente_id` is a required FK to `Fuente` and this
public source has no scraper `Fuente`, the script gets-or-creates a single
inactive sentinel `Fuente` row to anchor the run log — see
`_get_or_create_sentinel_fuente()`.

A run always writes exactly one `RegistroEjecucion(tipo="notariado_zonas")`
row (success and failure). PAV002 ("area with limited data") is an expected
no-data outcome, never an error, and never forces a non-zero exit; a run
where every combo returned PAV002 still exits 0 but logs a WARNING. Any
real error (network failure, non-PAV002 non-2xx, unusable geometry file)
forces a non-zero exit so CI surfaces it.

Usage:
    python scripts/fetch_notariado_zonas.py
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session  # noqa: E402

from db.database import (  # noqa: E402
    engine,
    EstadisticaZonaNotarialCRUD,
    FuenteCRUD,
    RegistroEjecucionCRUD,
)
from db.models import (  # noqa: E402
    EstadisticaZonaNotarial,
    Fuente,
    RegistroEjecucion,
)
from scraper.notariado_client import ZONA_COMBOS, fetch_price_avg  # noqa: E402
from scraper.notariado_zonas import ZONA_SLUGS, load_zona_geometry  # noqa: E402

logger = logging.getLogger(__name__)

SENTINEL_FUENTE_URL = "internal://notariado-zonas"
SENTINEL_FUENTE_NOMBRE = "Notariado zones (public price-avg)"


def _get_or_create_sentinel_fuente(session: Session) -> Fuente:
    """Get-or-create the inactive placeholder Fuente used only to anchor
    this script's RegistroEjecucion rows (fuente_id is a required FK and
    this public source has no real scraper Fuente)."""
    fuente = FuenteCRUD.get_by_url(session, SENTINEL_FUENTE_URL)
    if fuente:
        return fuente
    return FuenteCRUD.create(
        session,
        Fuente(
            nombre=SENTINEL_FUENTE_NOMBRE,
            url=SENTINEL_FUENTE_URL,
            tipo_scraper="notariado_zonas",
            activa=False,
        ),
    )


def ingest_zona_combo(
    session: Session,
    zona: str,
    geometry: dict,
    property_slug: str,
    construction_slug: str,
    where: str,
) -> tuple[int, int]:
    """Fetch one (zona, combo) price-avg and dedup-insert a row.

    Returns `(rows_inserted, returned_pav002)` — the first is 0 or 1, the
    second is 1 when the endpoint reported PAV002 this run (independent of
    whether a row was inserted).
    """
    value = fetch_price_avg(geometry, where)
    if value is None:
        price_avg: Optional[float] = None
        sin_datos = True
    else:
        price_avg = float(value)
        sin_datos = False

    latest = EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
        session, zona, property_slug, construction_slug
    )
    changed = latest is None or (latest.sin_datos, latest.price_avg) != (
        sin_datos,
        price_avg,
    )

    inserted = 0
    if changed:
        EstadisticaZonaNotarialCRUD.create(
            session,
            EstadisticaZonaNotarial(
                zona=zona,
                property_type=property_slug,
                construction_type=construction_slug,
                price_avg=price_avg,
                sin_datos=sin_datos,
                where_clause=where,
            ),
        )
        inserted = 1

    return inserted, 1 if sin_datos else 0


def _write_run_log(
    fuente_id: Optional[int],
    *,
    total: int,
    inserted: int,
    errores: int,
    sin_datos: int,
    duracion_segundos: float,
) -> None:
    try:
        with Session(engine) as session:
            if fuente_id is None:
                fuente_id = _get_or_create_sentinel_fuente(session).id
            RegistroEjecucionCRUD.create(
                session,
                RegistroEjecucion(
                    fuente_id=fuente_id,
                    tipo="notariado_zonas",
                    total=total,
                    nuevas=inserted,
                    errores=errores,
                    sin_datos=sin_datos,
                    duracion_segundos=duracion_segundos,
                ),
            )
    except Exception as exc:  # pragma: no cover - defensive, log-only path
        logger.warning("⚠️ Could not write RegistroEjecucion: %s", exc)


def main(argv=None) -> int:
    """Run one full ingestion cycle. `argv` is accepted for test-call
    parity; there are no command-line flags."""
    start = time.time()
    inserted = 0
    error_count = 0
    no_data_count = 0
    failed = False
    fuente_id: Optional[int] = None

    try:
        with Session(engine) as session:
            fuente_id = _get_or_create_sentinel_fuente(session).id

            for zona in ZONA_SLUGS:
                try:
                    geometry = load_zona_geometry(zona)
                except Exception as exc:
                    error_count += 1
                    logger.error("❌ zona %s geometry unavailable: %s", zona, exc)
                    continue

                for property_slug, construction_slug, where in ZONA_COMBOS:
                    try:
                        row_inserted, row_no_data = ingest_zona_combo(
                            session,
                            zona,
                            geometry,
                            property_slug,
                            construction_slug,
                            where,
                        )
                        inserted += row_inserted
                        no_data_count += row_no_data
                    except Exception as exc:
                        # Any real failure (NotariadoPriceAvgError, or an
                        # unexpected error) is isolated to this combo; the
                        # siblings and remaining zonas still run.
                        error_count += 1
                        logger.error(
                            "❌ %s/%s/%s: %s",
                            zona,
                            property_slug,
                            construction_slug,
                            exc,
                        )
    except Exception as exc:
        failed = True
        logger.error("❌ Fatal error: %s", exc, exc_info=True)

    if error_count and not failed:
        failed = True

    total = len(ZONA_SLUGS) * len(ZONA_COMBOS)
    errores = error_count if not failed else max(error_count, 1)
    duracion = round(time.time() - start, 2)

    _write_run_log(
        fuente_id,
        total=total,
        inserted=inserted,
        errores=errores,
        sin_datos=no_data_count,
        duracion_segundos=duracion,
    )

    if no_data_count == total and not failed:
        logger.warning(
            "⚠️ Every combo returned PAV002 — check polygons/endpoint."
        )

    logger.info(
        "📊 notariado_zonas — total=%s nuevas=%s errores=%s sin_datos=%s",
        total,
        inserted,
        errores,
        no_data_count,
    )

    return 1 if failed else 0


if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/fetch_notariado_zonas.log", mode="a"),
        ],
    )
    sys.exit(main())

#!/usr/bin/env python3
"""
Weekly ingestion of official Consejo General del Notariado market statistics.

Logs in via ROPC, fetches the 4 fixed (propertyType, constructionType)
combinations for `LOCATION_CODE`, dedups against the latest stored row per
combo (by `last_data_update`), persists structured + raw JSON rows, and
writes a `RegistroEjecucion` run-log row (`tipo="notariado_stats"`) on both
success and failure. Exits non-zero on any failure so CI surfaces it.

Since RegistroEjecucion.fuente_id is a required FK to Fuente (there is no
scraper `Fuente` for this source), the script gets-or-creates a single
inactive sentinel Fuente row to anchor the run log — see
`_get_or_create_sentinel_fuente()`.

Usage:
    python scripts/fetch_notariado_stats.py              # current data only
    python scripts/fetch_notariado_stats.py --backfill    # also persist
                                                            # nested historical
                                                            # monthly/quarterly/
                                                            # yearly periods
"""

import json
import logging
import sys
import time
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session  # noqa: E402

from config import settings  # noqa: E402
from db.database import (  # noqa: E402
    engine,
    EstadisticaNotarialCRUD,
    FuenteCRUD,
    RegistroEjecucionCRUD,
)
from db.models import EstadisticaNotarial, Fuente, RegistroEjecucion  # noqa: E402
from scraper.notariado_client import (  # noqa: E402
    COMBOS,
    CONSTRUCTION_TYPES,
    LOCATION_CODE,
    PROPERTY_TYPES,
    NotariadoAuthError,
    fetch_quota,
    fetch_stats,
    login,
)

logger = logging.getLogger(__name__)

SENTINEL_FUENTE_URL = "internal://notariado-stats"
SENTINEL_FUENTE_NOMBRE = "Notariado (estadísticas oficiales)"

_SLUG_BY_PROPERTY_CODE = {code: slug for slug, code in PROPERTY_TYPES.items()}
_SLUG_BY_CONSTRUCTION_CODE = {code: slug for slug, code in CONSTRUCTION_TYPES.items()}

_HISTORICAL_KEYS = ("monthly", "quarterly", "yearly")


def _get_or_create_sentinel_fuente(session: Session) -> Fuente:
    """Get-or-create the inactive placeholder Fuente used only to anchor
    this script's RegistroEjecucion rows (fuente_id is a required FK and
    this source has no real scraper Fuente)."""
    fuente = FuenteCRUD.get_by_url(session, SENTINEL_FUENTE_URL)
    if fuente:
        return fuente
    return FuenteCRUD.create(
        session,
        Fuente(
            nombre=SENTINEL_FUENTE_NOMBRE,
            url=SENTINEL_FUENTE_URL,
            tipo_scraper="notariado_stats",
            activa=False,
        ),
    )


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _map_current_row(
    response: dict, property_type_code: int, construction_type_code: int
) -> EstadisticaNotarial:
    return EstadisticaNotarial(
        location_code=LOCATION_CODE,
        property_type=_SLUG_BY_PROPERTY_CODE[property_type_code],
        construction_type=_SLUG_BY_CONSTRUCTION_CODE[construction_type_code],
        current_price_per_sqm=response.get("currentPricePerSqm"),
        current_number_of_sales=response.get("currentNumberOfSales"),
        current_average_price=response.get("currentAveragePrice"),
        current_average_area_sqm=response.get("currentAverageAreaSqm"),
        rate_price_change=response.get("ratePriceChange"),
        last_data_update=_parse_datetime(response["lastDataUpdate"]),
        report_date=_parse_datetime(response["reportDate"]),
        raw_json=json.dumps(response),
    )


def _map_historical_period(
    period: dict, property_type_code: int, construction_type_code: int
) -> EstadisticaNotarial:
    return EstadisticaNotarial(
        location_code=LOCATION_CODE,
        property_type=_SLUG_BY_PROPERTY_CODE[property_type_code],
        construction_type=_SLUG_BY_CONSTRUCTION_CODE[construction_type_code],
        current_price_per_sqm=period.get("pricePerSqm"),
        current_number_of_sales=period.get("numberOfSales"),
        current_average_price=period.get("averagePrice"),
        current_average_area_sqm=period.get("averageAreaSqm"),
        rate_price_change=period.get("rateChange"),
        last_data_update=_parse_datetime(period["dataUpdate"]),
        report_date=_parse_datetime(period["reportDate"]),
        raw_json=json.dumps(period),
    )


def _historical_periods(response: dict) -> list:
    """Flatten the response's nested monthly/quarterly/yearly period arrays,
    if present, into a single list. No separate endpoint call — the standard
    response already carries them."""
    historical = response.get("historicalData") or {}
    periods = []
    for key in _HISTORICAL_KEYS:
        periods.extend(historical.get(key) or [])
    return periods


def ingest_combo(
    session: Session,
    token: str,
    property_type_code: int,
    construction_type_code: int,
    *,
    backfill: bool,
) -> int:
    """Fetch one combo, dedup-insert the current row, and (if --backfill)
    insert every nested historical period. Returns the number of rows
    inserted."""
    response = fetch_stats(
        token, LOCATION_CODE, property_type_code, construction_type_code
    )
    inserted = 0

    slug_property = _SLUG_BY_PROPERTY_CODE[property_type_code]
    slug_construction = _SLUG_BY_CONSTRUCTION_CODE[construction_type_code]

    latest = EstadisticaNotarialCRUD.get_latest_for_combo(
        session, LOCATION_CODE, slug_property, slug_construction
    )
    current_row = _map_current_row(response, property_type_code, construction_type_code)

    if latest is None or latest.last_data_update != current_row.last_data_update:
        EstadisticaNotarialCRUD.create(session, current_row)
        inserted += 1

    if backfill:
        for period in _historical_periods(response):
            row = _map_historical_period(
                period, property_type_code, construction_type_code
            )
            EstadisticaNotarialCRUD.create(session, row)
            inserted += 1

    return inserted


def _write_run_log(
    fuente_id: Optional[int],
    *,
    total: int,
    inserted: int,
    errores: int,
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
                    tipo="notariado_stats",
                    total=total,
                    nuevas=inserted,
                    errores=errores,
                    duracion_segundos=duracion_segundos,
                ),
            )
    except Exception as exc:  # pragma: no cover - defensive, log-only path
        logger.warning(f"⚠️ No se pudo escribir RegistroEjecucion: {exc}")


def _log_quota(token: str) -> None:
    try:
        quota = fetch_quota(token)
        logger.info(
            "📊 API quota — numberMonthlyQueries=%s, numberExtraQueries=%s",
            quota.get("numberMonthlyQueries"),
            quota.get("numberExtraQueries"),
        )
    except Exception as exc:
        logger.warning(f"⚠️ Could not fetch API quota: {exc}")


def main(argv=None) -> int:
    parser = ArgumentParser(
        description="Ingest official Consejo General del Notariado market stats"
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Also persist nested monthly/quarterly/yearly historical periods",
    )
    args = parser.parse_args(argv)

    start = time.time()
    total_inserted = 0
    error_count = 0
    fuente_id: Optional[int] = None
    token: Optional[str] = None
    failed = False
    failure_reason: Optional[str] = None

    try:
        with Session(engine) as session:
            fuente = _get_or_create_sentinel_fuente(session)
            fuente_id = fuente.id

            token = login(settings.NOTARIADO_EMAIL, settings.NOTARIADO_PASSWORD)

            for property_type_code, construction_type_code in COMBOS:
                try:
                    total_inserted += ingest_combo(
                        session,
                        token,
                        property_type_code,
                        construction_type_code,
                        backfill=args.backfill,
                    )
                except Exception as exc:
                    error_count += 1
                    logger.error(
                        f"❌ Error ingesting combo ({property_type_code},"
                        f"{construction_type_code}): {exc}"
                    )
    except NotariadoAuthError as exc:
        failed = True
        failure_reason = str(exc)
        logger.error(f"❌ Auth failed: {exc}")
    except Exception as exc:
        failed = True
        failure_reason = str(exc)
        logger.error(f"❌ Fatal error: {exc}", exc_info=True)

    if error_count and not failed:
        failed = True
        failure_reason = f"{error_count} combo(s) failed"

    if token is not None:
        _log_quota(token)

    duracion = round(time.time() - start, 2)
    _write_run_log(
        fuente_id,
        total=len(COMBOS),
        inserted=total_inserted,
        errores=error_count if not failed else max(error_count, 1),
        duracion_segundos=duracion,
    )

    if failed:
        logger.error(f"❌ Run failed: {failure_reason}")
        return 1

    logger.info(f"✅ Run complete — inserted {total_inserted} row(s)")
    return 0


if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/fetch_notariado_stats.log", mode="a"),
        ],
    )
    sys.exit(main())

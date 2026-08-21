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
    python scripts/fetch_notariado_stats.py --backfill    # also persist the
                                                            # 12-month price-
                                                            # per-sqm series
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

_SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


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
    """Parse to a naive UTC datetime. `EstadisticaNotarial.last_data_update`
    has no `timezone=True`, so SQLite silently drops tzinfo on read-back —
    an aware value here would never equal the same instant read back from
    the DB, breaking dedup. Stripping tzinfo up front keeps both sides
    naive and comparable."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=None)


def _map_current_row(
    response: dict, property_type_code: int, construction_type_code: int
) -> EstadisticaNotarial:
    """Map the live response shape (verified 2026-08-21): everything lives
    under `data.statistics`, not the response's top level as originally
    assumed. `ratePriceChange` is itself `{"value": ..., "metric": [...]}`,
    not a bare float."""
    stats = response["data"]["statistics"]
    rate_change = stats.get("ratePriceChange")
    rate_change_value = (
        rate_change.get("value") if isinstance(rate_change, dict) else rate_change
    )
    return EstadisticaNotarial(
        location_code=LOCATION_CODE,
        property_type=_SLUG_BY_PROPERTY_CODE[property_type_code],
        construction_type=_SLUG_BY_CONSTRUCTION_CODE[construction_type_code],
        current_price_per_sqm=stats.get("currentPricePerSqm"),
        current_number_of_sales=stats.get("currentNumberOfSales"),
        current_average_price=stats.get("currentAveragePrice"),
        current_average_area_sqm=stats.get("currentAverageAreaSqm"),
        rate_price_change=rate_change_value,
        last_data_update=_parse_datetime(stats["lastDataUpdate"]),
        report_date=_parse_datetime(stats["reportDate"]),
        raw_json=json.dumps(response),
    )


def _parse_month_legend(legend: str) -> Optional[datetime]:
    """Parse a Spanish month legend like "Dic 2025" into its first-of-month
    datetime. Returns None for anything else (quarter ranges like "Jul-Sep
    2024", bare years like "2025") — those buckets aren't backfilled yet."""
    parts = legend.strip().split()
    if len(parts) != 2:
        return None
    month_abbr, year = parts[0].lower()[:3], parts[1]
    month = _SPANISH_MONTHS.get(month_abbr)
    if month is None or not year.isdigit():
        return None
    return datetime(int(year), month, 1)


def _12month_metric_by_legend(stats: dict, metric_name: str) -> dict:
    """Return {legend: entry} for one metric's 12months bucket."""
    metric = stats.get(metric_name, {}).get("12months", {}).get("metric", [])
    return {entry.get("legend"): entry for entry in metric if entry.get("legend")}


def _historical_periods(
    response: dict, property_type_code: int, construction_type_code: int
) -> list:
    """Map the 12-month price-per-sqm, number-of-sales, and average-price
    series together (matched by legend, e.g. "Dic 2025") into one row per
    non-zero month.

    The design originally assumed a flat `historicalData.monthly/quarterly/
    yearly` list of full period records; the real response has no such
    thing. It exposes per-metric time-bucket series (`pricePerSqm` /
    `numberOfSales` / `averagePrice`, each split into `12months` / `2years`
    / `5years` / `12years`), keyed by a locale legend string with no real
    timestamp. Only the `12months` buckets are mapped here — they're the
    ones with real (non-estimated) monthly values in practice. The quarter/
    year buckets need their own design pass (legend parsing across
    "Jul-Sep 2024"-style ranges and bare years) before being backfilled;
    `raw_json` on the current row preserves the full nested series either
    way, so nothing is lost by deferring them.

    A month with `pricePerSqm.value == 0` means the notary hasn't reported
    real sales for it yet (only a trend `estimation`) — those are skipped
    rather than stored as a misleading zero price point.
    """
    stats = response.get("data", {}).get("statistics", {})
    price_by_legend = _12month_metric_by_legend(stats, "pricePerSqm")
    sales_by_legend = _12month_metric_by_legend(stats, "numberOfSales")
    avg_price_by_legend = _12month_metric_by_legend(stats, "averagePrice")
    report_date = _parse_datetime(stats["reportDate"]) if stats.get("reportDate") else None

    rows = []
    for legend, price_entry in price_by_legend.items():
        value = price_entry.get("value")
        if not value:
            continue
        month_date = _parse_month_legend(legend)
        if month_date is None:
            logger.warning(
                "⚠️ Could not parse month legend %r for combo (%s,%s) — skipped.",
                legend, property_type_code, construction_type_code,
            )
            continue
        rows.append(
            EstadisticaNotarial(
                location_code=LOCATION_CODE,
                property_type=_SLUG_BY_PROPERTY_CODE[property_type_code],
                construction_type=_SLUG_BY_CONSTRUCTION_CODE[construction_type_code],
                current_price_per_sqm=value,
                current_number_of_sales=sales_by_legend.get(legend, {}).get("value"),
                current_average_price=avg_price_by_legend.get(legend, {}).get("value"),
                last_data_update=month_date,
                report_date=report_date or month_date,
                raw_json=json.dumps(
                    {
                        "legend": legend,
                        "pricePerSqm": price_entry,
                        "numberOfSales": sales_by_legend.get(legend),
                        "averagePrice": avg_price_by_legend.get(legend),
                    }
                ),
            )
        )
    return rows


def ingest_combo(
    session: Session,
    token: str,
    property_type_code: int,
    construction_type_code: int,
    *,
    backfill: bool,
) -> int:
    """Fetch one combo, dedup-insert the current row, and (if --backfill)
    insert one row per non-zero month in the 12-month price-per-sqm series
    not already stored with the same value. Returns the number of rows
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
        def _dedup_key(row: EstadisticaNotarial) -> tuple:
            return (
                row.last_data_update,
                row.current_price_per_sqm,
                row.current_number_of_sales,
                row.current_average_price,
            )

        existing = {
            _dedup_key(row)
            for row in EstadisticaNotarialCRUD.get_by_combo(
                session, LOCATION_CODE, slug_property, slug_construction
            )
        }
        for row in _historical_periods(
            response, property_type_code, construction_type_code
        ):
            if _dedup_key(row) in existing:
                continue
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

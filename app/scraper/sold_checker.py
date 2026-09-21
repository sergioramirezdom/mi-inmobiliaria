"""Verify active properties and mark sold/reserved ones as inactive."""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from sqlmodel import Session, select

from db.models import Propiedad, Fuente, PrecioHistorico, RegistroEjecucion
from db.database import RegistroEjecucionCRUD
from .config import ScraperConfig
from .detail_factory import get_detail_scraper
from .check_outcome import (
    CheckOutcome,
    apply_check_outcome,
    classify_check_outcome,
    classify_fetch_error,
    source_looks_broken,
)
from .price_drop import build_price_drop_entry

logger = logging.getLogger(__name__)


def _get_scraper(detail_type: Optional[str], config: ScraperConfig):
    """Resolve a detail scraper for `detail_type`.

    Delegates to the shared `detail_factory.get_detail_scraper()` registry so
    this call site cannot silently diverge from `paginated_scraper.py` again
    (the Aug 20 incident: this function was missing `uriahomes`/`jimenezruiz`
    and mis-classified those properties with the generic fallback scraper).
    Kept as a thin alias for import-compatibility with existing tests/callers.
    """
    return get_detail_scraper(detail_type, config)


def _fuente_stats(por_fuente: Dict[int, Dict[str, int]], fuente_id: Optional[int]) -> Dict[str, int]:
    """Get or create the per-fuente stat bucket used to build RegistroEjecucion rows."""
    return por_fuente.setdefault(
        fuente_id, {"total": 0, "activas": 0, "vendidas": 0, "sin_datos": 0, "errores": 0}
    )


async def check_sold_properties(
    session: Session,
    limit: Optional[int] = None,
    fuente_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch all active properties' detail pages and mark sold/reserved ones inactive.

    Uses `classify_check_outcome()` + `apply_check_outcome()` as the single
    gate: an explicit GONE signal (a 404/410 response or a sold status on the
    ficha) deactivates immediately, an EMPTY (no-data) result only deactivates
    after a second confirming strike on a later day (`STRIKE_THRESHOLD`,
    `STRIKE_MIN_INTERVAL`), and fetch errors never touch the strike counter.
    EMPTY results are held until the whole run is known: when most of a
    fuente's listings came back EMPTY/ERROR the source is broken (anti-bot
    page, layout change), so none of them is struck and the fuente is reported
    in ``stats["fuentes_fallidas"]``.

    When `fuente_id` is omitted or `None`, every active property across all
    fuentes is checked (the scheduler path). When `fuente_id` is given, only
    that fuente's active properties are re-fetched, and the per-fuente
    RegistroEjecucion loop below naturally emits exactly one `sold_check` row
    for it. The omitted-parameter path is byte-identical to before.

    Returns stats dict including a 'vendidas_lista' list for Telegram
    notifications and a 'por_fuente' breakdown used to write one
    RegistroEjecucion row per fuente touched.
    """
    start_time = time.time()
    run_id = str(uuid.uuid4())

    stmt = select(Propiedad).where(Propiedad.activa == True)
    if fuente_id is not None:
        stmt = stmt.where(Propiedad.fuente_id == fuente_id)
    stmt = stmt.order_by(Propiedad.fecha_scraping.asc())
    propiedades = session.exec(stmt).all()

    if limit:
        propiedades = list(propiedades)[:limit]

    fuentes = {f.id: f for f in session.exec(select(Fuente)).all()}

    stats: Dict[str, Any] = {
        "total": len(propiedades),
        "vendidas": 0,
        "activas": 0,
        "errores": 0,
        "sin_datos": 0,
        "vendidas_lista": [],
        "por_fuente": {},
        "fuentes_fallidas": {},
    }
    por_fuente = stats["por_fuente"]
    pending_empty: Dict[Optional[int], list] = {}

    def record_deactivated(index: int, prop) -> None:
        logger.info(f"[{index}/{stats['total']}] 🚫 {prop.estado_baja}: {prop.titulo[:60]}")
        stats["vendidas"] += 1
        _fuente_stats(por_fuente, prop.fuente_id)["vendidas"] += 1
        stats["vendidas_lista"].append({
            "titulo": prop.titulo,
            "url": prop.url_original,
            "precio": prop.precio,
            "estado": prop.estado_baja,
        })

    logger.info(f"🔍 Verificando {stats['total']} propiedades activas...")

    for i, prop in enumerate(propiedades, 1):
        fstats = _fuente_stats(por_fuente, prop.fuente_id)
        fstats["total"] += 1
        try:
            fuente = fuentes.get(prop.fuente_id)
            config = (
                ScraperConfig.from_fuente_notas(fuente.notas)
                if fuente and fuente.notas
                else ScraperConfig()
            )
            scraper = _get_scraper(config.detail_scraper_type, config)
            details = await scraper.scrape_property_details(prop.url_original)

            outcome = classify_check_outcome(details)
            if outcome is CheckOutcome.EMPTY:
                # Struck only after the run, once we know the source is not broken.
                pending_empty.setdefault(prop.fuente_id, []).append((i, prop))
                continue
            estado = details.get("estado", "Vendida") if outcome is CheckOutcome.GONE else None
            result = apply_check_outcome(session, prop, outcome, estado=estado)

            if result == "deactivated":
                record_deactivated(i, prop)
            else:  # "alive"
                logger.debug(f"[{i}/{stats['total']}] ✅ Activa: {prop.titulo[:60]}")
                stats["activas"] += 1
                fstats["activas"] += 1
                # Price-change detection for EVERY source. The detail page is
                # already fetched above for the sold/alive check, so reading
                # its price here keeps PrecioHistorico complete for scraped
                # sources too (issue #1) — not just detail_scraper_type ==
                # "manual_auto". The paginated scraper only records a change
                # for duplicates older than 3 days, so this daily pass is the
                # backstop that makes the cumulative-drop math correct.
                nuevo_precio = details.get("precio")
                if nuevo_precio and prop.precio and abs(nuevo_precio - prop.precio) > 100:
                    precio_anterior = prop.precio
                    prop.precio_anterior = precio_anterior
                    prop.precio = nuevo_precio
                    prop.updated_at = datetime.utcnow()
                    session.add(prop)
                    session.add(PrecioHistorico(propiedad_id=prop.id, precio=nuevo_precio))
                    session.commit()
                    if nuevo_precio < precio_anterior:
                        bajada = round(100 * (precio_anterior - nuevo_precio) / precio_anterior, 1)
                        logger.info(f"[{i}/{stats['total']}] 📉 Bajada {bajada}%: {prop.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")
                        stats.setdefault("bajadas_precio", []).append(
                            build_price_drop_entry(
                                prop, precio_anterior, nuevo_precio, bajada
                            )
                        )
                    else:
                        logger.info(f"[{i}/{stats['total']}] 📈 Subida precio: {prop.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")

        except Exception as e:
            # Only a 404/410 response means the listing is gone; timeouts, 5xx and
            # network errors are counted as errors and never touch the listing.
            if classify_fetch_error(e) is CheckOutcome.GONE:
                try:
                    apply_check_outcome(session, prop, CheckOutcome.GONE, estado="No disponible")
                    record_deactivated(i, prop)
                except Exception:
                    session.rollback()
                    stats["errores"] += 1
                    fstats["errores"] += 1
            else:
                # Fetch/network errors are a no-op for the strike counter — never
                # routed through apply_check_outcome(), only counted as errors.
                logger.warning(f"[{i}/{stats['total']}] ⚠️ Error en {prop.url_original[:60]}: {e}")
                stats["errores"] += 1
                fstats["errores"] += 1

    # Strike the EMPTY results, unless they show the source itself is broken.
    for fuente_key, empties in pending_empty.items():
        fstats = _fuente_stats(por_fuente, fuente_key)
        if source_looks_broken(len(empties) + fstats["errores"], fstats["total"]):
            motivo = (
                f"{len(empties)} of {fstats['total']} listings returned no data and "
                f"{fstats['errores']} failed to fetch (anti-bot page or layout change?); "
                "nothing was deactivated"
            )
            logger.error(f"❌ Fuente {fuente_key}: {motivo}")
            stats["fuentes_fallidas"][fuente_key] = motivo
            fstats["errores"] += len(empties)
            fstats["error_mensaje"] = motivo
            stats["errores"] += len(empties)
            continue
        for i, prop in empties:
            try:
                result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)
            except Exception as e:
                session.rollback()
                logger.warning(f"[{i}/{stats['total']}] ⚠️ Error en {prop.url_original[:60]}: {e}")
                stats["errores"] += 1
                fstats["errores"] += 1
                continue
            if result == "deactivated":
                record_deactivated(i, prop)
            else:  # "strike"
                logger.warning(
                    f"[{i}/{stats['total']}] ⚠️ Scraper sin datos válidos para "
                    f"{prop.url_original[:60]} — 1ª confirmación, aún activa"
                )
                stats["sin_datos"] += 1
                fstats["sin_datos"] += 1

    elapsed = time.time() - start_time

    logger.info(
        f"✅ Verificación completa — vendidas: {stats['vendidas']}, "
        f"activas: {stats['activas']}, sin_datos: {stats['sin_datos']}, "
        f"errores: {stats['errores']}"
    )

    # One RegistroEjecucion row per fuente touched. All rows for this run
    # share the whole-run duration (simplest cadence — see design's
    # "Run-log write site" decision; per-fuente sub-timing was not specified).
    for fuente_id, fstat in por_fuente.items():
        if fuente_id is None:
            continue
        try:
            RegistroEjecucionCRUD.create(
                session,
                RegistroEjecucion(
                    fuente_id=fuente_id,
                    tipo="sold_check",
                    total=fstat["total"],
                    activas=fstat["activas"],
                    vendidas=fstat["vendidas"],
                    sin_datos=fstat["sin_datos"],
                    errores=fstat["errores"],
                    error_mensaje=fstat.get("error_mensaje"),
                    duracion_segundos=round(elapsed, 2),
                    run_id=run_id,
                ),
            )
        except Exception as e:
            logger.warning(f"⚠️ No se pudo escribir RegistroEjecucion para fuente {fuente_id}: {e}")

    return stats

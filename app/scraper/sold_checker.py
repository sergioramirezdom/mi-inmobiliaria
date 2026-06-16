"""Verify active properties and mark sold/reserved ones as inactive."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from sqlmodel import Session, select

from db.models import Propiedad, Fuente
from .config import ScraperConfig
from .puerto_inmobiliaria import PuertoInmobiliariaScraper
from .mobilia_scraper import MobiliaScraper
from .punto_hogar_scraper import PuntoHogarScraper
from .guadalete_scraper import GuadaleteScraper

logger = logging.getLogger(__name__)


def _get_scraper(detail_type: Optional[str], config: ScraperConfig):
    if detail_type == "mobilia":
        return MobiliaScraper(config)
    elif detail_type == "puntohogar":
        return PuntoHogarScraper(config)
    elif detail_type == "guadalete":
        return GuadaleteScraper(config)
    return PuertoInmobiliariaScraper(config)


async def check_sold_properties(session: Session, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Fetch all active properties' detail pages and mark sold/reserved ones inactive.

    Returns stats dict including a 'vendidas_lista' list for Telegram notifications.
    """
    propiedades = session.exec(
        select(Propiedad).where(Propiedad.activa == True).order_by(Propiedad.fecha_scraping.asc())
    ).all()

    if limit:
        propiedades = list(propiedades)[:limit]

    fuentes = {f.id: f for f in session.exec(select(Fuente)).all()}

    stats: Dict[str, Any] = {
        "total": len(propiedades),
        "vendidas": 0,
        "activas": 0,
        "errores": 0,
        "vendidas_lista": [],
    }

    logger.info(f"🔍 Verificando {stats['total']} propiedades activas...")

    for i, prop in enumerate(propiedades, 1):
        try:
            fuente = fuentes.get(prop.fuente_id)
            config = (
                ScraperConfig.from_fuente_notas(fuente.notas)
                if fuente and fuente.notas
                else ScraperConfig()
            )
            scraper = _get_scraper(config.detail_scraper_type, config)
            details = await scraper.scrape_property_details(prop.url_original)

            if not details.get("activa", True):
                estado = details.get("estado", "Vendida")
                prop.activa = False
                prop.estado = estado
                prop.fecha_baja = datetime.utcnow()
                session.add(prop)
                session.commit()
                logger.info(f"[{i}/{stats['total']}] 🚫 {estado}: {prop.titulo[:60]}")
                stats["vendidas"] += 1
                stats["vendidas_lista"].append({
                    "titulo": prop.titulo,
                    "url": prop.url_original,
                    "precio": prop.precio,
                    "estado": estado,
                })
            else:
                logger.debug(f"[{i}/{stats['total']}] ✅ Activa: {prop.titulo[:60]}")
                stats["activas"] += 1

        except Exception as e:
            err_str = str(e)
            # 404 via raise_for_status() → property gone, mark as inactive
            if "404" in err_str or "Not Found" in err_str:
                try:
                    prop.activa = False
                    prop.estado = "No disponible"
                    prop.fecha_baja = datetime.utcnow()
                    session.add(prop)
                    session.commit()
                    logger.info(f"[{i}/{stats['total']}] 🚫 404 No disponible: {prop.titulo[:60]}")
                    stats["vendidas"] += 1
                    stats["vendidas_lista"].append({
                        "titulo": prop.titulo,
                        "url": prop.url_original,
                        "precio": prop.precio,
                        "estado": "No disponible",
                    })
                except Exception:
                    stats["errores"] += 1
            else:
                logger.warning(f"[{i}/{stats['total']}] ⚠️ Error en {prop.url_original[:60]}: {e}")
                stats["errores"] += 1

    logger.info(
        f"✅ Verificación completa — vendidas: {stats['vendidas']}, "
        f"activas: {stats['activas']}, errores: {stats['errores']}"
    )
    return stats

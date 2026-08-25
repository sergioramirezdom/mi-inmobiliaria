#!/usr/bin/env python3
"""One-off cleanup: NULL out `fecha_publicacion` values stamped by the old
scraper bug (NEOPOLIS, PUERTO_INMOBILIARIA, MOBILIA used to set it to
`datetime.utcnow()` at scrape time — see spec "Scrapers stop stamping fake
fecha_publicacion").

`fecha_publicacion` is now authoritative for the real listing publication
date (app/listing_date.py resolver): a row where it was stamped to the same
instant as `fecha_scraping` is not a real user-confirmed date, and must be
cleared so the resolver correctly falls back to `fecha_scraping`.

A row is considered "falsely stamped" when
`abs(fecha_publicacion - fecha_scraping) < 60s`.

Idempotent — safe to run more than once; already-NULL or already-corrected
rows are never touched.

Usage:
    python scripts/limpiar_fecha_publicacion_falsa.py             # apply
    python scripts/limpiar_fecha_publicacion_falsa.py --dry-run   # preview only
"""

import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad

UMBRAL_SEGUNDOS = 60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def encontrar_filas_afectadas(session: Session) -> list[Propiedad]:
    """Propiedades con `fecha_publicacion` estampada a scrape-time (bug)."""
    props = session.exec(
        select(Propiedad).where(Propiedad.fecha_publicacion != None)
    ).all()
    return [
        p for p in props
        if p.fecha_scraping is not None
        and abs((p.fecha_publicacion - p.fecha_scraping).total_seconds()) < UMBRAL_SEGUNDOS
    ]


def main() -> None:
    parser = ArgumentParser(
        description="Limpia fecha_publicacion falsa estampada por el bug de scrapers antiguo."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo muestra cuántas filas se verían afectadas, sin escribir nada.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        afectadas = encontrar_filas_afectadas(session)
        logger.info(f"Filas con fecha_publicacion falsa detectadas: {len(afectadas)}")

        if args.dry_run:
            logger.info("--dry-run: no se ha modificado ninguna fila.")
            return

        for p in afectadas:
            p.fecha_publicacion = None
            session.add(p)
        session.commit()
        logger.info(f"✅ Limpieza completada: {len(afectadas)} fila(s) corregida(s).")


if __name__ == "__main__":
    main()

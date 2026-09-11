#!/usr/bin/env python3
"""Resolve Propiedad.zona_poligono_id from coordinates (one-off / on-demand).

For every property that has latitud/longitud, find the app_zona_poligono
whose geometry contains the point and store its id. Run it after drawing or
editing polygons in the web app, or to backfill existing rows.

Usage:
    python scripts/backfill_zona_poligono.py --dry-run
    python scripts/backfill_zona_poligono.py                 # only unresolved rows
    python scripts/backfill_zona_poligono.py --all           # re-resolve every row
    python scripts/backfill_zona_poligono.py --incluir-inactivas

Options:
    --dry-run             Show what would change, write nothing.
    --all                 Re-resolve every property with coords, not just the
                          ones whose zona_poligono_id is currently NULL.
    --incluir-inactivas   Include activa = False properties.
    --limit N             Process at most N properties.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import ZonaPoligonoCRUD, engine
from db.models import Propiedad

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", dest="reresolve_all", action="store_true")
    parser.add_argument("--incluir-inactivas", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    with Session(engine) as session:
        poligonos = ZonaPoligonoCRUD.listar(session)
        if not poligonos:
            logger.info("No hay polígonos activos en app_zona_poligono. Nada que hacer.")
            return
        logger.info("%d polígono(s) activo(s): %s", len(poligonos),
                    ", ".join(z.nombre for z in poligonos))

        stmt = (
            select(Propiedad)
            .where(Propiedad.latitud != None)  # noqa: E711
            .where(Propiedad.longitud != None)  # noqa: E711
        )
        if not args.incluir_inactivas:
            stmt = stmt.where(Propiedad.activa == True)  # noqa: E712
        if not args.reresolve_all:
            stmt = stmt.where(Propiedad.zona_poligono_id == None)  # noqa: E711
        stmt = stmt.order_by(Propiedad.id)

        propiedades = list(session.exec(stmt).all())
        if args.limit:
            propiedades = propiedades[: args.limit]

        if not propiedades:
            logger.info("No hay propiedades que resolver.")
            return

        logger.info("%d propiedad(es) a evaluar%s", len(propiedades),
                    " — DRY RUN" if args.dry_run else "")

        cambios = {"asignadas": 0, "reasignadas": 0, "sin_zona": 0, "sin_cambio": 0}
        for prop in propiedades:
            nuevo = ZonaPoligonoCRUD.resolver_id(prop.latitud, prop.longitud, poligonos)
            actual = prop.zona_poligono_id
            if nuevo == actual:
                cambios["sin_cambio"] += 1
                continue
            if nuevo is None:
                cambios["sin_zona"] += 1
            elif actual is None:
                cambios["asignadas"] += 1
            else:
                cambios["reasignadas"] += 1
            logger.info("  ID %s: %s -> %s", prop.id, actual, nuevo)
            if not args.dry_run:
                prop.zona_poligono_id = nuevo
                session.add(prop)
                session.commit()

        logger.info(
            "Resumen: asignadas=%d, reasignadas=%d, sin_zona=%d, sin_cambio=%d%s",
            cambios["asignadas"], cambios["reasignadas"], cambios["sin_zona"],
            cambios["sin_cambio"], " — DRY RUN, nada escrito" if args.dry_run else "",
        )


if __name__ == "__main__":
    main()

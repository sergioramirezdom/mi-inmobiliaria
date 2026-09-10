#!/usr/bin/env python3
"""Backfill map coordinates for existing properties (one-off script).

Re-fetches the detail page of active properties that have no `latitud`
stored yet, for the sources whose scrapers can extract a map point, and
writes ONLY the location fields:

  * ``Propiedad.latitud`` / ``Propiedad.longitud``
  * a row in ``app_ubicacion_aproximada`` when the point is approximate
    (exact points leave that table untouched)

No other property field is touched.

Usage:

    python scripts/backfill_coordenadas.py --dry-run
    python scripts/backfill_coordenadas.py --source neopolis --limit 20
    python scripts/backfill_coordenadas.py                     # all sources, live

Options:
    --dry-run        Show what would change, write nothing.
    --source KEY     Restrict to one source (see SOURCES keys below, or the
                     full origen_web domain).
    --limit N        Process at most N properties.
    --sleep SECONDS  Delay between detail requests (default 1.0).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine, UbicacionAproximadaCRUD
from db.models import Propiedad
from scraper.config import ScraperConfig
from scraper.alonsaga_scraper import AlonsagaScraper
from scraper.jimenezruiz_scraper import JimenezRuizScraper
from scraper.neopolis_scraper import NeopolisScraper
from scraper.puerto_inmobiliaria import PuertoInmobiliariaScraper
from scraper.puertopiso_scraper import PuertoPisoScraper
from scraper.punto_hogar_scraper import PuntoHogarScraper
from scraper.samper_scraper import SamperScraper
from scraper.tular_scraper import TularScraper
from scraper.uriahomes_scraper import UriaHomesScraper

# origen_web domain -> (short key, detail scraper class)
SOURCES = {
    "www.uriahomesinmobiliaria.com": ("uriahomes", UriaHomesScraper),
    "www.alonsaga.com": ("alonsaga", AlonsagaScraper),
    "www.neopolis.es": ("neopolis", NeopolisScraper),
    "www.puertoinmobiliaria.es": ("puertoinmobiliaria", PuertoInmobiliariaScraper),
    "www.puertopiso.com": ("puertopiso", PuertoPisoScraper),
    "www.puntohogarinmobiliaria.com": ("puntohogar", PuntoHogarScraper),
    "www.jimenezruiz.com": ("jimenezruiz", JimenezRuizScraper),
    "www.sampergestionesinmobiliarias.es": ("samper", SamperScraper),
    "www.tular.es": ("tular", TularScraper),
}

_KEY_TO_DOMAIN = {key: domain for domain, (key, _) in SOURCES.items()}


def _resolve_domains(source_arg: str | None) -> list[str]:
    if not source_arg:
        return list(SOURCES)
    if source_arg in SOURCES:
        return [source_arg]
    if source_arg in _KEY_TO_DOMAIN:
        return [_KEY_TO_DOMAIN[source_arg]]
    raise SystemExit(
        f"Fuente desconocida: {source_arg!r}. "
        f"Opciones: {', '.join(sorted(_KEY_TO_DOMAIN))}"
    )


async def _extract_coords(
    scraper, url: str
) -> tuple[float | None, float | None, bool, int]:
    """Return (lat, lng, aproximada, radio_m) from a fresh detail scrape."""
    details = await scraper.scrape_property_details(url)
    return (
        details.get("latitud"),
        details.get("longitud"),
        bool(details.get("ubicacion_aproximada")),
        int(details.get("radio_m") or 300),
    )


async def _run(args: argparse.Namespace) -> None:
    domains = _resolve_domains(args.source)
    config = ScraperConfig()
    scrapers = {d: SOURCES[d][1](config) for d in domains}

    with Session(engine) as session:
        stmt = (
            select(Propiedad)
            .where(Propiedad.activa == True)  # noqa: E712
            .where(Propiedad.latitud == None)  # noqa: E711
            .where(Propiedad.origen_web.in_(domains))
            .order_by(Propiedad.id)
        )
        pending = session.exec(stmt).all()
        if args.limit:
            pending = pending[: args.limit]

        if not pending:
            print("No hay propiedades pendientes de coordenadas.")
            return

        print(
            f"{len(pending)} propiedad(es) sin coordenadas "
            f"({', '.join(SOURCES[d][0] for d in domains)})"
            + (" — DRY RUN" if args.dry_run else "")
        )

        stats = {"actualizadas": 0, "aproximadas": 0, "sin_coords": 0, "errores": 0}

        for prop in pending:
            scraper = scrapers[prop.origen_web]
            try:
                lat, lng, aproximada, radio_m = await _extract_coords(
                    scraper, prop.url_original
                )
            except Exception as e:
                stats["errores"] += 1
                print(f"  ✗ ID {prop.id} ({prop.origen_web}): {e}")
                continue
            finally:
                await asyncio.sleep(args.sleep)

            if lat is None or lng is None:
                stats["sin_coords"] += 1
                print(f"  – ID {prop.id}: sin coordenadas en la ficha")
                continue

            tag = f"aproximada r={radio_m}m" if aproximada else "exacta"
            print(f"  ✓ ID {prop.id}: {lat}, {lng} ({tag})")
            stats["actualizadas"] += 1
            if aproximada:
                stats["aproximadas"] += 1

            if args.dry_run:
                continue

            prop.latitud = lat
            prop.longitud = lng
            session.add(prop)
            session.commit()
            if aproximada:
                UbicacionAproximadaCRUD.marcar_aproximada(session, prop.id, radio_m)

        print(
            "\nResumen: "
            f"actualizadas={stats['actualizadas']} "
            f"(aproximadas={stats['aproximadas']}), "
            f"sin_coords={stats['sin_coords']}, errores={stats['errores']}"
            + (" — DRY RUN, nada escrito" if args.dry_run else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=1.0)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

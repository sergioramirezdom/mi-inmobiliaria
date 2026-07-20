#!/usr/bin/env python3
"""Rellena zona_normalizada en las propiedades ya existentes.

Por defecto es dry-run: informa sin escribir. Con --apply escribe, y SOLO
los match de confianza 'exacta'. Los 'via' y 'debil' se dejan vacíos a
propósito: aparecen como sugerencias en la página de Revisión.

Reejecutable sin efectos secundarios: como Propiedad.barrio nunca se
modifica, se puede relanzar tantas veces como se amplíe el catálogo.

  python scripts/backfill_zonas.py            # dry-run
  python scripts/backfill_zonas.py --apply    # escribe
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad
from scraper.zona_normalizer import CONFIANZA_EXACTA, normalizar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Escribe en la BD. Sin este flag solo informa.",
    )
    args = parser.parse_args()

    reparto = Counter()
    escritas = 0

    with Session(engine) as session:
        propiedades = session.exec(
            select(Propiedad).where(Propiedad.zona_normalizada == None)  # noqa: E711
        ).all()

        for p in propiedades:
            m = normalizar(
                barrio=p.barrio, direccion=p.direccion, titulo=p.titulo,
                descripcion=p.descripcion, url=p.url_original,
            )
            reparto[m.confianza or "sin match"] += 1

            if args.apply and m.confianza == CONFIANZA_EXACTA:
                p.zona_normalizada = m.zona
                p.zona_confianza = m.confianza
                session.add(p)
                escritas += 1

        if args.apply:
            session.commit()

    print(f"Propiedades sin zona     : {len(propiedades)}")
    for confianza in ("exacta", "via", "debil", "sin match"):
        print(f"  {confianza:<10}: {reparto[confianza]}")

    if args.apply:
        print(f"\n✓ Escritas {escritas} propiedades (solo confianza 'exacta')")
        print("  Las de confianza 'via' y 'debil' esperan en la página Revisión.")
    else:
        print("\nDRY-RUN: no se ha escrito nada. Usa --apply para confirmar.")


if __name__ == "__main__":
    main()

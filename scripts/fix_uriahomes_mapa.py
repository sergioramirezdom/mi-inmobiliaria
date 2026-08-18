#!/usr/bin/env python3
"""Corrige las propiedades UriaHomes que tienen "mapa"/"map" añadido
al campo `barrio` (one-time script).

Ejecutable de una sola vez:

    python scripts/fix_uriahomes_mapa.py
"""

import re
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import or_
from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad


_MAPA_RE = re.compile(r"\s*mapa?\s*$", re.IGNORECASE)


def main() -> None:
    with Session(engine) as session:
        properties = session.exec(
            select(Propiedad).where(
                or_(
                    Propiedad.barrio.ilike("%mapa"),
                    Propiedad.barrio.ilike("%map"),
                )
            )
        ).all()

        if not properties:
            print("No se encontraron propiedades con 'mapa'/'map' en barrio.")
            return

        print(f"Encontradas {len(properties)} propiedades para corregir:")
        fixed = 0
        for prop in properties:
            barrio = prop.barrio
            if not barrio:
                continue
            new_barrio = _MAPA_RE.sub("", barrio).strip()
            if new_barrio == barrio:
                continue
            print(f"  ID {prop.id}: '{barrio}' -> '{new_barrio}'")
            prop.barrio = new_barrio
            session.add(prop)
            fixed += 1

        if fixed == 0:
            print("Nada que corregir.")
            return

        session.commit()
        print(f"\n✅ Commit realizado. {fixed} propiedades actualizadas.")

        # Verify
        verify = session.exec(
            select(Propiedad).where(
                or_(
                    Propiedad.barrio.ilike("%mapa"),
                    Propiedad.barrio.ilike("%map"),
                )
            )
        ).all()
        if verify:
            print(f"⚠️  Todavía hay {len(verify)} propiedades con 'mapa'/'map' en barrio:")
            for p in verify:
                print(f"  ID {p.id}: '{p.barrio}'")
        else:
            print("✅ Verificación OK: no quedan propiedades con 'mapa'/'map' en barrio.")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Corrige las propiedades UriaHomes que tienen "mapa"/"map" añadido
al final del campo `direccion` (one-time script).

Ejecutable de una sola vez:

    python scripts/fix_uriahomes_mapa.py

Para cada propiedad que cumpla, se recorta el sufijo "mapa"/"map"
al final de `direccion` (sin distinción de mayúsculas/minúsculas) y
se actualiza el registro.
"""

import re
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import or_
from sqlmodel import Session, select

from db.database import PropiedadCRUD, engine
from db.models import Propiedad


def find_properties(session: Session):
    """Devuelve las propiedades cuya direccion termina en 'mapa' o 'map'."""
    return session.exec(
        select(Propiedad).where(
            or_(
                Propiedad.direccion.ilike("%mapa"),
                Propiedad.direccion.ilike("%map"),
                Propiedad.direccion.ilike("%mapa %"),
                Propiedad.direccion.ilike("%map %"),
            )
        )
    ).all()


def main() -> None:
    with Session(engine) as session:
        # Find properties with 'mapa'/'map' in direccion
        properties = session.exec(
            select(Propiedad).where(
                or_(
                    Propiedad.direccion.ilike("%mapa"),
                    Propiedad.direccion.ilike("%map"),
                )
            )
        ).all()

        if not properties:
            print("No se encontraron propiedades con 'mapa'/'map' en la direccion.")
            return

        print(f"Encontradas {len(properties)} propiedades para corregir:")
        fixed = 0
        for prop in properties:
            direccion = prop.direccion
            if not direccion:
                continue
            new_direccion = re.sub(
                r"\s*mapa?\s*$", "", direccion, flags=re.IGNORECASE
            ).strip()
            if new_direccion == direccion:
                continue
            print(f"  ID {prop.id}: '{direccion}' -> '{new_direccion}'")
            prop.direccion = new_direccion
            session.add(prop)
            fixed += 1

        if fixed == 0:
            print("Nada que corregir.")
            return

        session.commit()
        print(f"\n✅ Commit realizado. {fixed} propiedades actualizadas.")

        # Verify by re-querying
        verify = session.exec(
            select(Propiedad).where(
                or_(
                    Propiedad.direccion.ilike("%mapa"),
                    Propiedad.direccion.ilike("%map"),
                )
            )
        ).all()
        if verify:
            print(f"⚠️  Todavía hay {len(verify)} propiedades con 'mapa'/'map':")
            for p in verify:
                print(f"  ID {p.id}: '{p.direccion}'")
        else:
            print("✅ Verificación OK: no quedan propiedades con 'mapa'/'map'.")


if __name__ == "__main__":
    main()
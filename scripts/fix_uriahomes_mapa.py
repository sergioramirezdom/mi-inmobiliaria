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
        properties = find_properties(session)

        if not properties:
            print("No se encontraron propiedades con 'mapa'/'map' al final de la direccion.")
            return

        fixed = []
        for prop in properties:
            direccion = prop.direccion
            if not direccion:
                continue
            new_direccion = re.sub(
                r"\s*mapa?\s*$", "", direccion, flags=re.IGNORECASE
            )
            if new_direccion == direccion:
                continue
            PropiedadCRUD.update(session, prop.id, direccion=new_direccion)
            fixed.append((prop.id, direccion, new_direccion))

        print(f"Se corrigieron {len(fixed)} propiedades:")
        for prop_id, old, new in fixed:
            print(f"  ID {prop_id}: '{old}' -> '{new}'")


if __name__ == "__main__":
    main()
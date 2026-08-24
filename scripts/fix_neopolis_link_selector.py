#!/usr/bin/env python3
"""Corrige la Fuente NEOPOLIS ya creada: `notas.selectors.link_href_contains`
se guardó como "/ficha/" (con barra inicial), pero los hrefs reales del
listado son relativos sin barra inicial ("ficha/piso/..."), por lo que el
scraper encontraba 0 propiedades (one-time script).

Ejecutable de una sola vez:

    python scripts/fix_neopolis_link_selector.py
"""

import json
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Fuente

OLD_VALUE = "/ficha/"
NEW_VALUE = "ficha/"


def main() -> None:
    with Session(engine) as session:
        fuente = session.exec(
            select(Fuente).where(Fuente.nombre == "NEOPOLIS")
        ).first()

        if not fuente:
            print("No se encontró ninguna Fuente llamada NEOPOLIS. Nada que corregir.")
            return

        notas = json.loads(fuente.notas or "{}")
        current = notas.get("selectors", {}).get("link_href_contains")

        if current == NEW_VALUE:
            print(f"Fuente NEOPOLIS (ID {fuente.id}) ya tiene el selector correcto. Nada que hacer.")
            return

        if current != OLD_VALUE:
            print(
                f"⚠️  Fuente NEOPOLIS (ID {fuente.id}) tiene un valor inesperado "
                f"('{current}'), no '{OLD_VALUE}'. No se modifica automáticamente; revisa a mano."
            )
            return

        notas.setdefault("selectors", {})["link_href_contains"] = NEW_VALUE
        fuente.notas = json.dumps(notas)
        session.add(fuente)
        session.commit()

        print(
            f"✅ Fuente NEOPOLIS (ID {fuente.id}) corregida: "
            f"link_href_contains '{OLD_VALUE}' -> '{NEW_VALUE}'."
        )


if __name__ == "__main__":
    main()

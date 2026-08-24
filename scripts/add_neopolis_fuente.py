#!/usr/bin/env python3
"""Registra la fuente NEOPOLIS en la base de datos (one-time script).

Ejecutable de una sola vez:

    python scripts/add_neopolis_fuente.py

Si la fuente ya existe (se comprueba por URL) no se duplica: imprime un
mensaje y termina sin escribir nada.

La fuente se crea con `activa=False`: el usuario la activa manualmente tras
verificar un ciclo con `python scripts/scheduler.py --once --force`.
"""

import json
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Fuente

# URL exacta del buscador de NEOPOLIS (Venta, El Puerto de Santa María).
# Almacenada verbatim: no decodificar ni normalizar limtipos=/areas=.
NEOPOLIS_URL = (
    "https://www.neopolis.es/index.php?limtipos=6599,599,699,6899,899,7099,7599,3699,"
    "11699,4599,11899,21299,5999,6099,6299,999,4999,6199,6499,7499,199,299,20599,399,"
    "21199,499,799,2799,10299,2899,2999,3099,3299,3399,3499,3599,4399,4699,4899"
    "&areas=9985_id,9984_id,9981_id,8469_id,102134_id,8468_id,9980_id,102134_id"
    "&buscador=1&idio=1"
)

# Configuración ScraperConfig-compatible almacenada en el campo notas.
# use_results_per_page=False: solo la paginación pag=N se verificó en vivo
# (Fase 0); &res=N nunca fue probado y podría truncar u obtener un 500.
NOTAS_CONFIG = {
    "selectors": {"link_href_contains": "/ficha/"},
    "detail_scraper_type": "neopolis",
    "pagination_param": "pag",
    "pagination_start": 1,
    "pagination_skip_first": False,
    "use_results_per_page": False,
    "max_pages": 10,
    "timeout": 120,
    "retries": 2,
    "verify_ssl": True,
}


def main() -> None:
    with Session(engine) as session:
        # Handle the case where the Fuente already exists (check by URL)
        existing = session.exec(
            select(Fuente).where(Fuente.url == NEOPOLIS_URL)
        ).first()

        if existing:
            print(
                f"La fuente NEOPOLIS ya existe (ID {existing.id}). "
                "No se ha creado nada."
            )
            return

        fuente = Fuente(
            nombre="NEOPOLIS",
            url=NEOPOLIS_URL,
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas=json.dumps(NOTAS_CONFIG),
        )

        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        print(
            f"Fuente NEOPOLIS registrada correctamente (ID {fuente.id}), "
            "inactiva (activa=False)."
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Registra la fuente UriaHomes en la base de datos (one-time script).

Ejecutable de una sola vez:

    python scripts/add_uriahomes_fuente.py

Si la fuente ya existe (se comprueba por URL) no se duplica: imprime un
mensaje y termina sin escribir nada.
"""

import json
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Fuente

# URL exacta del buscador de UriaHomes (Venta, El Puerto de Santa María, Cádiz)
URIAHOMES_URL = (
    "https://www.uriahomesinmobiliaria.com/buscar.php?br=&o=Venta"
    "&check_tipo_inmueble%5B%5D=&p=C%C3%A1diz"
    "&po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa"
    "&check_zona%5B%5D=&md=&pd=&ph=&or=id2&vista=listado"
)

# Configuración ScraperConfig-compatible almacenada en el campo notas
NOTAS_CONFIG = {
    "selectors": {
        "property_container": ".listado5_contendor_inmueble",
        "link": "a.listado5_contendor_inmueble_datos",
        "title": ".listado5_contendor_inmueble_datos_titulo",
        "description": ".listado5_contendor_inmueble_datos_descripcion",
    },
    "pagination_param": "pag",
    "pagination_start": 1,
    "pagination_skip_first": False,
    "use_results_per_page": False,
    "detail_scraper_type": "uriahomes",
    "municipio_filter": "El Puerto de Santa María",
}


def main() -> None:
    with Session(engine) as session:
        # Handle the case where the Fuente already exists (check by URL)
        existing = session.exec(
            select(Fuente).where(Fuente.url == URIAHOMES_URL)
        ).first()

        if existing:
            print(
                f"La fuente UriaHomes ya existe (ID {existing.id}). "
                "No se ha creado nada."
            )
            return

        fuente = Fuente(
            nombre="UriaHomes",
            url=URIAHOMES_URL,
            tipo_scraper="generic",
            activa=True,
            intervalo_horas=24,
            notas=json.dumps(NOTAS_CONFIG),
        )

        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        print(f"Fuente UriaHomes registrada correctamente (ID {fuente.id}).")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Registra la fuente SAMPER Gestiones Inmobiliarias en la base de datos (one-time script).

Ejecutable de una sola vez:

    python scripts/add_samper_fuente.py

Se crea con `activa=False`: el operador la activa manualmente desde la UI
tras revisar un dry run (`python scripts/scheduler.py --once --force`).

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

# URL exacta del buscador de SAMPER (Venta, El Puerto de Santa María)
SAMPER_URL = (
    "https://www.sampergestionesinmobiliarias.es/buscar.php?br=&o=Venta"
    "&check_tipo_inmueble%5B%5D=&p="
    "&po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa"
    "&check_zona%5B%5D=&md=&pd=&ph=&or=ed2&vista=listado"
)

# Configuración ScraperConfig-compatible almacenada en el campo notas
# (debe coincidir con SCRAPER_CONFIG_TEMPLATES["samper"] en app/pages/1_fuentes.py)
NOTAS_CONFIG = {
    "detail_scraper_type": "samper",
    # Sin municipio_filter: la config solo usa link_href_contains (sin
    # selector de title), por lo que GenericScraper nunca extrae un título
    # real en el listado y cae siempre en "Sin título" — con municipio_filter
    # activo eso descarta el 100% de los resultados antes de pedir el detalle.
    # La URL ya filtra por El Puerto de Santa María en servidor (po[]=...).
    "max_pages": 1,
    "pagination_param": "pag",
    "pagination_start": 1,
    "pagination_skip_first": True,
    "use_results_per_page": False,
    "selectors": {"link_href_contains": "/Venta-"},
}


def main() -> None:
    with Session(engine) as session:
        existing = session.exec(select(Fuente).where(Fuente.url == SAMPER_URL)).first()

        if existing:
            print(
                f"La fuente SAMPER ya existe (ID {existing.id}). "
                "No se ha creado nada."
            )
            return

        fuente = Fuente(
            nombre="SAMPER Gestiones Inmobiliarias",
            url=SAMPER_URL,
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas=json.dumps(NOTAS_CONFIG, ensure_ascii=False),
        )

        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        print(
            f"Fuente SAMPER registrada correctamente (ID {fuente.id}), activa=False. "
            "Actívala manualmente desde la UI tras revisar un dry run."
        )


if __name__ == "__main__":
    main()

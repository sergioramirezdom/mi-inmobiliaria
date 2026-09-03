#!/usr/bin/env python3
"""Registra la fuente Tular Inmobiliaria (tular.es) en la base de datos (one-time script).

Ejecutable de una sola vez:

    python scripts/add_tular_fuente.py

Se crea con `activa=False`: el operador la activa manualmente desde la UI
tras revisar un dry run ("Scraping Completo" sobre la fuente Tular).

Si la fuente ya existe (se comprueba por URL) no se duplica: imprime un
mensaje y termina sin escribir nada.

NOTA: este script NO se ejecuta durante `apply` (no hay `DATABASE_URL`).
"""

import json
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Fuente

# URL exacta del buscador de Tular (Venta + Vivienda + El Puerto de Santa María).
TULAR_URL = (
    "https://www.tular.es/buscar.php?br=&o=Venta"
    "&check_tipo_inmueble%5B%5D=Vivienda"
    "&p=C%C3%A1diz"
    "&po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa"
    "&check_zona%5B%5D=&md=&pd=0&ph=0&or=id2"
)

# Configuración ScraperConfig-compatible almacenada en el campo notas.
# DEBE coincidir byte a byte con SCRAPER_CONFIG_TEMPLATES["tular"] en
# app/pages/1_fuentes.py. SIN municipio_filter (ref bug #43): en modo
# link_href_contains el título del listado es siempre un placeholder que
# nunca casa con el filtro, así que descartaría el 100% de los resultados
# antes del scraper de detalle. La URL ya filtra por El Puerto + Vivienda
# en servidor y TularScraper fija municipio="El Puerto de Santa María".
NOTAS_CONFIG = {
    "detail_scraper_type": "tular",
    "max_pages": 1,
    "pagination_param": "pag",
    "pagination_start": 1,
    "pagination_skip_first": True,
    "use_results_per_page": False,
    "selectors": {"link_href_contains": "/Venta-"},
}


def main() -> None:
    with Session(engine) as session:
        existing = session.exec(select(Fuente).where(Fuente.url == TULAR_URL)).first()

        if existing:
            print(
                f"La fuente Tular ya existe (ID {existing.id}). No se ha creado nada."
            )
            return

        fuente = Fuente(
            nombre="Tular",
            url=TULAR_URL,
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas=json.dumps(NOTAS_CONFIG, ensure_ascii=False),
        )

        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        print(
            f"Fuente Tular registrada correctamente (ID {fuente.id}), activa=False. "
            "Actívala manualmente desde la UI tras revisar un dry run."
        )


if __name__ == "__main__":
    main()

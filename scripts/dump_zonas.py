#!/usr/bin/env python3
"""Vuelca los valores de barrio existentes, con frecuencia, a un CSV.

SOLO LECTURA: no modifica la base de datos.

El CSV resultante es el material con el que se construye el catálogo
zonas_elpuerto.yaml. Columnas:
  barrio_crudo, veces, zona_actual, confianza_actual, ejemplo_url
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad
from scraper.zona_normalizer import normalizar

SALIDA = Path(__file__).parent.parent / "docs" / "superpowers" / "zonas_actuales.csv"

SIN_BARRIO = "(vacío)"


def main() -> None:
    with Session(engine) as session:
        propiedades = session.exec(select(Propiedad)).all()

    conteo = Counter()
    ejemplo = {}
    for p in propiedades:
        clave = (p.barrio or "").strip() or SIN_BARRIO
        conteo[clave] += 1
        ejemplo.setdefault(clave, p)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        escritor = csv.writer(fh)
        escritor.writerow([
            "barrio_crudo", "veces", "zona_actual", "confianza_actual", "ejemplo_url",
        ])
        for clave, veces in conteo.most_common():
            p = ejemplo[clave]
            m = normalizar(
                barrio=p.barrio, direccion=p.direccion, titulo=p.titulo,
                descripcion=p.descripcion, url=p.url_original,
            )
            escritor.writerow([
                clave, veces, m.zona or "", m.confianza or "", p.url_original,
            ])

    sin_match = sum(v for k, v in conteo.items()
                    if normalizar(barrio=ejemplo[k].barrio).zona is None)
    print(f"Propiedades analizadas : {len(propiedades)}")
    print(f"Valores distintos      : {len(conteo)}")
    print(f"Sin zona por 'barrio'  : {sin_match}")
    print(f"CSV escrito en         : {SALIDA}")


if __name__ == "__main__":
    main()

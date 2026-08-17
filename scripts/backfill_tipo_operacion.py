#!/usr/bin/env python3
"""Backfill tipo_operacion para propiedades existentes.

Analiza título, precio y URL para determinar si cada propiedad
es venta o alquiler. Idempotente: solo actualiza donde tipo_operacion IS NULL.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select
from db.database import engine
from db.models import Propiedad
from scraper.operacion_detector import detectar_operacion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    with Session(engine) as session:
        props = session.exec(
            select(Propiedad).where(Propiedad.tipo_operacion == None)
        ).all()

        logger.info(f"Propiedades sin tipo_operacion: {len(props)}")

        ventas = 0
        alquileres = 0
        unknows = 0

        for p in props:
            operacion = detectar_operacion(
                titulo=p.titulo, precio=p.precio,
                url=p.url_original, descripcion=p.descripcion,
            )
            if operacion:
                p.tipo_operacion = operacion
                session.add(p)
                if operacion == "venta":
                    ventas += 1
                else:
                    alquileres += 1
            else:
                # Default to "venta" for existing properties
                p.tipo_operacion = "venta"
                session.add(p)
                unknows += 1

        session.commit()
        logger.info(f"✅ Backfill completado:")
        logger.info(f"   Ventas: {ventas}")
        logger.info(f"   Alquileres detectados: {alquileres}")
        logger.info(f"   Marcadas como venta (por defecto): {unknows}")

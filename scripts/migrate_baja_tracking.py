#!/usr/bin/env python3
"""Añade las columnas estado_baja y ultimo_strike a propiedad.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
Ambas columnas son nullable y sin default, así que Postgres no reescribe
la tabla (no hay downtime en Neon). La tabla también la lee la app de
Vercel, por lo que la migración es aditiva pura: sin rename, sin cambio
de tipo, sin drop, sin NOT NULL.

  estado_baja   motivo de la baja (Vendida / Reservada / No disponible);
                deja de sobrescribirse `estado`, que es el estado del inmueble.
  ultimo_strike cuándo se contó el último strike de sold-check, para que los
                strikes se separen en el tiempo.

Debe aplicarse ANTES de desplegar el código que lee/escribe las columnas
(SQLModel las incluye en cada SELECT de Propiedad).
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import text
from db.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENTENCIAS = [
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS estado_baja VARCHAR",
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS ultimo_strike TIMESTAMP",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")

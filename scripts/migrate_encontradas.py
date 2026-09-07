#!/usr/bin/env python3
"""Añade la columna encontradas a registroejecucion.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
La columna es nullable y sin default, así que Postgres no reescribe
la tabla (no hay downtime en Neon). La tabla también la lee la app
de Vercel, por lo que la migración es aditiva pura: sin rename, sin
cambio de tipo, sin drop, sin NOT NULL.
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
    "ALTER TABLE registroejecucion ADD COLUMN IF NOT EXISTS encontradas INTEGER",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")

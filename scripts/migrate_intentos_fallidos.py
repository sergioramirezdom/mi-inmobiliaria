#!/usr/bin/env python3
"""Añade la columna intentos_fallidos a propiedad.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
La columna es nullable con default 0, así que Postgres no reescribe
la tabla (no hay downtime en Neon).
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
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS intentos_fallidos INTEGER DEFAULT 0",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")

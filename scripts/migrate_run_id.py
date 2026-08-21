#!/usr/bin/env python3
"""Añade la columna run_id a registroejecucion.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
La columna es nullable y sin default, así que Postgres no reescribe
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
    "ALTER TABLE registroejecucion ADD COLUMN IF NOT EXISTS run_id VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_registroejecucion_run_id "
    "ON registroejecucion (run_id)",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")

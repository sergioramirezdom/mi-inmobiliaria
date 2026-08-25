#!/usr/bin/env python3
"""Añade la columna excluir_de_estadisticas a propiedad.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
La columna es nullable con default False, así que Postgres no reescribe
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
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS excluir_de_estadisticas BOOLEAN DEFAULT FALSE",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")

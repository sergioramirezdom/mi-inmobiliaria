#!/usr/bin/env python3
"""Añade la columna tipo_alerta a filtroalerta.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
La columna es additive-nullable con DEFAULT 'nuevas', así que Postgres no
reescribe la tabla (no hay downtime en Neon). Las filas existentes se leen
como 'nuevas', preservando el comportamiento actual.

DEBE ejecutarse ANTES de desplegar el código de PR2 (el modelo ya declara
el campo en cuanto el código llega).
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
    "ALTER TABLE filtroalerta ADD COLUMN IF NOT EXISTS tipo_alerta VARCHAR "
    "DEFAULT 'nuevas'",
    "UPDATE filtroalerta SET tipo_alerta = 'nuevas' WHERE tipo_alerta IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_filtroalerta_tipo_alerta "
    "ON filtroalerta (tipo_alerta)",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(f"Executing: {sql}")
            conn.execute(text(sql))
    logger.info("✅ Migración tipo_alerta completada")

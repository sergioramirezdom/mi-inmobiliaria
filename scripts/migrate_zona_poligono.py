#!/usr/bin/env python3
"""Crea la tabla app_zona_poligono y añade propiedad.zona_poligono_id.

Idempotente: se puede ejecutar varias veces sin efecto adicional.

- app_zona_poligono: polígonos con nombre dibujados desde el desarrollo web
  (geometria = GeoJSON Polygon/MultiPolygon en columna JSON).
- propiedad.zona_poligono_id: FK nullable, sin default, así que Postgres no
  reescribe la tabla (sin downtime en Neon). La FK se añade sobre una columna
  todo-NULL, operación instantánea.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import text

from db.database import engine
from db.models import ZonaPoligono

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENTENCIAS = [
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS zona_poligono_id INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_propiedad_zona_poligono_id "
    "ON propiedad (zona_poligono_id)",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_propiedad_zona_poligono'
        ) THEN
            ALTER TABLE propiedad
                ADD CONSTRAINT fk_propiedad_zona_poligono
                FOREIGN KEY (zona_poligono_id)
                REFERENCES app_zona_poligono (id)
                ON DELETE SET NULL;
        END IF;
    END $$;
    """,
]


if __name__ == "__main__":
    # 1. Create app_zona_poligono from the model (checkfirst -> idempotent).
    logger.info("CREATE TABLE app_zona_poligono (si no existe)")
    ZonaPoligono.__table__.create(bind=engine, checkfirst=True)

    # 2. Add the resolved-zona column + index + FK on propiedad.
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql.strip().splitlines()[0])
            conn.execute(text(sql))

    logger.info("✓ Migración completada")

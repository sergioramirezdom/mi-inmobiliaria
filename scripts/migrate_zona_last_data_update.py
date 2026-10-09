#!/usr/bin/env python3
"""Añade last_data_update (periodo de datos) a estadisticazonanotarial.

Pasos, en una sola transacción:
1. ADD COLUMN nullable + índice ix_estadisticazonanotarial_last_data_update.
2. Backfill de las filas existentes con el periodo general vigente en el
   momento de la captura: MAX(estadisticanotarial.last_data_update) de las
   filas creadas antes o en el mismo instante que captured_at. Si no hay
   ninguna, se usa el mes de captura (misma regla de respaldo que el
   frontend) y esas filas se listan como aviso.
3. SET NOT NULL.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
Con --dry-run se ejecuta todo y se hace rollback al final.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import text  # noqa: E402
from db.database import engine  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ESQUEMA = [
    "ALTER TABLE estadisticazonanotarial "
    "ADD COLUMN IF NOT EXISTS last_data_update TIMESTAMP WITHOUT TIME ZONE",
    "CREATE INDEX IF NOT EXISTS ix_estadisticazonanotarial_last_data_update "
    "ON estadisticazonanotarial (last_data_update)",
]

BACKFILL = """
UPDATE estadisticazonanotarial AS z
SET last_data_update = COALESCE(
    (
        SELECT MAX(e.last_data_update)
        FROM estadisticanotarial AS e
        WHERE e.created_at <= z.captured_at
    ),
    date_trunc('month', z.captured_at)
)
WHERE z.last_data_update IS NULL
"""

SIN_PERIODO_GENERAL = """
SELECT z.id, z.zona, z.property_type, z.construction_type, z.captured_at
FROM estadisticazonanotarial AS z
WHERE z.last_data_update IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM estadisticanotarial AS e
      WHERE e.created_at <= z.captured_at
  )
ORDER BY z.captured_at
"""

NOT_NULL = (
    "ALTER TABLE estadisticazonanotarial "
    "ALTER COLUMN last_data_update SET NOT NULL"
)

RESUMEN = """
SELECT date_trunc('month', captured_at) AS mes_captura,
       last_data_update AS periodo,
       COUNT(*) AS filas
FROM estadisticazonanotarial
GROUP BY 1, 2
ORDER BY 1, 2
"""


def migrar(conn) -> None:
    """Run the migration on an open transaction."""
    for sql in ESQUEMA:
        logger.info(sql)
        conn.execute(text(sql))

    sin_periodo_general = conn.execute(text(SIN_PERIODO_GENERAL)).fetchall()
    if sin_periodo_general:
        logger.warning(
            "%s fila(s) sin periodo general previo; se usa el mes de captura:",
            len(sin_periodo_general),
        )
        for fila in sin_periodo_general:
            logger.warning("  %s", tuple(fila))

    actualizadas = conn.execute(text(BACKFILL)).rowcount
    logger.info("Backfill: %s fila(s) actualizada(s)", actualizadas)

    for mes, periodo, filas in conn.execute(text(RESUMEN)):
        logger.info("  captura %s -> periodo %s: %s fila(s)", mes, periodo, filas)

    logger.info(NOT_NULL)
    conn.execute(text(NOT_NULL))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecuta la migración y hace rollback al final",
    )
    args = parser.parse_args(argv)

    conn = engine.connect()
    trans = conn.begin()
    try:
        migrar(conn)
        if args.dry_run:
            trans.rollback()
            logger.info("Dry run: rollback, no se ha modificado nada")
        else:
            trans.commit()
            logger.info("✓ Migración completada")
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

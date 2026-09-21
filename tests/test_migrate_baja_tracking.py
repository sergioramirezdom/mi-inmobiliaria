"""Tests for the estado_baja / ultimo_strike migration script (issue #53).

Same shape as tests/test_migrate_encontradas.py: additive, idempotent
statements checked without a live DB (Propiedad has an ARRAY column SQLite
cannot render).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Propiedad  # noqa: E402


def test_migration_adds_both_columns_idempotently_and_nullable():
    sql_statements = __import__("migrate_baja_tracking").SENTENCIAS
    assert len(sql_statements) == 2
    joined = " ".join(sql_statements)
    assert "ADD COLUMN IF NOT EXISTS estado_baja" in joined
    assert "ADD COLUMN IF NOT EXISTS ultimo_strike TIMESTAMP" in joined
    for stmt in sql_statements:
        assert stmt.startswith("ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS")
        assert "NOT NULL" not in stmt.upper()
        assert "DROP" not in stmt.upper()


def test_model_declares_new_columns_as_optional():
    columns = Propiedad.__table__.columns
    for name in ("estado_baja", "ultimo_strike"):
        assert columns[name].nullable is True
        assert columns[name].default is None

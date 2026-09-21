"""Tests for the error_mensaje migration script (issue #50).

Same shape as tests/test_migrate_encontradas.py: a single idempotent
additive statement, checked without a live DB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import RegistroEjecucion  # noqa: E402


def test_migration_adds_nullable_error_mensaje_text_idempotently():
    sql_statements = __import__("migrate_error_mensaje").SENTENCIAS
    assert len(sql_statements) == 1
    stmt = sql_statements[0]
    assert "registroejecucion" in stmt
    assert "ADD COLUMN IF NOT EXISTS error_mensaje TEXT" in stmt
    assert "NOT NULL" not in stmt.upper()
    assert "DEFAULT" not in stmt.upper()


def test_model_declares_error_mensaje_as_optional():
    assert RegistroEjecucion(fuente_id=1, tipo="scrape").error_mensaje is None

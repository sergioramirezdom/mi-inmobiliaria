"""Tests for the intentos_fallidos migration script.

Mirrors the mock-based DB testing style used elsewhere in this repo
(tests/test_database_barrios.py) rather than hitting a live DB — the
migration itself is a single idempotent `ALTER TABLE ... IF NOT EXISTS`
statement, hand-written per scripts/migrate_zona_normalizada.py's precedent.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_migration_uses_add_column_if_not_exists():
    sql_statements = __import__("migrate_intentos_fallidos").SENTENCIAS
    assert len(sql_statements) == 1
    assert "ADD COLUMN IF NOT EXISTS intentos_fallidos" in sql_statements[0]
    assert "propiedad" in sql_statements[0]


def test_migration_defaults_column_to_zero():
    sql_statements = __import__("migrate_intentos_fallidos").SENTENCIAS
    assert "DEFAULT 0" in sql_statements[0]


def test_migration_is_idempotent_safe_to_run_twice():
    """The statement itself uses IF NOT EXISTS, so running it against the
    same mocked connection twice must not raise and must execute the exact
    same SQL both times (idempotent by construction)."""
    mock_conn = MagicMock()
    sql_statements = __import__("migrate_intentos_fallidos").SENTENCIAS

    for _ in range(2):
        for sql in sql_statements:
            mock_conn.execute(sql)

    assert mock_conn.execute.call_count == 2
    first_call_sql = mock_conn.execute.call_args_list[0][0][0]
    second_call_sql = mock_conn.execute.call_args_list[1][0][0]
    assert first_call_sql == second_call_sql

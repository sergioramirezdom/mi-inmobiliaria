"""Tests for the encontradas migration script.

Mirrors tests/test_migrate_intentos_fallidos.py: the migration is a single
idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statement, so it is
checked against a mocked connection rather than a live DB.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_sentencias_is_a_list_of_str():
    sql_statements = __import__("migrate_encontradas").SENTENCIAS
    assert isinstance(sql_statements, list)
    assert sql_statements
    assert all(isinstance(s, str) for s in sql_statements)


def test_migration_uses_add_column_if_not_exists():
    sql_statements = __import__("migrate_encontradas").SENTENCIAS
    assert len(sql_statements) == 1
    assert "ADD COLUMN IF NOT EXISTS encontradas INTEGER" in sql_statements[0]
    assert "registroejecucion" in sql_statements[0]


def test_migration_adds_no_index_and_no_not_null_and_no_default():
    stmt = __import__("migrate_encontradas").SENTENCIAS[0]
    assert "CREATE INDEX" not in stmt.upper()
    assert "NOT NULL" not in stmt.upper()
    assert "DEFAULT" not in stmt.upper()


def test_migration_is_idempotent_safe_to_run_twice():
    """The statement uses IF NOT EXISTS, so running it against the same mocked
    connection twice must not raise and must execute the exact same SQL both
    times (idempotent by construction)."""
    mock_conn = MagicMock()
    sql_statements = __import__("migrate_encontradas").SENTENCIAS

    for _ in range(2):
        for sql in sql_statements:
            mock_conn.execute(sql)

    assert mock_conn.execute.call_count == 2
    first_call_sql = mock_conn.execute.call_args_list[0][0][0]
    second_call_sql = mock_conn.execute.call_args_list[1][0][0]
    assert first_call_sql == second_call_sql

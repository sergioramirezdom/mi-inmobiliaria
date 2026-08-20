"""Tests for RegistroEjecucionCRUD (T6.3) — CRUD helper matching the existing
static-method style used by FuenteCRUD/PropiedadCRUD in app/db/database.py.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.database import RegistroEjecucionCRUD
from db.models import RegistroEjecucion


def test_create_adds_commits_refreshes_and_returns_registro():
    session = MagicMock()
    registro = RegistroEjecucion(
        fuente_id=1, tipo="sold_check", total=5, activas=4, vendidas=1,
        sin_datos=0, errores=0, duracion_segundos=1.2,
    )

    result = RegistroEjecucionCRUD.create(session, registro)

    session.add.assert_called_once_with(registro)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(registro)
    assert result is registro


def test_get_by_fuente_returns_rows_for_that_fuente():
    session = MagicMock()
    rows = [RegistroEjecucion(fuente_id=7, tipo="scrape", total=3)]
    session.exec.return_value.all.return_value = rows

    result = RegistroEjecucionCRUD.get_by_fuente(session, fuente_id=7)

    assert result == rows


def test_get_recent_returns_rows_across_fuentes():
    session = MagicMock()
    rows = [
        RegistroEjecucion(fuente_id=1, tipo="sold_check", total=7),
        RegistroEjecucion(fuente_id=2, tipo="scrape", total=4),
    ]
    session.exec.return_value.all.return_value = rows

    result = RegistroEjecucionCRUD.get_recent(session)

    assert result == rows

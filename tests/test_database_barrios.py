"""Tests for PropiedadCRUD.get_distinct_barrios."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.database import PropiedadCRUD


def _mock_session(barrio_rows):
    session = MagicMock()
    session.exec.return_value.all.return_value = barrio_rows
    return session


def test_get_distinct_barrios_dedupes_and_sorts_case_insensitive():
    session = _mock_session(["Valdelagrana", "crevillet", "Valdelagrana", "Vistahermosa"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["crevillet", "Valdelagrana", "Vistahermosa"]


def test_get_distinct_barrios_filters_none_and_blank():
    session = _mock_session(["Valdelagrana", None, "  ", "", "Crevillet"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["Crevillet", "Valdelagrana"]


def test_get_distinct_barrios_strips_whitespace():
    session = _mock_session(["  Valdelagrana  ", "Crevillet"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["Crevillet", "Valdelagrana"]


def test_get_distinct_barrios_empty_when_no_properties():
    session = _mock_session([])
    assert PropiedadCRUD.get_distinct_barrios(session) == []

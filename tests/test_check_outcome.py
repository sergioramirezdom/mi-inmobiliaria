"""Tests for the pure outcome classifier and the deactivation gate."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pytest

from scraper.check_outcome import (
    CheckOutcome,
    STRIKE_THRESHOLD,
    classify_check_outcome,
    apply_check_outcome,
)


# --- classify_check_outcome ---------------------------------------------

@pytest.mark.parametrize(
    "details,expected",
    [
        ({"activa": False}, CheckOutcome.GONE),
        ({"activa": False, "estado": "Reservada"}, CheckOutcome.GONE),
        ({}, CheckOutcome.EMPTY),
        ({"titulo": None, "precio": None}, CheckOutcome.EMPTY),
        ({"titulo": "Piso en venta"}, CheckOutcome.ALIVE),
        ({"activa": True}, CheckOutcome.ALIVE),
        ({"precio": 150000}, CheckOutcome.ALIVE),
    ],
)
def test_classify_check_outcome(details, expected):
    assert classify_check_outcome(details) == expected


def test_strike_threshold_is_two():
    assert STRIKE_THRESHOLD == 2


# --- apply_check_outcome --------------------------------------------------

def _make_prop(intentos_fallidos=0, activa=True):
    prop = MagicMock()
    prop.intentos_fallidos = intentos_fallidos
    prop.activa = activa
    prop.estado = None
    prop.fecha_baja = None
    return prop


def test_gone_on_strike_zero_deactivates_immediately():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=0, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.GONE, estado="No disponible")

    assert result == "deactivated"
    assert prop.activa is False
    assert prop.estado == "No disponible"
    assert prop.fecha_baja is not None
    assert prop.intentos_fallidos == 0
    session.add.assert_called_with(prop)
    session.commit.assert_called_once()


def test_empty_on_null_strike_counter_treated_as_zero_becomes_one():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=None, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert result == "strike"
    assert prop.intentos_fallidos == 1
    assert prop.activa is True
    assert prop.estado is None
    session.commit.assert_called_once()


def test_empty_on_strike_one_deactivates_and_resets_counter():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert result == "deactivated"
    assert prop.activa is False
    assert prop.intentos_fallidos == 0
    session.commit.assert_called_once()


def test_alive_with_strikes_resets_counter():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.ALIVE)

    assert result == "alive"
    assert prop.intentos_fallidos == 0
    assert prop.activa is True
    session.commit.assert_called_once()


def test_alive_with_zero_strikes_is_a_noop_write():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=0, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.ALIVE)

    assert result == "alive"
    assert prop.intentos_fallidos == 0
    session.commit.assert_not_called()


def test_error_outcome_makes_zero_db_writes():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.ERROR)

    assert result == "skipped"
    assert prop.intentos_fallidos == 1
    assert prop.activa is True
    session.add.assert_not_called()
    session.commit.assert_not_called()

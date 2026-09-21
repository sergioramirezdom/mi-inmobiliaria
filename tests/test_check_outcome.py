"""Tests for the pure outcome classifier and the deactivation gate."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from datetime import datetime, timedelta

import httpx
import pytest

from scraper.check_outcome import (
    CheckOutcome,
    STRIKE_MIN_INTERVAL,
    STRIKE_THRESHOLD,
    apply_check_outcome,
    classify_check_outcome,
    classify_fetch_error,
    reactivate,
    source_looks_broken,
)
from scraper.exceptions import ScraperException


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
    prop.estado_baja = None
    prop.ultimo_strike = None
    prop.fecha_baja = None
    return prop


def test_gone_on_strike_zero_deactivates_immediately():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=0, activa=True)

    result = apply_check_outcome(session, prop, CheckOutcome.GONE, estado="No disponible")

    assert result == "deactivated"
    assert prop.activa is False
    assert prop.estado_baja == "No disponible"
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


# --- classify_fetch_error (issue #53) ----------------------------------------

def _status_error(status, url="https://x.es/inmueble/14042"):
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"HTTP {status} for {url}", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.parametrize("status", [404, 410])
def test_gone_status_codes_classify_as_gone(status):
    assert classify_fetch_error(_status_error(status)) is CheckOutcome.GONE


@pytest.mark.parametrize("status", [403, 429, 500, 502, 503, 504])
def test_other_status_codes_are_errors_never_gone(status):
    assert classify_fetch_error(_status_error(status)) is CheckOutcome.ERROR


def test_503_whose_url_contains_404_is_an_error():
    # httpx embeds the URL in the message: "...inmueble/14042" contains "404".
    exc = _status_error(503, "https://x.es/inmueble/14042")
    assert "404" in str(exc)

    assert classify_fetch_error(exc) is CheckOutcome.ERROR


def test_timeout_and_network_errors_are_errors():
    request = httpx.Request("GET", "https://x.es/404")
    assert classify_fetch_error(httpx.ReadTimeout("timed out", request=request)) is CheckOutcome.ERROR
    assert classify_fetch_error(httpx.ConnectError("refused", request=request)) is CheckOutcome.ERROR


def test_text_that_merely_says_404_or_not_found_is_an_error():
    assert classify_fetch_error(Exception("404 Client Error: Not Found for url")) is CheckOutcome.ERROR


def _wrapped(status):
    """Scrapers re-raise the httpx error inside their own exception type."""
    try:
        try:
            raise _status_error(status)
        except httpx.HTTPStatusError as e:
            raise ScraperException(f"Failed to fetch: {e}")
    except ScraperException as wrapper:
        return wrapper


def test_wrapped_404_is_found_through_the_exception_chain():
    assert classify_fetch_error(_wrapped(404)) is CheckOutcome.GONE


def test_wrapped_503_is_an_error():
    assert classify_fetch_error(_wrapped(503)) is CheckOutcome.ERROR


# --- estado is preserved (issue #53) ------------------------------------------

def test_gone_records_estado_baja_and_preserves_the_building_condition():
    session = MagicMock()
    prop = _make_prop()
    prop.estado = "segunda mano"

    apply_check_outcome(session, prop, CheckOutcome.GONE, estado="Vendida")

    assert prop.estado == "segunda mano"
    assert prop.estado_baja == "Vendida"


def test_empty_deactivation_also_sets_estado_baja_and_keeps_estado():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1)
    prop.estado = "nuevo"
    prop.ultimo_strike = datetime.utcnow() - STRIKE_MIN_INTERVAL - timedelta(hours=1)

    result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert result == "deactivated"
    assert prop.estado == "nuevo"
    assert prop.estado_baja == "No disponible"


# --- strikes are time-separated (issue #53) ------------------------------------

def test_first_empty_records_the_strike_timestamp():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=0)

    apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert prop.intentos_fallidos == 1
    assert prop.ultimo_strike is not None


def test_second_empty_within_the_interval_is_not_a_second_strike():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1)
    prop.ultimo_strike = datetime.utcnow() - timedelta(hours=1)

    result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert result == "strike"
    assert prop.activa is True
    assert prop.intentos_fallidos == 1
    session.commit.assert_not_called()


def test_second_empty_after_the_interval_deactivates():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1)
    prop.ultimo_strike = datetime.utcnow() - STRIKE_MIN_INTERVAL - timedelta(minutes=1)

    result = apply_check_outcome(session, prop, CheckOutcome.EMPTY)

    assert result == "deactivated"
    assert prop.activa is False


def test_strike_without_a_timestamp_counts_as_old_legacy_row():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1)
    prop.ultimo_strike = None

    assert apply_check_outcome(session, prop, CheckOutcome.EMPTY) == "deactivated"


def test_alive_clears_the_strike_timestamp():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=1)
    prop.ultimo_strike = datetime.utcnow()

    apply_check_outcome(session, prop, CheckOutcome.ALIVE)

    assert prop.intentos_fallidos == 0
    assert prop.ultimo_strike is None


# --- reactivate / breaker (issue #53) --------------------------------------------

def test_reactivate_restores_the_listing_and_clears_baja_fields():
    session = MagicMock()
    prop = _make_prop(intentos_fallidos=0, activa=False)
    prop.fecha_baja = datetime.utcnow()
    prop.estado_baja = "No disponible"
    prop.estado = "segunda mano"

    reactivate(session, prop)

    assert prop.activa is True
    assert prop.fecha_baja is None
    assert prop.estado_baja is None
    assert prop.estado == "segunda mano"
    assert prop.intentos_fallidos == 0
    session.commit.assert_called_once()


@pytest.mark.parametrize(
    "bad,total,expected",
    [
        (5, 5, True),    # everything empty
        (6, 10, True),   # more than half
        (5, 10, False),  # exactly half is not "more than"
        (4, 4, False),   # below the minimum sample: too little evidence
        (0, 50, False),
    ],
)
def test_source_looks_broken(bad, total, expected):
    assert source_looks_broken(bad, total) is expected

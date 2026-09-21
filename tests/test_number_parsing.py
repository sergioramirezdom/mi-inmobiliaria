"""Shared EU number parser: thousands '.', decimal ',', anchored unit/currency
suffixes (never a character class over letters/digits)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.number_parsing import parse_eu_number


@pytest.mark.parametrize(
    "text, expected",
    [
        ("150.000", 150000.0),
        ("225.000", 225000.0),
        ("220.000", 220000.0),
        ("120.000", 120000.0),
        ("72,5", 72.5),
        ("82", 82.0),
        ("1.234,5", 1234.5),
        ("1.200", 1200.0),
        ("69,84", 69.84),
        ("69.84", 69.84),
        ("0.500", 0.5),
        ("1.234.567", 1234567.0),
        ("1,234.5", 1234.5),
    ],
)
def test_plain_numbers(text, expected):
    assert parse_eu_number(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("150.000 €", 150000.0),
        ("€ 225.000", 225000.0),
        ("150.000\xa0€", 150000.0),
        ("72 m²", 72.0),
        ("72,5 m2", 72.5),
        ("1.200 M2", 1200.0),
        ("  82  ", 82.0),
    ],
)
def test_currency_and_unit_suffixes_are_stripped(text, expected):
    assert parse_eu_number(text) == expected


@pytest.mark.parametrize(
    "text", [None, "", "  ", ",", ".", "abc", "1.2.3", "12,34,56", "m2", "1.23.456", "7 habitaciones"]
)
def test_unparseable_input_is_none(text):
    assert parse_eu_number(text) is None


def test_numbers_pass_through_and_bool_is_rejected():
    assert parse_eu_number(150000) == 150000.0
    assert parse_eu_number(72.5) == 72.5
    assert parse_eu_number(True) is None

"""Shared parsing of European-formatted numbers scraped from listing pages."""

import re
from typing import Any, Optional

# One number with an optional currency prefix and an optional currency/unit
# suffix. Anchored on both ends so stray letters or digits never leak into the
# number (a character class like [m2] would eat every "2").
_NUMBER_RE = re.compile(
    r"^(?:[€$]\s*)?(?P<num>\d[\d.,]*)\s*(?:€|\$|m²|m2|m\^2)?$",
    re.IGNORECASE,
)


def parse_eu_number(value: Any) -> Optional[float]:
    """Parse '1.234,5', '150.000 €', '72,5 m²' or '1.200' into a float.

    '.' is a thousands separator when it groups exactly three digits
    ('1.200' -> 1200.0); ',' is the decimal separator ('72,5' -> 72.5).
    When both appear, the last one is the decimal separator ('1,234.5'
    -> 1234.5). Anything ambiguous or malformed returns None rather than a
    wrong number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    match = _NUMBER_RE.match(value.replace("\xa0", " ").strip())
    if not match:
        return None
    num = match.group("num").rstrip(".,")

    if "." in num and "," in num:
        decimal = "." if num.rindex(".") > num.rindex(",") else ","
        thousands = "," if decimal == "." else "."
        integer, _, fraction = num.rpartition(decimal)
        if not _is_grouped(integer, thousands) or not fraction.isdigit():
            return None
        return float(integer.replace(thousands, "") + "." + fraction)

    for sep in (".", ","):
        if sep not in num:
            continue
        if num.count(sep) > 1:
            return float(num.replace(sep, "")) if _is_grouped(num, sep) else None
        integer, _, fraction = num.partition(sep)
        if sep == "." and len(fraction) == 3 and 1 <= len(integer) <= 3 and integer != "0":
            return float(integer + fraction)
        return float(integer + "." + fraction)

    return float(num)


def _is_grouped(text: str, sep: str) -> bool:
    """True when text is digits grouped by `sep` in threes: '1.234.567'."""
    return re.fullmatch(rf"\d{{1,3}}(?:{re.escape(sep)}\d{{3}})*", text) is not None

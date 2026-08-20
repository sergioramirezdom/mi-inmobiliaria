"""Pure outcome classifier and single deactivation gate for sold-check flows.

Shared by `sold_checker.py`'s Case 1/Case 2 logic and `paginated_scraper.py`'s
3-day duplicate re-check, so both paths use identical gone/unknown/error
semantics and write through the same strike counter.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlmodel import Session

STRIKE_THRESHOLD = 2


class CheckOutcome(str, Enum):
    """Tri-state result of inspecting a property detail fetch."""

    ALIVE = "alive"
    GONE = "gone"
    EMPTY = "empty"
    ERROR = "error"


def classify_check_outcome(details: Dict[str, Any]) -> CheckOutcome:
    """Classify a detail-scrape result dict into ALIVE / GONE / EMPTY.

    `ERROR` is never produced here — it is the caller's responsibility to
    map a fetch exception (timeout, 5xx, etc.) to `CheckOutcome.ERROR`
    without calling this classifier at all.
    """
    if "activa" in details and not details["activa"]:
        return CheckOutcome.GONE
    if "activa" not in details and not details.get("titulo") and not details.get("precio"):
        return CheckOutcome.EMPTY
    return CheckOutcome.ALIVE


def apply_check_outcome(
    session: Session,
    prop: Any,
    outcome: CheckOutcome,
    estado: Optional[str] = None,
) -> str:
    """Apply a `CheckOutcome` to a `Propiedad`-like object.

    This is the SINGLE writer of `intentos_fallidos`. Returns one of:
    - "deactivated": property was just marked activa=False
    - "strike": an EMPTY outcome was recorded but did not yet deactivate
    - "alive": outcome was ALIVE (counter reset if it was non-zero)
    - "skipped": outcome was ERROR — no DB writes, counter untouched
    """
    if outcome is CheckOutcome.ERROR:
        return "skipped"

    if outcome is CheckOutcome.GONE:
        prop.activa = False
        prop.estado = estado
        prop.fecha_baja = datetime.utcnow()
        prop.intentos_fallidos = 0
        session.add(prop)
        session.commit()
        return "deactivated"

    if outcome is CheckOutcome.EMPTY:
        strikes = (prop.intentos_fallidos or 0) + 1
        if strikes >= STRIKE_THRESHOLD:
            prop.activa = False
            prop.fecha_baja = datetime.utcnow()
            prop.intentos_fallidos = 0
            session.add(prop)
            session.commit()
            return "deactivated"
        prop.intentos_fallidos = strikes
        session.add(prop)
        session.commit()
        return "strike"

    # ALIVE
    if (prop.intentos_fallidos or 0) != 0:
        prop.intentos_fallidos = 0
        session.add(prop)
        session.commit()
    return "alive"

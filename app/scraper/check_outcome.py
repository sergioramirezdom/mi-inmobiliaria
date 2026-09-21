"""Pure outcome classifier and single deactivation gate for sold-check flows.

Shared by `sold_checker.py`'s Case 1/Case 2 logic and `paginated_scraper.py`'s
3-day duplicate re-check, so both paths use identical gone/unknown/error
semantics and write through the same strike counter.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

import httpx
from sqlmodel import Session

STRIKE_THRESHOLD = 2
# Strikes count separate looks at the listing, not calls: scrapes run hourly, so
# two EMPTY results minutes apart (one anti-bot page) must be one strike.
STRIKE_MIN_INTERVAL = timedelta(hours=20)

# Per-run circuit breaker: when more than this share of one fuente's checked
# listings comes back EMPTY/ERROR the source itself is broken (anti-bot page,
# layout change), not the listings. Below the minimum sample there is too
# little evidence to say so.
BROKEN_SOURCE_RATIO = 0.5
BROKEN_SOURCE_MIN_SAMPLE = 5

# Statuses that mean the listing itself is gone. Everything else (403/429/5xx,
# timeouts, DNS...) says nothing about the listing.
GONE_STATUS_CODES = (404, 410)


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


def classify_fetch_error(exc: BaseException) -> CheckOutcome:
    """Map a detail-fetch exception to GONE or ERROR by HTTP status, never by text.

    Scrapers re-raise the httpx error wrapped in their own exception type, so
    the ``__cause__``/``__context__`` chain is searched for an
    ``httpx.HTTPStatusError``. Only a 404/410 response is GONE. The exception
    message is never inspected: httpx embeds the URL in it, so ".../14042"
    would look like a 404.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in GONE_STATUS_CODES:
                return CheckOutcome.GONE
            return CheckOutcome.ERROR
        exc = exc.__cause__ or exc.__context__
    return CheckOutcome.ERROR


def source_looks_broken(bad: int, total: int) -> bool:
    """True when ``bad`` of ``total`` checks is too many to blame the listings."""
    return total >= BROKEN_SOURCE_MIN_SAMPLE and bad / total > BROKEN_SOURCE_RATIO


def reactivate(session: Session, prop: Any) -> None:
    """Restore a deactivated listing that is live again and clear its baja data.

    The building condition (`estado`) is never touched. Callers must not use
    this for manually excluded listings (`excluir_de_estadisticas`).
    """
    prop.activa = True
    prop.fecha_baja = None
    prop.estado_baja = None
    prop.intentos_fallidos = 0
    prop.ultimo_strike = None
    session.add(prop)
    session.commit()


def apply_check_outcome(
    session: Session,
    prop: Any,
    outcome: CheckOutcome,
    estado: Optional[str] = None,
) -> str:
    """Apply a `CheckOutcome` to a `Propiedad`-like object.

    This is the SINGLE writer of `intentos_fallidos`. Returns one of:
    - "deactivated": property was just marked activa=False
    - "strike": an EMPTY outcome was recorded (or already counted within
      `STRIKE_MIN_INTERVAL`) but did not yet deactivate
    - "alive": outcome was ALIVE (counter reset if it was non-zero)
    - "skipped": outcome was ERROR — no DB writes, counter untouched
    """
    if outcome is CheckOutcome.ERROR:
        return "skipped"

    # `estado` is the sale status ("Vendida"/"No disponible"); it goes to
    # `estado_baja`, never over `Propiedad.estado` (the building condition).
    if outcome is CheckOutcome.GONE:
        prop.activa = False
        prop.estado_baja = estado
        prop.fecha_baja = datetime.utcnow()
        prop.intentos_fallidos = 0
        session.add(prop)
        session.commit()
        return "deactivated"

    if outcome is CheckOutcome.EMPTY:
        now = datetime.utcnow()
        # A repeat look inside the interval is the same strike; a missing
        # timestamp (rows struck before the column existed) counts as old.
        if prop.ultimo_strike is not None and now - prop.ultimo_strike < STRIKE_MIN_INTERVAL:
            return "strike"
        strikes = (prop.intentos_fallidos or 0) + 1
        if strikes >= STRIKE_THRESHOLD:
            prop.activa = False
            prop.estado_baja = estado or "No disponible"
            prop.fecha_baja = now
            prop.intentos_fallidos = 0
            prop.ultimo_strike = None
            session.add(prop)
            session.commit()
            return "deactivated"
        prop.intentos_fallidos = strikes
        prop.ultimo_strike = now
        session.add(prop)
        session.commit()
        return "strike"

    # ALIVE
    if (prop.intentos_fallidos or 0) != 0:
        prop.intentos_fallidos = 0
        prop.ultimo_strike = None
        session.add(prop)
        session.commit()
    return "alive"

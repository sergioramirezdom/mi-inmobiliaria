"""Shared sold/reserved/rented detection for detail scrapers.

A ficha that reports "vendido"/"reservado" is deactivated immediately (no
strike counter) and a new one is never saved, so a false positive silently
loses a live listing. Searching the whole page text for a bare keyword also
matches the footer ("Todos los derechos reservados"), menus, "similares"
cards and the description ("plaza de garaje reservada"). This helper only
trusts a bounded, contextual signal:

1. a status element (class/id says ribbon/estado/badge/...) with short text;
2. an element whose entire text is the status word or sentence ("VENDIDO",
   "Reserved", "Este inmueble está vendido");
3. a status segment of the ``<h1>`` title ("Vendido - Piso en ...").

Nothing inside nav/footer/menu/"similares" regions, links, buttons or
selects counts. Sites whose ribbon markup matches none of these are left
active (and re-checked next run): a missed sold flag is recoverable, a false one is not.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)

_WORDS = r"vendid[oa]|reservad[oa]|sold|reserved"
_WORDS_RENTED = _WORDS + r"|alquilad[oa]|rented"

# Canonical Spanish estado for the English words; Spanish keeps its gender.
_ENGLISH = {"sold": "Vendido", "reserved": "Reservado", "rented": "Alquilado"}

_HINTS = ("estado", "status", "ribbon", "cinta", "sold", "vendid", "reservad", "badge", "banner", "flag")
_HINT_SELECTOR = ", ".join(f'[class*="{h}" i], [id*="{h}" i]' for h in _HINTS)
_MAX_BADGE_CHARS = 40

_EXCLUDED_TAGS = frozenset(
    {"nav", "footer", "select", "option", "a", "button", "script", "style", "noscript", "head"}
)
SECONDARY_REGION_RE = re.compile(r"similar|relacionad|related|recomend|footer|cookie|menu|\bnav", re.I)

# Free text (manual URLs on unknown sites): the status must be the predicate of
# the listing, not a complement ("plaza de garaje reservada").
_TEXT_LEAD = (
    r"(?:^|[.!?:;|•\n\-–—]\s*"
    r"|\b(?:est[aá]|ha\s+sido|se\s+ha|propiedad|inmueble|vivienda|anuncio|piso|casa)\s+(?:ya\s+|actualmente\s+)?)"
)


# "Este inmueble está VENDIDO": a standalone status sentence, not a description.
_SUBJECT = r"(?:(?:este|esta)\s+)?(?:(?:inmueble|propiedad|vivienda|piso|casa|anuncio|ficha)\s+)?"
_AUX = r"(?:ya\s+)?(?:est[aá]|ha\s+sido)(?:\s+ya)?"


def _regexes(include_rented: bool):
    words = _WORDS_RENTED if include_rented else _WORDS
    return {
        "exact": re.compile(rf"^\W*(?:{_SUBJECT}{_AUX}\s+)?({words})\W*$", re.I),
        "word": re.compile(rf"\b({words})\b", re.I),
        "title": re.compile(
            rf"^\W*({words})\b|\b({words})\W*$|[\-–—|:·(\[]\s*({words})\s*(?:[\-–—|:·)\]]|$)", re.I
        ),
        "text": re.compile(_TEXT_LEAD + rf"({words})\b", re.I),
    }


def _estado(word: str) -> str:
    word = word.lower()
    return _ENGLISH.get(word) or word.capitalize()


def _matched(match: "re.Match") -> str:
    return next(g for g in match.groups() if g)


def _excluded(node) -> bool:
    """True when the node sits inside nav/footer/menu/"similares"/link regions."""
    el = node if isinstance(node, Tag) else node.parent
    while el is not None and getattr(el, "name", None) not in (None, "[document]"):
        if el.name in _EXCLUDED_TAGS:
            return True
        attrs = " ".join(
            [" ".join(el.get("class") or []), el.get("id") or ""]
        )
        if attrs.strip() and SECONDARY_REGION_RE.search(attrs):
            return True
        el = el.parent
    return False


def detect_estado_venta(
    soup: BeautifulSoup, *, include_rented: bool = False
) -> Optional[str]:
    """Return the ficha's own status ("Vendido", "Reservada", ...) or None.

    ``include_rented`` also accepts "alquilado/a"/"rented" (scrapers that
    already treated it as a gone listing). The matched rule and text are
    logged so a deactivation can be traced.
    """
    rx = _regexes(include_rented)

    # 1. Status elements (ribbon/badge/estado...) with short text.
    for el in soup.select(_HINT_SELECTOR):
        if _excluded(el):
            continue
        text = el.get_text(" ", strip=True)
        m = rx["word"].search(text) if 0 < len(text) <= _MAX_BADGE_CHARS else None
        if m:
            return _found(_matched(m), f"status element <{el.name} class={el.get('class')}>", text)

    # 2. An element whose whole text is the status word or a status sentence.
    for node in soup.find_all(string=rx["exact"]):
        if type(node) is not NavigableString or _excluded(node):
            continue
        m = rx["exact"].match(str(node).strip())
        if m:
            return _found(_matched(m), f"status text in <{node.parent.name}>", str(node).strip())

    # 3. Status segment of the title.
    for h1 in soup.find_all("h1"):
        if _excluded(h1):
            continue
        text = h1.get_text(" ", strip=True)
        m = rx["title"].search(text)
        if m:
            return _found(_matched(m), "h1 title", text)

    return None


def detect_estado_en_texto(text: str, *, include_rented: bool = False) -> Optional[str]:
    """Free-text fallback for pages with unknown markup (manual URLs).

    Only matches a status that is the predicate of the listing ("Esta propiedad
    está vendida", a leading "RESERVADO."), never "plaza de garaje reservada",
    "zona reservada" or "derechos reservados".
    """
    m = _regexes(include_rented)["text"].search(text or "")
    if not m:
        return None
    return _found(_matched(m), "text phrase", (text or "")[max(0, m.start() - 20): m.end() + 20])


def _found(word: str, rule: str, evidence: str) -> str:
    estado = _estado(word)
    logger.info("Estado '%s' detectado por %s: %r", estado, rule, evidence[:60])
    return estado

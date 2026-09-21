"""Common detection of operation type (venta/alquiler) and property type exclusions.

A wrong answer here silently DROPS a listing, so every signal is matched on word
boundaries and the costly errors (a sale read as a rental, a flat read as a
garage) are avoided by preferring "uncertain" over a weak guess.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Signals ─────────────────────────────────────────────────────────────────
# "alquilado/a" (a rented-out flat sold to an investor) is an attribute, not an
# operation, so it is deliberately absent; \b keeps "diferente"/"aparente" out.
_TITULO_ALQUILER_RE = re.compile(
    r"\balquiler(?:es)?\b|\balquila\b|\barrendamiento\b|\bfor rent\b|\bto rent\b"
    r"|\d\s*(?:€|eur|euros?)?\s*/\s*mes\b",
)
_TITULO_VENTA_RE = re.compile(r"\bventa\b|\bvende\b|\bvendo\b|\bfor sale\b")

# URL path segments ("Venta-Piso-1", "/alquiler/"): the site's own category.
_URL_ALQUILER_RE = re.compile(r"(?<![a-z])alquiler(?:es)?(?![a-z])")
_URL_VENTA_RE = re.compile(r"(?<![a-z])ventas?(?![a-z])")

# Description: phrases only, and only when nothing points to a sale. The words
# below mark a sale of a rented-out / investment property, not a rental.
_DESC_ALQUILER_RE = re.compile(r"\bse alquila\b|\ben alquiler\b")
_DESC_VENTA_RE = re.compile(r"\bse vende\b|\ben venta\b|\bvendo\b")
_DESC_INVERSION_RE = re.compile(r"inquilino|alquilad[oa]|rentabilidad|inversi[oó]n")

# "garaje" only counts as the property type when it is the head noun of the
# title ("Plaza de garaje en centro"), not a complement ("Piso con garaje").
_GARAJE_NOUN = (
    r"(?:plazas?\s+de\s+(?:garaje|garage|parking|aparcamiento)|plazas?\s+garaje"
    r"|garajes?|garages?|parking|aparcamientos?|cocheras?)"
)
_TITULO_GARAJE_RE = re.compile(
    r"^\W*(?:(?:se\s+)?(?:vende|alquila)\s+|(?:en\s+)?venta\s+(?:de\s+)?|for\s+sale\s+(?:of\s+)?)?"
    r"(?:una?\s+)?" + _GARAJE_NOUN + r"\b"
)
_TIPOS_GARAJE = ("garaje", "garage", "parking")
_TIPOS_GENERICOS = ("", "inmueble", "otros", "otro")


def _url_operacion(url: Optional[str]) -> Optional[str]:
    """Operation from the URL path/query only (the domain says nothing)."""
    parsed = urlparse((url or "").lower())
    haystack = f"{parsed.path} {parsed.query}"
    alquiler = _URL_ALQUILER_RE.search(haystack)
    venta = _URL_VENTA_RE.search(haystack)
    if alquiler and not venta:
        return "alquiler"
    if venta and not alquiler:
        return "venta"
    return None


def detectar_operacion(
    titulo: Optional[str] = None,
    precio: Optional[float] = None,
    url: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> Optional[str]:
    """Detect if a property is venta or alquiler.

    Signals, strongest first: URL path, title, description phrases. ``precio``
    is accepted for backwards compatibility but is not a signal: a cheap plot,
    garage or storage room is a sale, and a rental normally says so in its URL
    or title.

    Returns:
        "venta", "alquiler", or None if uncertain.
    """
    # ── 1. URL path (the site's own category) ───────────────────────────────
    operacion = _url_operacion(url)
    if operacion:
        logger.debug("%s detectada por URL: %s", operacion, (url or "")[:60])
        return operacion

    # ── 2. Title ────────────────────────────────────────────────────────────
    titulo_lower = (titulo or "").lower()
    alquiler = _TITULO_ALQUILER_RE.search(titulo_lower)
    venta = _TITULO_VENTA_RE.search(titulo_lower)
    if alquiler and venta:
        logger.debug("Operación ambigua en título: %s", titulo_lower[:60])
        return None
    if alquiler:
        logger.debug("Alquiler detectado en título: %s", titulo_lower[:60])
        return "alquiler"
    if venta:
        logger.debug("Venta detectada en título: %s", titulo_lower[:60])
        return "venta"

    # ── 3. Description phrases (weak; first 500 chars, sale evidence wins) ──
    desc_lower = (descripcion or "")[:500].lower()
    if (
        _DESC_ALQUILER_RE.search(desc_lower)
        and not _DESC_VENTA_RE.search(desc_lower)
        and not _DESC_INVERSION_RE.search(desc_lower)
    ):
        logger.debug("Alquiler detectado en descripción: %s", (titulo or "")[:60])
        return "alquiler"

    return None  # Uncertain


def es_garaje(
    titulo: Optional[str] = None,
    tipo_propiedad: Optional[str] = None,
    url: Optional[str] = None,
) -> bool:
    """Detect if a property IS a garage (not just includes one)."""
    tipo = (tipo_propiedad or "").strip().lower()
    if tipo in _TIPOS_GARAJE:
        return True

    url_lower = (url or "").lower()
    if "/garajes/" in url_lower or "/garaje/" in url_lower:
        return True

    # A known, non-garage type is authoritative over the title wording.
    if tipo not in _TIPOS_GENERICOS:
        return False

    return bool(_TITULO_GARAJE_RE.search((titulo or "").lower()))

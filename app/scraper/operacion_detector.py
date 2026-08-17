"""Common detection of operation type (venta/alquiler) and property type exclusions."""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Keywords ────────────────────────────────────────────────────────────────
_ALQUILER_KEYWORDS = (
    "alquiler", "alquila", "alquilado", "arrendamiento",
    "rent", "rental", "leasing",
    "/mes", "€/mes", "eur/mes",
)

_VENTA_KEYWORDS = (
    "venta", "vende", "en venta",
    "sale", "for sale",
)

# Price threshold: below this, it's almost certainly a rental (monthly rent)
_PRECIO_ALQUILER_MAX = 5_000  # €/mes — very few sales below this in El Puerto

# Garaje-related keywords for tipo_propiedad detection
_GARAJE_KEYWORDS = (
    "garaje", "garage", "parking", "plaza de garaje",
    "plaza garaje", "plazas de garaje",
)


def detectar_operacion(
    titulo: Optional[str] = None,
    precio: Optional[float] = None,
    url: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> Optional[str]:
    """Detect if a property is venta or alquiler.

    Returns:
        "venta", "alquiler", or None if uncertain.
    """
    # ── 1. Explicit keywords in title (strongest signal) ────────────────────
    titulo_lower = (titulo or "").lower()

    for kw in _ALQUILER_KEYWORDS:
        if kw in titulo_lower:
            logger.debug(f"Alquiler detectado por keyword '{kw}' en título: {titulo[:60]}")
            return "alquiler"

    for kw in _VENTA_KEYWORDS:
        if kw in titulo_lower:
            logger.debug(f"Venta detectada por keyword '{kw}' en título: {titulo[:60]}")
            return "venta"

    # ── 2. URL check ────────────────────────────────────────────────────────
    url_lower = (url or "").lower()
    if "alquiler" in url_lower or "alquileres" in url_lower:
        logger.debug(f"Alquiler detectado por URL: {url[:60]}")
        return "alquiler"
    if "venta" in url_lower or "ventas" in url_lower:
        logger.debug(f"Venta detectada por URL: {url[:60]}")
        return "venta"

    # ── 3. Price heuristic ──────────────────────────────────────────────────
    if precio is not None and precio > 0:
        if precio < _PRECIO_ALQUILER_MAX:
            # Very low price → likely a monthly rent
            logger.debug(f"Precio bajo ({precio}€) sugiere alquiler: {titulo[:60]}")
            return "alquiler"

    # ── 4. Description keywords (weaker signal, only check first 500 chars) ──
    desc_lower = (descripcion or "")[:500].lower()
    for kw in ("alquiler", "alquila", "arrendamiento", "/mes"):
        if kw in desc_lower:
            logger.debug(f"Alquiler detectado por keyword '{kw}' en descripción: {titulo[:60]}")
            return "alquiler"

    return None  # Uncertain


def es_garaje(
    titulo: Optional[str] = None,
    tipo_propiedad: Optional[str] = None,
    url: Optional[str] = None,
) -> bool:
    """Detect if a property IS a garage (not just includes one)."""
    if tipo_propiedad and tipo_propiedad.lower() in ("garaje", "garage", "parking"):
        return True

    titulo_lower = (titulo or "").lower()
    for kw in _GARAJE_KEYWORDS:
        if kw in titulo_lower:
            # Verify it's the main type, not just "incluye garaje"
            if "incluye" in titulo_lower or "con garaje" in titulo_lower:
                return False
            return True

    url_lower = (url or "").lower()
    if "/garajes/" in url_lower or "/garaje/" in url_lower:
        return True

    return False

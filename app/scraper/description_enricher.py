"""
Extract structured property data from free-text descriptions.

Used for the review page: proposes values for empty fields so the user
can approve/reject them before they are written to the database.
"""

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple


# (suggested_value, human-readable reason shown in UI)
Suggestion = Tuple[Any, str]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _has_negation(text_norm: str, keyword: str) -> bool:
    pattern = rf"(sin|no (tiene|hay|dispone|cuenta con)|no (tiene|hay))\s+\w*\s*{keyword}"
    return bool(re.search(pattern, text_norm))


def extract_suggestions(prop) -> Dict[str, Suggestion]:
    """
    Parse a property's titulo + descripcion and return suggested values
    only for fields that are currently None/empty.

    Returns dict: {field_name: (suggested_value, reason_text)}
    """
    raw = " ".join(filter(None, [prop.titulo, prop.descripcion]))
    if not raw:
        return {}

    n = _norm(raw)  # normalized for matching
    suggestions: Dict[str, Suggestion] = {}

    # ── Ascensor ─────────────────────────────────────────────────────────
    if prop.ascensor is None:
        neg = bool(re.search(
            r"(sin ascensor|no (tiene|hay|dispone|cuenta con) ascensor)", n
        ))
        pos = not neg and bool(re.search(r"\bascensor\b", n))

        if neg:
            suggestions["ascensor"] = (False, "Detectado 'sin ascensor' en descripción")
        elif pos:
            # Extra confidence: if piso on floor >= 2 without negation, very likely
            suggestions["ascensor"] = (True, "Detectado 'ascensor' en descripción")

    # ── Garaje ───────────────────────────────────────────────────────────
    if prop.garaje is None:
        neg = bool(re.search(
            r"(sin (garaje|plaza|parking)|no (tiene|incluye|hay) (garaje|parking|plaza))", n
        ))
        pos = not neg and bool(re.search(
            r"(con garaje|plaza de garaje|garaje incluido|parking incluido|\bgaraje\b|\bparking\b)", n
        ))
        if neg:
            suggestions["garaje"] = (False, "Detectado 'sin garaje' en descripción")
        elif pos:
            suggestions["garaje"] = (True, "Detectado 'garaje/parking' en descripción")

    # ── Terraza ───────────────────────────────────────────────────────────
    if prop.terraza is None and re.search(r"\bterraza\b", n):
        neg = _has_negation(n, "terraza")
        suggestions["terraza"] = (
            not neg,
            "'sin terraza' detectado" if neg else "Detectado 'terraza' en descripción",
        )

    # ── Balcón ────────────────────────────────────────────────────────────
    if prop.balcon is None and re.search(r"\bbalcon\b", n):
        neg = _has_negation(n, "balcon")
        suggestions["balcon"] = (
            not neg,
            "'sin balcón' detectado" if neg else "Detectado 'balcón' en descripción",
        )

    # ── Piscina ───────────────────────────────────────────────────────────
    if prop.piscina is None and re.search(r"\bpiscina\b", n):
        neg = _has_negation(n, "piscina")
        suggestions["piscina"] = (
            not neg,
            "'sin piscina' detectado" if neg else "Detectado 'piscina' en descripción",
        )

    # ── Trastero ─────────────────────────────────────────────────────────
    if prop.trastero is None and re.search(r"\btrastero\b", n):
        neg = _has_negation(n, "trastero")
        suggestions["trastero"] = (
            not neg,
            "'sin trastero' detectado" if neg else "Detectado 'trastero' en descripción",
        )

    # ── Aire acondicionado ────────────────────────────────────────────────
    if prop.aire_acondicionado is None and re.search(r"aire (acondicionado|acond\.?|acond\b)", n):
        neg = _has_negation(n, "aire")
        suggestions["aire_acondicionado"] = (
            not neg,
            "Detectado 'aire acondicionado' en descripción",
        )

    # ── Habitaciones ──────────────────────────────────────────────────────
    if prop.habitaciones is None:
        m = re.search(r"(\d+)\s*(habitacion(es)?|dormitorio(s)?|hab\.\s|dorm\.)", n)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                suggestions["habitaciones"] = (val, f"Extraído: '{m.group().strip()}'")

    # ── Baños ─────────────────────────────────────────────────────────────
    if prop.banos is None:
        m = re.search(r"(\d+)\s*(bano(s)?|aseo(s)?|cuarto(s)? de bano)", n)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 6:
                suggestions["banos"] = (val, f"Extraído: '{m.group().strip()}'")

    # ── Superficie ────────────────────────────────────────────────────────
    if prop.superficie_m2 is None:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", n)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                if 20 <= val <= 2000:
                    suggestions["superficie_m2"] = (val, f"Extraído: '{m.group().strip()}'")
            except ValueError:
                pass

    # ── Barrio / zona ─────────────────────────────────────────────────────
    if not prop.barrio:
        # Use original text (pre-norm) to preserve accents for display
        raw_lower = raw.lower()
        zone_patterns = [
            r"urbanizaci[oó]n\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,30}?)(?=\s*[,.\n]|$)",
            r"urb\.\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,30}?)(?=\s*[,.\n]|$)",
            r"zona\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,25}?)(?=\s*[,.\n]|$)",
            r"barrio\s+(?:de\s+)?([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,25}?)(?=\s*[,.\n]|$)",
        ]
        for pattern in zone_patterns:
            m = re.search(pattern, raw_lower)
            if m:
                zona = m.group(1).strip().title()
                stopwords = {"la", "el", "los", "las", "un", "una", "del", "de"}
                if len(zona) > 2 and zona.lower() not in stopwords:
                    suggestions["barrio"] = (zona, f"Detectado: «{m.group().strip()}»")
                    break

    return suggestions

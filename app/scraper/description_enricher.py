"""
Extract structured property data from free-text descriptions.

Used for the review page: proposes values for empty fields so the user
can approve/reject them before they are written to the database.
"""

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

from .zona_normalizer import CONFIANZA_EXACTA, normalizar as normalizar_zona


# (suggested_value, human-readable reason shown in UI)
Suggestion = Tuple[Any, str]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


# Negation right before the keyword, within the same clause (up to 3 words between).
_NEGATION_RE = re.compile(
    r"\b(?:sin|no\s+(?:tiene|hay|dispone|cuenta|incluye)(?:\s+(?:de|con))?)(?:\s+\w+){0,3}\s*$"
)
# Proximity or speculative wording: the feature is not (yet) part of the property.
_NOT_A_FEATURE_RE = re.compile(
    r"\b(?:cerca|junto|frente|proxim\w*|lindando|al lado|a pocos (?:metros|minutos)"
    r"|posibilidad|opcion|instalar|instalacion|colocar|preinstalacion|proyecto)\b(?:\s+\w+){0,4}\s*$"
)


def _classify_mention(text_norm: str, keyword: str) -> Optional[bool]:
    """True/False if the text says the property has/lacks `keyword`; None if unclear.

    `keyword` is a regex over the normalized text. Each mention is judged by
    the clause preceding it: negation wins, proximity/speculative mentions
    ("cerca de la piscina municipal", "posibilidad de instalar ascensor") are ignored.
    """
    has, lacks = False, False
    for m in re.finditer(rf"\b{keyword}\b", text_norm):
        clause = re.split(r"[,.;:\n]", text_norm[max(0, m.start() - 60):m.start()])[-1]
        if _NEGATION_RE.search(clause):
            lacks = True
        elif not _NOT_A_FEATURE_RE.search(clause):
            has = True
    if lacks:
        return False
    return True if has else None


_M2_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m[²2]")
# Areas that describe something other than the dwelling itself
_OTHER_AREA_RE = re.compile(r"\b(?:parcela|terreno|solar|finca|jardin|terraza|patio|garaje|trastero|plaza)\b")
_DWELLING_AREA_RE = re.compile(r"\b(?:construid\w*|util\w*|vivienda)\b")


def _extract_superficie(text_norm: str) -> Optional[Suggestion]:
    """Dwelling area: prefer 'construidos/utiles/vivienda' m2, skip parcela/terraza/etc."""
    candidatos, preferidos = [], []
    previo = 0
    for m in _M2_RE.finditer(text_norm):
        antes = text_norm[max(previo, m.start() - 30):m.start()]
        despues = text_norm[m.end():m.end() + 15]
        previo = m.end()
        try:
            val = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if not 20 <= val <= 2000 or _OTHER_AREA_RE.search(antes):
            continue
        sugerencia = (val, f"Extraído: '{m.group().strip()}'")
        candidatos.append(sugerencia)
        if _DWELLING_AREA_RE.search(antes) or _DWELLING_AREA_RE.search(despues):
            preferidos.append(sugerencia)
    return (preferidos or candidatos or [None])[0]


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
        tiene = _classify_mention(n, "ascensor")
        if tiene is False:
            suggestions["ascensor"] = (False, "Detectado 'sin ascensor' en descripción")
        elif tiene:
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

    # ── Terraza / balcón / piscina / trastero / aire acondicionado ───────
    amenities = [
        ("terraza", "terraza", "'sin terraza' detectado", "Detectado 'terraza' en descripción"),
        ("balcon", "balcon", "'sin balcón' detectado", "Detectado 'balcón' en descripción"),
        ("piscina", "piscina", "'sin piscina' detectado", "Detectado 'piscina' en descripción"),
        ("trastero", "trastero", "'sin trastero' detectado", "Detectado 'trastero' en descripción"),
        ("aire_acondicionado", r"aire (?:acondicionado|acond)", "'sin aire' detectado",
         "Detectado 'aire acondicionado' en descripción"),
    ]
    for field, keyword, neg_reason, pos_reason in amenities:
        if getattr(prop, field) is None:
            tiene = _classify_mention(n, keyword)
            if tiene is not None:
                suggestions[field] = (tiene, pos_reason if tiene else neg_reason)

    # ── Habitaciones ──────────────────────────────────────────────────────
    if prop.habitaciones is None:
        m = re.search(r"(\d+)\s*(habitacion(es)?|dormitorio(s)?|hab\.\s|dorm\.)", n)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                suggestions["habitaciones"] = (val, f"Extraído: '{m.group().strip()}'")

    # ── Baños ─────────────────────────────────────────────────────────────
    if prop.banos is None:
        m = re.search(r"(\d+)\s*(bano(s)?|cuarto(s)? de bano)", n)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 6:
                suggestions["banos"] = (val, f"Extraído: '{m.group().strip()}'")

    # ── Superficie ────────────────────────────────────────────────────────
    if prop.superficie_m2 is None:
        found = _extract_superficie(n)
        if found:
            suggestions["superficie_m2"] = found

    # ── Barrio / zona ─────────────────────────────────────────────────────
    if not prop.barrio:
        found = _buscar_barrio(prop.titulo or "", prop.descripcion or "")
        if found:
            zona, fragmento = found
            suggestions["barrio"] = (zona, f"Detectado: «{fragmento}»")

    # ── Zona canónica ─────────────────────────────────────────────────────
    # Se sugiere revisión cuando la confianza NO es 'exacta':
    # - zona_normalizada IS NULL: nunca se resolvió
    # - zona_confianza = 'via' o 'debil': resolución incierta, el usuario
    #   debe confirmar o corregir antes de usar en filtros y estadísticas.
    if prop.zona_confianza != "exacta":
        match = normalizar_zona(
            barrio=prop.barrio,
            direccion=prop.direccion,
            titulo=prop.titulo,
            descripcion=prop.descripcion,
            url=prop.url_original,
        )
        if match.zona:
            suggestions["zona_normalizada"] = (match.zona, match.evidencia)

    return suggestions


# Zone cue words ("urbanización X", "zona X", "barrio de X"); what follows is only
# a candidate, it must resolve to the zone catalogue to be accepted.
_ZONE_CUE_RE = re.compile(
    r"\b(?:urbanizaci[oó]n|urb\.|zona|barrio(?:\s+de)?)\s+([^,.;\n]{2,40})"
)


def _buscar_barrio(titulo: str, descripcion: str) -> Optional[Tuple[str, str]]:
    """(canonical zone, matched text) for a cue phrase that hits the catalogue, else None."""
    raw = " ".join(filter(None, [titulo, descripcion]))
    for m in _ZONE_CUE_RE.finditer(raw.lower()):
        match = normalizar_zona(barrio=m.group(1))
        if match.zona and match.confianza == CONFIANZA_EXACTA:
            return match.zona, m.group().strip()
    return None


def extract_barrio_from_text(titulo: str, descripcion: str) -> Optional[str]:
    """
    Extract the barrio/zona from free text (titulo + descripcion).

    Only zones from the catalogue (zonas_elpuerto.yaml) are returned, by their
    canonical name; generic phrases ("zona residencial tranquila") yield None.
    Does not require a DB object.
    """
    found = _buscar_barrio(titulo or "", descripcion or "")
    return found[0] if found else None

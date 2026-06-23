"""Shared helpers for extracting zona/barrio from URL and HTML."""

import re
from typing import Optional
from urllib.parse import urlparse

MUNICIPIO_SLUGS = {
    "el_puerto_de_santa_maria", "el-puerto-de-santa-maria",
    "cadiz", "puerto_de_santa_maria", "puerto-de-santa-maria",
    "san_fernando", "jerez_de_la_frontera", "rota", "chipiona",
    "sanlucar_de_barrameda", "chiclana_de_la_frontera",
    "la_barca_de_la_florida",
}

SKIP_SEGMENTS = {
    "en_venta", "en_alquiler", "venta", "alquiler",
    "piso", "chalet", "casa", "local", "garaje", "terreno",
    "apartamento", "duplex", "atico", "finca", "oficina",
    "detalle", "buscador", "inmuebles", "cadiz", "www",
}

_ID_RE = re.compile(r"^\d[\d.]*$|^[a-f0-9]{10,}$", re.IGNORECASE)


def extract_from_url(url: str) -> Optional[str]:
    """Return zona from URL path segment after a known municipio slug, or None."""
    if not url:
        return None
    try:
        path = urlparse(url).path
    except Exception:
        return None

    segments = [s for s in path.split("/") if s]
    found_municipio = False

    for seg in segments:
        seg_lower = seg.lower()
        if seg_lower in MUNICIPIO_SLUGS:
            found_municipio = True
            continue
        if not found_municipio:
            continue
        if seg_lower in SKIP_SEGMENTS:
            continue
        if _ID_RE.match(seg):
            continue
        zona = seg.replace("_", " ").replace("-", " ").title()
        if len(zona) > 2:
            return zona

    return None


_HTML_PATTERNS = [
    re.compile(r"Zona[:\s]+([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s\-]{1,150})(?=[,\n<]|$)", re.IGNORECASE),
    re.compile(r"Barrio[:\s]+([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s\-]{1,150})(?=[,\n<]|$)", re.IGNORECASE),
    re.compile(r"\ben ([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,49}?) -\s*(?:El Puerto|Jerez|Cádiz|Cadiz|Rota|San Fernando)", re.IGNORECASE),
    re.compile(r"\bzona de ([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,39}?)[,\.]", re.IGNORECASE),
    re.compile(r"\bbarrio (?:de )?([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,39}?)[,\.]", re.IGNORECASE),
]

_STOP_WORDS = {"la", "el", "los", "las", "un", "una", "del", "de", "en", "por", "su"}


def extract_from_html(page_text: str, soup=None) -> Optional[str]:
    """Return zona from page text (and optional soup for h1/title priority), or None."""
    sources = []

    if soup is not None:
        for tag_name in ("h1", "title"):
            el = soup.find(tag_name)
            if el:
                sources.append(el.get_text(" ", strip=True))

    sources.append(page_text)

    for text in sources:
        for pattern in _HTML_PATTERNS:
            m = pattern.search(text)
            if m:
                zona = m.group(1).strip()[:60].strip()
                if len(zona) > 2 and zona.lower() not in _STOP_WORDS:
                    return zona

    return None

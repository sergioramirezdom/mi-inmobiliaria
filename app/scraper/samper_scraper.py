"""Detail scraper for sampergestionesinmobiliarias.es (InmoServer CMS).

SAMPER uses the same InmoServer CMS convention as Alonsaga/UriaHomes
(`#inmueble2_*` ids, `#carousel-img-principal` photo carousel), served in
Spanish. Unlike UriaHomes, the property characteristics are exposed as a
plain free-text `<li>` list inside
`#inmueble2_caracteristicas_inmueble_container` (e.g. "72 M2 Construidos",
"3 Dormitorios", "1 Baños", "Planta baja") rather than icon-labeled badges,
so those fields are extracted with the same regex/text-parsing approach as
`jimenezruiz_scraper.py`.

Selectors confirmed by a direct curl fetch of a real listing/detail page
(see sdd/samper-scraper-source/selectors-confirmed).
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from .config import ScraperConfig
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sampergestionesinmobiliarias.es"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}

TIPO_MAP = {
    "piso": "piso",
    "casa": "casa",
    "chalet": "chalet",
    "villa": "villa",
    "local": "local",
    "garaje": "garaje",
    "terreno": "terreno",
    "finca": "finca",
    "finca rustica": "finca",
    "oficina": "oficina",
    "edificio": "edificio",
    "duplex": "dúplex",
    "atico": "ático",
    "adosado": "adosado",
}

# Keywords that indicate a property is sold/reserved/rented on this site
# (checked against the lowercased page text).
_SOLD_KEYWORDS = ("vendido", "vendida", "reservado", "reservada", "alquilado", "alquilada")


class SamperScraper:
    """Detail scraper for SAMPER Gestiones Inmobiliarias (InmoServer CMS)."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {
            "url_original": url,
            "activa": True,
            "tipo_operacion": "venta",
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=BROWSER_HEADERS, timeout=self.config.timeout)
                if response.status_code == 404:
                    logger.info(f"HTTP 404 — marcando como no disponible: {url}")
                    data["activa"] = False
                    data["estado"] = "No disponible"
                    return data
                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    return data
                html = response.text
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return data

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True)
        lower_text = page_text.lower()

        # Sold/reserved/rented detection
        for keyword in _SOLD_KEYWORDS:
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title / tipo: #inmueble2_titulo2 (h4) → "Piso en venta"
        h4 = soup.select_one("#inmueble2_titulo2")
        titulo_text = h4.get_text(strip=True) if h4 else None
        if titulo_text:
            data["titulo"] = titulo_text
            tipo = _extract_tipo(titulo_text)
            if tipo:
                data["tipo_propiedad"] = tipo

        # Price: #inmueble2_precio, e.g. "240.000 €"
        precio_el = soup.select_one("#inmueble2_precio")
        if precio_el:
            precio = _parse_price_eu(precio_el.get_text(strip=True))
            if precio is not None:
                data["precio"] = precio

        # Address / municipio / barrio from #inmueble2_titulo2_subtitulo
        direccion = _extract_direccion(soup)
        if direccion:
            data["direccion"] = direccion
            municipio = _extract_municipio(direccion)
            if municipio:
                data["municipio"] = municipio
            barrio = _extract_barrio(direccion)
            if barrio:
                data["barrio"] = barrio

        if not data.get("municipio"):
            data["municipio"] = "El Puerto de Santa María"

        # Characteristics: free-text <li> list inside
        # #inmueble2_caracteristicas_inmueble_container
        li_items = _extract_caracteristicas_li_items(soup)
        for item in li_items:
            if "superficie_m2" not in data:
                m2 = _extract_superficie_m2(item)
                if m2 is not None:
                    data["superficie_m2"] = m2
            if "habitaciones" not in data:
                hab = _extract_habitaciones(item)
                if hab is not None:
                    data["habitaciones"] = hab
            if "banos" not in data:
                banos = _extract_banos(item)
                if banos is not None:
                    data["banos"] = banos
            if "planta" not in data:
                planta = _extract_planta(item)
                if planta is not None:
                    data["planta"] = planta
        if li_items:
            data["amenidades"] = li_items

        # Description: #inmueble2_descripcion_aut + #inmueble2_datos_adicionales
        desc = _extract_descripcion(soup)
        if desc:
            data["descripcion"] = desc

        # Reference: #referenceTop h4
        referencia = _extract_referencia(soup)
        if referencia:
            data["referencia"] = referencia

        # Photos: #carousel-img-principal img
        fotos = _extract_fotos_detail(soup)
        if fotos:
            data["fotos"] = fotos

        # Zona fallback: URL first, then HTML text
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data


# ── Module-level helpers ──────────────────────────────────────────────────────


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price string: '240.000 €' → 240000.0."""
    if not text:
        return None
    m = re.search(r"([\d.]+(?:,\d+)?)\s*€", text)
    raw = m.group(1) if m else text
    raw = raw.strip().replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _extract_superficie_m2(text: str) -> Optional[float]:
    """Parse a free-text <li> item like '72 M2 Construidos' → 72.0."""
    if not text:
        return None
    m = re.search(r"([\d.,]+)\s*M2", text, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_habitaciones(text: str) -> Optional[int]:
    """Parse a free-text <li> item like '3 Dormitorios' → 3."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*Dormitor", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_banos(text: str) -> Optional[int]:
    """Parse a free-text <li> item like '1 Baños' → 1."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*Ba[ñn]o", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_planta(text: str) -> Optional[str]:
    """Parse a free-text <li> item like 'Planta baja' → 'baja', 'Planta 3' → '3'."""
    if not text:
        return None
    m = re.search(r"Planta\s+(\w+)", text, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _extract_caracteristicas_li_items(soup: BeautifulSoup) -> List[str]:
    """Extract the raw <li> text list from #inmueble2_caracteristicas_inmueble_container."""
    container = soup.select_one("#inmueble2_caracteristicas_inmueble_container")
    if not container:
        return []
    items: List[str] = []
    for li in container.find_all("li"):
        text = li.get_text(strip=True)
        if text:
            items.append(text)
    return items


def _extract_tipo(text: str) -> Optional[str]:
    """Extract property type from a title like 'Piso en venta' → 'piso'."""
    if not text:
        return None
    lower = text.lower()
    m = re.match(r"^([a-záéíóúñ]+(?:\s+r[uú]stica)?)", lower)
    if not m:
        return None
    tipo_raw = m.group(1).strip()
    return TIPO_MAP.get(tipo_raw)


def _extract_direccion(soup: BeautifulSoup) -> Optional[str]:
    """Extract the address line from #inmueble2_titulo2_subtitulo.

    The element contains a map button (#boton_modal_mapa) whose text
    ('map'/'mapa') must be excluded from the address.
    """
    p = soup.select_one("#inmueble2_titulo2_subtitulo")
    if not p:
        return None
    map_btn = p.select_one("#boton_modal_mapa")
    if map_btn:
        map_btn.decompose()
    text = p.get_text(strip=True)
    text = re.sub(r"\s*mapa?\s*$", "", text, flags=re.IGNORECASE)
    return text or None


def _extract_municipio(direccion: str) -> Optional[str]:
    """Extract municipio from the address line 'El Puerto de Santa María, PINAR ALTO'."""
    if not direccion:
        return None
    lower = direccion.lower()
    if "el puerto de santa maría" in lower or "el puerto de santa maria" in lower:
        return "El Puerto de Santa María"
    first = direccion.split(",")[0].strip()
    return first if first else None


def _extract_barrio(direccion: str) -> Optional[str]:
    """Extract barrio/zona from the address line after the municipio, if any."""
    if not direccion:
        return None
    if "," in direccion:
        zona = direccion.split(",", 1)[1].strip()
        if zona:
            return zona.title()
    return None


def _extract_descripcion(soup: BeautifulSoup) -> Optional[str]:
    """Concatenate #inmueble2_descripcion_aut and #inmueble2_datos_adicionales."""
    parts: List[str] = []
    for selector in ("#inmueble2_descripcion_aut", "#inmueble2_datos_adicionales"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                parts.append(text)
    if not parts:
        return None
    return " ".join(parts)[:2000]


def _extract_fotos_detail(soup: BeautifulSoup) -> List[str]:
    """Extract photo URLs from #carousel-img-principal img.img-gallery."""
    fotos: List[str] = []
    seen = set()
    carousel = soup.select_one("#carousel-img-principal")
    if not carousel:
        return fotos
    for img in carousel.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        base = src.split("?")[0]
        if base and base not in seen:
            seen.add(base)
            fotos.append(base)
    return fotos


def _extract_referencia(soup: BeautifulSoup) -> Optional[str]:
    """Extract the property reference from #referenceTop h4, e.g. '61-550'."""
    el = soup.select_one("#referenceTop h4")
    if not el:
        return None
    return el.get_text(strip=True) or None

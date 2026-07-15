"""Detail scraper for alonsaga.com."""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from .config import ScraperConfig
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alonsaga.com"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}


class AlonsagaScraper:
    """Detail scraper for Alonsaga Inmobiliaria."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {"url_original": url, "activa": True}

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

        # Sold detection
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title: h1 text as-is (the old "Alonsaga X - " prefix no longer appears)
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

        # Price: format "180.000 €" or "180.000€"
        price_match = re.search(r"([\d.]+(?:,\d+)?)\s*€", page_text)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Superficie: icon badge inside #inmueble2_caracteristicas
        superficie = _extract_superficie_m2(soup)
        if superficie is not None:
            data["superficie_m2"] = superficie

        # Habitaciones/banos: icon badges inside #inmueble2_caracteristicas
        habitaciones = _extract_room_count(soup, "fa-bed")
        if habitaciones is not None:
            data["habitaciones"] = habitaciones
        banos = _extract_room_count(soup, "fa-bath")
        if banos is not None:
            data["banos"] = banos

        # Fixed municipio
        data["municipio"] = "El Puerto de Santa María"

        # Property type from URL
        tipo = _extract_tipo_from_url(url)
        if tipo:
            data["tipo_propiedad"] = tipo

        # Photos
        property_id = _extract_property_id_from_url(url)
        if property_id:
            fotos = _extract_fotos(soup, property_id)
            if fotos:
                data["fotos"] = fotos

        # Description: alonsaga puts the full text in p#inmueble2_datos_adicionales
        desc = _extract_descripcion(soup)
        if desc:
            data["descripcion"] = desc

        # Zona fallback: URL first, then HTML
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price string: '180.000' → 180000.0, '250.000,50' → 250000.5"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _extract_tipo_from_url(url: str) -> Optional[str]:
    """Extract property type from URL path: /Venta-{Tipo}-{Municipio}-...-{id} → tipo (lowercase)"""
    m = re.search(r"/Venta-([A-Za-z]+)-", url)
    if m:
        return m.group(1).lower()
    return None


def _extract_property_id_from_url(url: str) -> Optional[str]:
    """Extract the numeric property id at the end of the detail URL."""
    m = re.search(r"-(\d+)/?$", url)
    return m.group(1) if m else None


def _extract_fotos(soup: BeautifulSoup, property_id: str) -> List[str]:
    """Return unique photo URLs belonging to this property (excludes 'similares' widget photos)."""
    marker = f"/wm/{property_id}_"
    seen = set()
    fotos = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if marker not in src:
            continue
        base = src.split("?")[0]
        if base not in seen:
            seen.add(base)
            fotos.append(base)
    return fotos


def _extract_room_count(soup: BeautifulSoup, icon_class: str) -> Optional[int]:
    """Read the numeric badge next to a feature icon inside #inmueble2_caracteristicas.

    Scoped to that container because the 'similares' widget further down the
    page reuses the same fa-bed/fa-bath icon classes for other properties.
    """
    container = soup.select_one("#inmueble2_caracteristicas")
    if not container:
        return None
    icon = container.select_one(f"i.{icon_class}")
    if not icon:
        return None
    span = icon.find_next_sibling("span")
    if not span:
        return None
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else None


def _extract_superficie_m2(soup: BeautifulSoup) -> Optional[float]:
    """Read the surface-area badge ('315 m<sup>2</sup>') inside #inmueble2_caracteristicas.

    The badge's "m²" uses a <sup> tag for the superscript 2, so it never
    appears as a literal "m²" string in page text — must be read from the
    span next to the fa-vector-square icon instead.
    """
    container = soup.select_one("#inmueble2_caracteristicas")
    if not container:
        return None
    icon = container.select_one("i.fa-vector-square")
    if not icon:
        return None
    span = icon.find_next_sibling("span")
    if not span:
        return None
    m = re.match(r"([\d.,]+)\s*m", span.get_text(strip=True))
    if not m:
        return None
    val = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_descripcion(soup: BeautifulSoup) -> Optional[str]:
    """Alonsaga puts the full description text in p#inmueble2_datos_adicionales."""
    p = soup.select_one("p#inmueble2_datos_adicionales")
    if not p:
        return None
    text = p.get_text(strip=True)
    return text[:2000] if len(text) > 50 else None

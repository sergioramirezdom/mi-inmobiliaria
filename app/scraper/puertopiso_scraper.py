"""Detail scraper for puertopiso.com."""

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

BASE_URL = "https://www.puertopiso.com/buscador/"

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
    "oficina": "oficina",
    "edificio": "edificio",
    "duplex": "dúplex",
    "dúplex": "dúplex",
    "atico": "ático",
    "ático": "ático",
    "apartamento": "apartamento",
    "estudio": "estudio",
}


class PuertoPisoScraper:
    """Detail scraper for puertopiso.com."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    def canonicalize_url(self, url: str) -> str:
        return _fix_url(url)

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        url = _fix_url(url)

        data: Dict[str, Any] = {
            "url_original": url,
            "activa": True,
            "municipio": "El Puerto de Santa María",
            "provincia": "Cádiz",
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=True) as client:
                response = await client.get(
                    url, headers=BROWSER_HEADERS, timeout=self.config.timeout
                )
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
            err = str(e)
            if "404" in err or "Not Found" in err:
                data["activa"] = False
                data["estado"] = "No disponible"
            else:
                logger.warning(f"Error fetching {url}: {e}")
            return data

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        lower_text = page_text.lower()

        # Sold detection
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in lower_text[:3000]:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title and price from div.uno h4 elements
        uno = soup.find("div", class_="uno")
        if uno:
            h4s = uno.find_all("h4")
            if h4s:
                data["titulo"] = h4s[0].get_text(strip=True)
            if len(h4s) >= 2:
                price_text = h4s[1].get_text(strip=True)
                m = re.search(r"([\d.,]+)€", price_text.replace(" ", ""))
                if m:
                    data["precio"] = _parse_price_eu(m.group(1))

        # If title not found in div.uno, try fallback
        if "titulo" not in data:
            h1 = soup.find("h1")
            if h1:
                data["titulo"] = h1.get_text(strip=True)

        # Surface, rooms, bathrooms, type, zone — from page text
        m = re.search(r"Superficie [ÚU]til[:\s]+([\d.,]+)\s*m2", page_text, re.IGNORECASE)
        if not m:
            m = re.search(r"Superficie[:\s]+([\d.,]+)\s*m2", page_text, re.IGNORECASE)
        if m:
            data["superficie_m2"] = _parse_float_eu(m.group(1))

        m = re.search(r"Habitaciones[:\s]+(\d+)", page_text, re.IGNORECASE)
        if m:
            data["habitaciones"] = int(m.group(1))

        m = re.search(r"Ba[ñn]os[:\s]+(\d+)", page_text, re.IGNORECASE)
        if m:
            data["banos"] = int(m.group(1))

        m = re.search(r"Tipo de Propiedad[:\s]+(\w+)", page_text, re.IGNORECASE)
        if m:
            tipo_raw = m.group(1).lower()
            data["tipo_propiedad"] = TIPO_MAP.get(tipo_raw, tipo_raw)

        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        # Boolean amenities
        amenity_map = {
            "ascensor": "ascensor",
            "garaje": "garaje",
            "garage": "garaje",
            "trastero": "trastero",
            "terraza": "terraza",
            "balcón": "balcon",
            "balcon": "balcon",
            "piscina": "piscina",
            "aire acondicionado": "aire_acondicionado",
        }
        for keyword, field in amenity_map.items():
            if keyword in lower_text and field not in data:
                data[field] = True

        # Description: first justified paragraph with enough text
        col_attr = soup.find("div", class_="column_attr")
        if col_attr:
            for p in col_attr.find_all("p"):
                style = p.get("style", "")
                text = p.get_text(strip=True)
                if "justify" in style and len(text) > 80:
                    data["descripcion"] = text[:2000]
                    break

        # Images: from div.fotorama anchor hrefs
        seen: set = set()
        fotos: List[str] = []
        fotorama = soup.find("div", class_="fotorama")
        if fotorama:
            for a in fotorama.find_all("a", href=True):
                href = a["href"]
                if href and href not in seen:
                    seen.add(href)
                    fotos.append(href)
        if fotos:
            data["fotos"] = fotos

        return data


def _fix_url(url: str) -> str:
    """Canonicalize puertopiso.com property URL to stable form: /buscador/inmueble.php?id=XXXXX.

    The listing page appends variable pagination params (pag, tpag2, filtrar, etc.)
    that change between scraping runs, causing hash mismatches for the same property.
    Keeping only the id param produces a stable canonical URL.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    if not url.startswith("http"):
        return BASE_URL + url.lstrip("/")

    # Insert /buscador/ if GenericScraper resolved the path without it
    if "puertopiso.com" in url and "/buscador/" not in url:
        url = url.replace("puertopiso.com/", "puertopiso.com/buscador/")

    # Strip all query params except 'id'
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "id" in params:
        canonical_query = urlencode({"id": params["id"][0]})
        url = urlunparse(parsed._replace(query=canonical_query))

    return url


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price string: '155.000' → 155000.0"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_float_eu(text: str) -> Optional[float]:
    """Parse European decimal: '69,84' or '69.84' → 69.84"""
    text = text.strip()
    # If both . and , present, the . is thousand separator
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None

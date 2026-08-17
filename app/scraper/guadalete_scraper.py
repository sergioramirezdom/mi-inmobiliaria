"""Detail scraper for inmobiliariaguadalete.com."""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from .config import ScraperConfig
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html

from .foto_extractor import extraer_fotos

logger = logging.getLogger(__name__)

BASE_URL = "https://www.inmobiliariaguadalete.com"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}


class GuadaleteScraper:
    """Detail scraper for Inmobiliaria Guadalete."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {"url_original": url, "activa": True}

        # Skip category listing pages (no property data)
        # Property URLs always end with -igNNNN, category pages end with /
        if not re.search(r"-ig\d+", url):
            logger.debug(f"Skipping non-property URL: {url}")
            return data

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

        # Sold detection
        lower_text = page_text.lower()
        for keyword in ("vendido", "vendida", "reservado", "reservada", "alquilado"):
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title: strip "IG1234 - " prefix
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            title = re.sub(r"^IG\d+\s*[-–]\s*", "", title, flags=re.IGNORECASE)
            data["titulo"] = title

        # Price: search in parsed text (avoids &euro; encoding issues)
        price_match = re.search(r"€\s*([\d.,]+)", page_text)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Characteristics: format is "N Label" e.g. "2 Habitaciones, 1 Baños, 90 sqmt"
        # Also handles "Label: N" format in structured section
        patterns = [
            (r"(\d+)\s*[Cc]amas?", "habitaciones"),
            (r"(\d+)\s*[Hh]abitaciones?", "habitaciones"),
            (r"(\d+)\s*[Bb]años?", "banos"),
            (r"([\d.,]+)\s*sqmt", "superficie_m2"),
            (r"([\d.,]+)\s*m²", "superficie_m2"),
            (r"[Mm]etro[s]?\s+cuadrado[s]?\s*[:\-]\s*([\d.,]+)", "superficie_m2"),
            (r"[Cc]amas?\s*[:\-]\s*(\d+)", "habitaciones"),
            (r"[Hh]abitaciones?\s*[:\-]\s*(\d+)", "habitaciones"),
            (r"[Bb]años?\s*[:\-]\s*(\d+)", "banos"),
        ]
        for pattern, field_name in patterns:
            if field_name in data:
                continue
            match = re.search(pattern, page_text)
            if match:
                val = match.group(1).replace(".", "").replace(",", ".")
                try:
                    data[field_name] = int(float(val)) if field_name in ("habitaciones", "banos") else float(val)
                except (ValueError, TypeError):
                    pass

        data["municipio"] = "El Puerto de Santa María"

        # Property type from URL
        url_match = re.search(r"/inmuebles/([^/]+)/", url)
        if url_match:
            tipo_map = {
                "pisos": "piso", "chalets": "chalet", "casas": "casa",
                "locales": "local", "garajes": "garaje", "oficinas": "oficina",
                "terrenos": "terreno", "fincas": "finca",
            }
            data["tipo_propiedad"] = tipo_map.get(url_match.group(1), url_match.group(1))

        # Description
        for tag in soup.find_all(["div", "section", "p"]):
            text = tag.get_text(strip=True)
            if len(text) > 150 and not tag.find_all(["div", "section"]):
                data.setdefault("descripcion", text[:2000])
                break

        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        if not data.get("fotos"):
            fotos = extraer_fotos(html, url=url)
            if fotos:
                data["fotos"] = fotos

        return data


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price: 200.000,00 → 200000.0"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_int(text: str) -> Optional[int]:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None

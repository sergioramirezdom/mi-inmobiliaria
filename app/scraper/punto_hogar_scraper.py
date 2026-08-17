"""Detail scraper for puntohogarinmobiliaria.com."""

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
from .operacion_detector import detectar_operacion, es_garaje

logger = logging.getLogger(__name__)

BASE_URL = "https://www.puntohogarinmobiliaria.com"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}


class PuntoHogarScraper:
    """Detail scraper for Punto Hogar Inmobiliaria."""

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

        # Sold detection
        lower_text = page_text.lower()
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Price
        price_el = soup.select_one(".precio-destacado")
        if price_el:
            data["precio"] = _parse_price(price_el.get_text(strip=True))

        # Characteristics: div.detalle-item > span.detalle-label + span.detalle-valor
        for item in soup.select(".detalle-item"):
            label_el = item.select_one(".detalle-label")
            valor_el = item.select_one(".detalle-valor")
            if not label_el or not valor_el:
                continue
            label = label_el.get_text(strip=True).lower()
            value = valor_el.get_text(strip=True)

            if "superficie" in label or "m²" in label or "tamaño" in label:
                data["superficie_m2"] = _parse_float(value)
            elif "dormitorio" in label or "habitaci" in label:
                data["habitaciones"] = _parse_int(value)
            elif "baño" in label:
                data["banos"] = _parse_int(value)
            elif "garaje" in label or "parking" in label:
                v = value.lower()
                data["garaje"] = v not in ("no", "")
            elif "tipo" in label:
                data["tipo_propiedad"] = value.lower()
            elif "planta" in label:
                data["planta"] = _parse_int(value)

        # Build title from scraped tipo (site has no useful title element)
        tipo = data.get("tipo_propiedad", "Inmueble").capitalize()
        data["titulo"] = f"{tipo} en El Puerto de Santa María"

        # Detect operation type and garaje
        operacion = detectar_operacion(
            titulo=data.get("titulo"), precio=data.get("precio"), url=url
        )
        if operacion:
            data["tipo_operacion"] = operacion
            if operacion == "alquiler":
                data["activa"] = False
                data["estado"] = "Alquiler"
                return data
        if es_garaje(titulo=data.get("titulo"), tipo_propiedad=data.get("tipo_propiedad"), url=url):
            data["tipo_propiedad"] = "garaje"

        # Description — look for a text block after a "Descripción" heading
        desc_heading = soup.find(string=re.compile(r"[Dd]escripci[oó]n"))
        if desc_heading:
            parent = desc_heading.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    text = sibling.get_text(" ", strip=True)
                    if len(text) > 20:
                        data["descripcion"] = text[:2000]

        muni_el = soup.select_one("p#municipio")
        data["municipio"] = muni_el.get_text(strip=True) if muni_el else "El Puerto de Santa María"

        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        if not data.get("fotos"):
            fotos = extraer_fotos(html, url=url)
            if fotos:
                data["fotos"] = fotos

        return data


def _parse_price(text: str) -> Optional[float]:
    text = text.replace(".", "").replace(",", ".").replace("€", "").replace("/mes", "").strip()
    try:
        return float(re.sub(r"[^\d.]", "", text))
    except (ValueError, TypeError):
        return None


def _parse_float(text: str) -> Optional[float]:
    match = re.search(r"[\d.,]+", text)
    if not match:
        return None
    value = match.group()
    # Detect format: if only dots and last segment has ≠3 digits → dot is decimal (e.g. "110.58")
    # If last segment has 3 digits → dot is thousands separator (e.g. "1.234")
    if "," in value and "." in value:
        # Both separators: EU format "1.234,56" → dot=thousands, comma=decimal
        value = value.replace(".", "").replace(",", ".")
    elif "." in value:
        parts = value.split(".")
        if len(parts[-1]) == 3:
            value = value.replace(".", "")  # thousands: "1.000" → "1000"
        # else dot is decimal: "110.58" → keep as-is
    elif "," in value:
        parts = value.split(",")
        if len(parts[-1]) == 3:
            value = value.replace(",", "")  # thousands: "1,000" → "1000"
        else:
            value = value.replace(",", ".")  # decimal: "110,58" → "110.58"
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(text: str) -> Optional[int]:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None

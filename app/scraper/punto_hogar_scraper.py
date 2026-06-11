"""Detail scraper for puntohogarinmobiliaria.com."""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, Any

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from .config import ScraperConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://www.puntohogarinmobiliaria.com"


class PuntoHogarScraper:
    """Detail scraper for Punto Hogar Inmobiliaria."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {"url_original": url, "activa": True}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": self.config.user_agent},
                    timeout=self.config.timeout,
                    follow_redirects=True,
                )
                if response.status_code != 200:
                    return data
                html = response.text
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return data

        soup = BeautifulSoup(html, "lxml")

        # Sold detection
        page_text = soup.get_text(" ", strip=True).lower()
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in page_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

        # Characteristics table: <tr><td>Label</td><td>Value</td></tr>
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)

            if "precio" in label:
                data["precio"] = _parse_price(value)
            elif "tamaño" in label or "superficie" in label:
                data["superficie_m2"] = _parse_float(value)
            elif "dormitorio" in label or "habitacion" in label:
                data["habitaciones"] = _parse_int(value)
            elif "baño" in label:
                data["banos"] = _parse_int(value)
            elif "garaje" in label:
                data["garaje"] = "sí" in value.lower() or "si" in value.lower()
            elif "año" in label and "construc" in label:
                data["estado"] = f"Año construcción: {value}"
            elif "tipo" in label:
                data["tipo_propiedad"] = value.lower()
            elif "planta" in label:
                data["planta"] = _parse_int(value)
            elif "referencia" in label or "ref" in label:
                pass  # skip reference number

        # Description
        desc_heading = soup.find(string=re.compile(r"[Dd]escripci[oó]n"))
        if desc_heading:
            parent = desc_heading.find_parent()
            if parent:
                sibling = parent.find_next_sibling()
                if sibling:
                    data["descripcion"] = sibling.get_text(strip=True)[:2000]

        # Location: extract municipality from page
        location_patterns = [
            r"El Puerto de Santa Mar[íi]a",
            r"Puerto de Santa Mar[íi]a",
        ]
        for pattern in location_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                data["municipio"] = "El Puerto de Santa María"
                break

        return data


def _parse_price(text: str) -> float | None:
    text = text.replace(".", "").replace(",", ".").replace("€", "").replace("/mes", "").strip()
    try:
        return float(re.sub(r"[^\d.]", "", text))
    except (ValueError, TypeError):
        return None


def _parse_float(text: str) -> float | None:
    match = re.search(r"[\d.,]+", text)
    if not match:
        return None
    value = match.group().replace(".", "").replace(",", ".")
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None

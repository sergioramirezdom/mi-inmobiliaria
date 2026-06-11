"""Detail scraper for inmobiliariaguadalete.com."""

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

BASE_URL = "https://www.inmobiliariaguadalete.com"


class GuadaleteScraper:
    """Detail scraper for Inmobiliaria Guadalete."""

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
        for keyword in ("vendido", "vendida", "reservado", "reservada", "alquilado"):
            if keyword in page_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title: strip "IG1234 - " prefix if present
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            title = re.sub(r"^IG\d+\s*[-–]\s*", "", title, flags=re.IGNORECASE)
            data["titulo"] = title

        # Price: look for € pattern in page
        price_match = re.search(r"€\s*([\d.,]+)", html)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Characteristics: format is "N Label" e.g. "2 Habitaciones, 1 Baños, 90 sqmt"
        full_text = soup.get_text(" ", strip=True)
        label_map = [
            (r"(\d+)\s*[Cc]amas?", "habitaciones"),
            (r"(\d+)\s*[Hh]abitaciones?", "habitaciones"),
            (r"(\d+)\s*[Bb]años?", "banos"),
            (r"([\d.,]+)\s*sqmt", "superficie_m2"),
            (r"([\d.,]+)\s*m²", "superficie_m2"),
            (r"[Mm]etro[s]?\s+cuadrado[s]?\s*[:\-]\s*([\d.,]+)", "superficie_m2"),
        ]
        for pattern, field_name in label_map:
            match = re.search(pattern, full_text)
            if match and field_name not in data:
                val = match.group(1).replace(",", ".")
                try:
                    data[field_name] = int(float(val)) if field_name in ("habitaciones", "banos") else float(val)
                except (ValueError, TypeError):
                    pass

        # Location
        data["municipio"] = "El Puerto de Santa María"

        # Description
        for tag in soup.find_all(["div", "section", "article"]):
            text = tag.get_text(strip=True)
            if len(text) > 150 and not tag.find_all(["div", "article"]):
                data.setdefault("descripcion", text[:2000])
                break

        # Property type from URL
        url_match = re.search(r"/inmuebles/([^/]+)/", url)
        if url_match:
            tipo_map = {
                "pisos": "piso", "chalets": "chalet", "casas": "casa",
                "locales": "local", "garajes": "garaje", "oficinas": "oficina",
                "terrenos": "terreno", "fincas": "finca",
            }
            data["tipo_propiedad"] = tipo_map.get(url_match.group(1), url_match.group(1))

        return data


def _parse_price_eu(text: str) -> float | None:
    """Parse European price format: 200.000,00 → 200000.0"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_int(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None

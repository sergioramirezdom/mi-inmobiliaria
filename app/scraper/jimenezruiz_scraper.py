"""Detail scraper for jimenezruiz.com."""

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

BASE_URL = "https://www.jimenezruiz.com"

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
    "atico": "ático",
}


class JimenezRuizScraper:
    """Detail scraper for Jiménez Ruiz inmobiliaria (jimenezruiz.com)."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {
            "url_original": url,
            "activa": True,
            "municipio": "El Puerto de Santa María",
            "provincia": "Cádiz",
        }

        # Extract type and zone from URL pattern:
        # /Venta-Tipo-El-Puerto-de-Santa-Maria-Zona-ID
        url_match = re.search(
            r"/Venta-(\w+)-El-Puerto-de-Santa-Maria-(.+)-(\d+)$",
            url,
            re.IGNORECASE,
        )
        if url_match:
            tipo_raw = url_match.group(1).lower()
            data["tipo_propiedad"] = TIPO_MAP.get(tipo_raw, tipo_raw)
            data["barrio"] = url_match.group(2).replace("-", " ")

        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
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
            logger.warning(f"Error fetching {url}: {e}")
            return data

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)

        # Sold detection (check only in the first ~3000 chars of text)
        lower_text = page_text.lower()
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in lower_text[:3000]:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Price: find first reasonable price not from "similar properties" section
        similar_prices: set = set()
        for el in soup.find_all(class_="inmuebles_similares_precio"):
            m = re.search(r"([\d.,]+)\s*€", el.get_text())
            if m:
                similar_prices.add(m.group(1).strip())

        for m in re.finditer(r"([\d.,]+)\s*€", page_text):
            val = m.group(1).strip()
            if val not in similar_prices:
                price = _parse_price_eu(val)
                if price and price > 10_000:
                    data["precio"] = price
                    break

        # Structured features from <ul> with <li class="mb-2"> items
        for ul in soup.find_all("ul"):
            items = [li.get_text(strip=True) for li in ul.find_all("li")]
            if not any("Dormitor" in t or "M2" in t or "Baño" in t for t in items):
                continue
            for item in items:
                il = item.lower()
                m2 = re.search(r"([\d.,]+)\s*m2", il)
                if m2 and "superficie_m2" not in data:
                    try:
                        data["superficie_m2"] = float(m2.group(1).replace(".", "").replace(",", "."))
                    except ValueError:
                        pass
                dorm = re.search(r"(\d+)\s*dormitor", il)
                if dorm and "habitaciones" not in data:
                    data["habitaciones"] = int(dorm.group(1))
                bano = re.search(r"(\d+)\s*baño", il)
                if bano and "banos" not in data:
                    data["banos"] = int(bano.group(1))
                planta = re.search(r"planta\s*(\d+)", il)
                if planta and "planta" not in data:
                    data["planta"] = int(planta.group(1))
                year = re.match(r"^(\d{4})$", item.strip())
                if year and "year_built" not in data:
                    data["year_built"] = int(year.group(1))
                for estado_kw in ("buen estado", "semi reformado", "reformado", "a reformar", "nuevo"):
                    if estado_kw in il and "estado" not in data:
                        data["estado"] = item.strip()
                        break
            break  # Only the first matching ul

        # Boolean amenities from full page text
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
            "amueblado": "amueblado",
            "amueblada": "amueblado",
        }
        for keyword, field in amenity_map.items():
            if keyword in lower_text and field not in data:
                data[field] = True

        # Description: find the main descriptive paragraph
        for el in soup.find_all(["p", "div"]):
            text = el.get_text(strip=True)
            if 150 < len(text) < 3000 and not el.find_all(["p", "div", "ul"]):
                if any(kw in text.lower() for kw in ["m²", "m2", "dormitor", "ubicad", "inmueble", "propiedad"]):
                    data["descripcion"] = text[:2000]
                    break

        # Images: unique URLs from inmoserver CDN
        seen: set = set()
        fotos: List[str] = []
        for img in soup.find_all("img", src=re.compile(r"inmoserver|/fotos/")):
            src = img.get("src", "")
            if src and src not in seen:
                seen.add(src)
                fotos.append(src)
        if fotos:
            data["fotos"] = fotos

        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        # Detect operation type and garaje
        operacion = detectar_operacion(
            titulo=data.get("titulo"), precio=data.get("precio"), url=url,
            descripcion=data.get("descripcion"),
        )
        if operacion:
            data["tipo_operacion"] = operacion
            if operacion == "alquiler":
                data["activa"] = False
                data["estado"] = "Alquiler"
                return data
        if es_garaje(titulo=data.get("titulo"), tipo_propiedad=data.get("tipo_propiedad"), url=url):
            data["tipo_propiedad"] = "garaje"

        return data


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price: '200.000' → 200000.0"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None

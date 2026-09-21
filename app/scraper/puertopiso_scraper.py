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
from .geo_utils import coords_from_gmaps_center
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
from .operacion_detector import detectar_operacion, es_garaje
from .estado_venta import detect_estado_venta
from .number_parsing import parse_eu_number

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

        # Sold detection (status badge / title only, see estado_venta)
        estado = detect_estado_venta(soup)
        if estado:
            data["activa"] = False
            data["estado"] = estado
            return data

        # Title and price from div.uno h4 elements
        uno = soup.find("div", class_="uno")
        if uno:
            h4s = uno.find_all("h4")
            if h4s:
                data["titulo"] = h4s[0].get_text(strip=True)
            # Price: first h4 after the title showing an amount (\s also
            # strips non-breaking spaces before the euro sign)
            for h4 in h4s[1:]:
                m = re.search(r"(\d[\d.,]*)€", re.sub(r"\s+", "", h4.get_text()))
                precio = parse_eu_number(m.group(1)) if m else None
                if precio is not None:
                    data["precio"] = precio
                    break

        # If title not found in div.uno, try fallback
        if "titulo" not in data:
            h1 = soup.find("h1")
            if h1:
                data["titulo"] = h1.get_text(strip=True)

        # Surface, rooms, bathrooms, type, zone — from page text
        # Built area goes to superficie_m2 (as in every other scraper); the
        # useful area is kept apart and never stands in for it.
        m = re.search(r"Superficie[:\s]+(\d[\d.,]*)\s*m[²2]", page_text, re.IGNORECASE)
        superficie = parse_eu_number(m.group(1)) if m else None
        if superficie is not None:
            data["superficie_m2"] = superficie
        m = re.search(r"Superficie [ÚU]til[:\s]+(\d[\d.,]*)\s*m[²2]", page_text, re.IGNORECASE)
        superficie_util = parse_eu_number(m.group(1)) if m else None
        if superficie_util is not None:
            data["superficie_util_m2"] = superficie_util

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
        # Scoped to the attributes column when present, so related-listing
        # widgets elsewhere on the page cannot set flags.
        col_attr = soup.find("div", class_="column_attr")
        amenity_text = col_attr.get_text(" ", strip=True).lower() if col_attr else lower_text
        affirmed: set = set()
        negated: set = set()
        for keyword, field in amenity_map.items():
            mention = _amenity_mention(amenity_text, keyword)
            if mention is True:
                affirmed.add(field)
            elif mention is False:
                negated.add(field)
        for field in affirmed - negated:
            if field not in data:
                data[field] = True

        # Description: first justified paragraph with enough text
        # (fallback: first long paragraph when no justified one exists)
        if col_attr:
            paragraphs = col_attr.find_all("p")
            for require_justify in (True, False):
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if len(text) > 80 and (not require_justify or "justify" in p.get("style", "")):
                        data["descripcion"] = text[:2000]
                        break
                if "descripcion" in data:
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

        # Approximate map coordinates (Google Maps initMap center)
        lat, lng = coords_from_gmaps_center(html)
        if lat is not None and lng is not None:
            data["latitud"] = lat
            data["longitud"] = lng
            data["ubicacion_aproximada"] = True

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


# "sin ascensor", "sin plaza de garaje", "no dispone de ascensor"...
_NEGATION_BEFORE = re.compile(r"(?:\bsin|\bno\s+(?:tiene|dispone\s+de|hay|cuenta\s+con))\s+(?:\w+\s+){0,2}$")


def _amenity_mention(text: str, keyword: str) -> Optional[bool]:
    """True if `keyword` is mentioned affirmatively, False if any mention is
    negated ("sin ascensor"), None if it does not appear. Text is lowercase."""
    found = False
    for m in re.finditer(rf"\b{re.escape(keyword)}", text):
        if _NEGATION_BEFORE.search(text[max(0, m.start() - 40):m.start()]):
            return False
        found = True
    return True if found else None

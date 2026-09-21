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
from .foto_extractor import extraer_fotos
from .geo_utils import coords_from_cargar_mapa
from .number_parsing import parse_eu_number
from .operacion_detector import detectar_operacion, es_garaje
from .estado_venta import SECONDARY_REGION_RE, detect_estado_venta
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

        # Sold detection (status badge / title only, see estado_venta)
        estado = detect_estado_venta(soup)
        if estado:
            data["activa"] = False
            data["estado"] = estado
            return data

        # Everything below reads the main ficha only: the "similares" widget,
        # menus and footer carry other listings' prices, photos and amenities.
        ficha = _ficha_scope(soup)

        h1 = ficha.find("h1")
        if h1 and h1.get_text(strip=True):
            data["titulo"] = h1.get_text(" ", strip=True)

        precio = _extract_precio(ficha)
        if precio:
            data["precio"] = precio

        # Structured features from <ul> with <li class="mb-2"> items
        features: List[str] = []
        for ul in ficha.find_all("ul"):
            items = [li.get_text(strip=True) for li in ul.find_all("li")]
            if not any("Dormitor" in t or "M2" in t or "Baño" in t for t in items):
                continue
            features = items
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
                planta = re.search(r"planta\s*(\d+|baja)", il)
                if planta and "planta" not in data:
                    data["planta"] = 0 if planta.group(1) == "baja" else int(planta.group(1))
                for estado_kw in ("buen estado", "semi reformado", "reformado", "a reformar", "nuevo"):
                    if estado_kw in il and "estado" not in data:
                        data["estado"] = item.strip()
                        break
            break  # Only the first matching ul

        # Boolean amenities from the features list only ("sin ascensor" never sets True)
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
        affirmed: set = set()
        negated: set = set()
        for item in features:
            il = item.lower()
            for keyword, field in amenity_map.items():
                if re.search(rf"\b{keyword}", il):
                    (negated if _NEGATED_ITEM_RE.match(il) else affirmed).add(field)
        for field in affirmed - negated:
            data.setdefault(field, True)

        # Description: find the main descriptive paragraph
        for el in ficha.find_all(["p", "div"]):
            text = el.get_text(strip=True)
            if 150 < len(text) < 3000 and not el.find_all(["p", "div", "ul"]):
                if any(kw in text.lower() for kw in ["m²", "m2", "dormitor", "ubicad", "inmueble", "propiedad"]):
                    data["descripcion"] = text[:2000]
                    break

        # Images: only this property's (InmoServer names them "<id>_<hash>.jpg")
        fotos = _extract_fotos(ficha, url)
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

        # Approximate map coordinates (InmoServer JS)
        lat, lng = coords_from_cargar_mapa(html)
        if lat is not None and lng is not None:
            data["latitud"] = lat
            data["longitud"] = lng
            data["ubicacion_aproximada"] = True

        return data


# A features item that says the property lacks the amenity ("Sin trastero").
_NEGATED_ITEM_RE = re.compile(r"^\s*(?:sin|no)\b")
_LEADING_PRICE_RE = re.compile(r"^\s*([\d.,]+)\s*€")
_BARE_PRICE_RE = re.compile(r"^\s*[\d.,]+\s*€\s*$")
_PROPERTY_ID_RE = re.compile(r"-(\d+)/?(?:[?#].*)?$")


def _ficha_scope(soup: BeautifulSoup) -> BeautifulSoup:
    """A copy of the main ficha without nav/footer/"similares" regions.

    Uses the InmoServer ficha container (#inmueble2, #inmueble1 on some skins)
    when present, else the whole page; the secondary regions are dropped in
    both cases because the widget may sit inside the container.
    """
    container = soup.select_one("#inmueble2, #inmueble1") or soup
    ficha = BeautifulSoup(str(container), "html.parser")
    for el in ficha.find_all(True):
        if el.decomposed:
            continue
        attrs = " ".join([" ".join(el.get("class") or []), el.get("id") or ""])
        if el.name in ("nav", "footer", "aside", "script", "style") or (
            attrs.strip() and SECONDARY_REGION_RE.search(attrs)
        ):
            el.decompose()
    return ficha


def _extract_precio(ficha: BeautifulSoup) -> Optional[float]:
    """Price of this property: the dedicated price element, else the first bare
    price of the ficha. None rather than a guess when neither parses."""
    for el in ficha.select("#inmueble2_precio, #inmueble1_precio, [class*='precio' i], [id*='precio' i]"):
        m = _LEADING_PRICE_RE.match(el.get_text(" ", strip=True))
        if m:
            return parse_eu_number(m.group(1))
    node = ficha.find(string=_BARE_PRICE_RE)
    return parse_eu_number(str(node).replace("€", "")) if node else None


def _extract_fotos(ficha: BeautifulSoup, url: str) -> List[str]:
    """Photos of this property, made absolute. With a property id in the URL
    only its own images count; better no photos than another listing's."""
    fotos = extraer_fotos(str(ficha), url=url)
    m = _PROPERTY_ID_RE.search(url)
    if not m:
        return fotos
    marker = f"/{m.group(1)}_"
    return [f for f in fotos if marker in f]

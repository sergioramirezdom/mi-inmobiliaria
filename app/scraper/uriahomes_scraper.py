"""Detail scraper for uriahomesinmobiliaria.com (InmoServer CMS).

UriaHomes uses the same InmoServer CMS as Alonsaga. The detail page shares
the #inmueble2_* selectors, the fa-vector-square / fa-bed / fa-bath icon
badges and the carousel structure, so most extraction helpers mirror the
alonsaga_scraper.py ones.

The main difference: this site responds in ENGLISH by default, so the quick
stats and the property-features list use English labels ("Flat", "bedrooms",
"Reformed", "Kitchen equipped"...). Those labels are mapped back to Spanish
for consistency with the other scrapers.
"""

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

from .foto_extractor import extraer_fotos
from .operacion_detector import detectar_operacion, es_garaje

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uriahomesinmobiliaria.com"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}

# English feature labels (as served by the site) → Spanish equivalents.
_EN_FEATURE_MAP = {
    "built": "construido",
    "bedrooms": "habitaciones",
    "bathrooms": "baños",
    "reformed": "reformado",
    "reformado": "reformado",
    "free": "libre",
    "outward": "exterior",
    "kitchen equipped": "cocina equipada",
    "kitchen furnished": "cocina amueblada",
    "fitted kitchen": "cocina amueblada",
    "furnished": "amueblado",
    "unfurnished": "sin amueblar",
    "air conditioning": "aire acondicionado",
    "elevator": "ascensor",
    "lift": "ascensor",
    "terrace": "terraza",
    "balcony": "balcón",
    "garage": "garaje",
    "parking": "garaje",
    "storage room": "trastero",
    "storage": "trastero",
    "pool": "piscina",
    "swimming pool": "piscina",
    "garden": "jardín",
    "heating": "calefacción",
    "gallery": "galería",
    "armored door": "puerta blindada",
    "security door": "puerta blindada",
    "exterior": "exterior",
    "interior": "interior",
    "new building": "obra nueva",
    "with elevator": "con ascensor",
    "ground floor": "planta baja",
    "floor baja": "planta baja",
    "low floor": "planta baja",
    "penthouse": "ático",
    "fitted wardrobes": "armarios empotrados",
    "wardrobes": "armarios empotrados",
    "energetic certificate": "certificado energético",
    "semi-detached": "adosado",
    "detached": "independiente",
}

# Keywords that indicate a property is sold/reserved/rented on this site
# (checked against the lowercased page text).
_SOLD_KEYWORDS = ("vendido", "vendida", "reservado", "reservada", "alquilado", "alquilada")


class UriaHomesScraper:
    """Detail scraper for UriaHomes Inmobiliaria (InmoServer CMS)."""

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

        # Sold/reserved/rented detection
        for keyword in _SOLD_KEYWORDS:
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title: h1 → "For sale of flat in El Puerto de Santa María, EL JUNCAL"
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

        # Price: format "180.000 €"
        price_match = re.search(r"([\d.]+(?:,\d+)?)\s*€", page_text)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Detect operation type and garaje (common helper)
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

        # Superficie: fa-vector-square badge inside #inmueble2_caracteristicas
        superficie = _extract_superficie_m2(soup)
        if superficie is not None:
            data["superficie_m2"] = superficie

        # Habitaciones / banos: fa-bed / fa-bath badges
        habitaciones = _extract_room_count(soup, "fa-bed")
        if habitaciones is not None:
            data["habitaciones"] = habitaciones
        banos = _extract_room_count(soup, "fa-bath")
        if banos is not None:
            data["banos"] = banos

        # Type: #inmueble2_titulo2 (h4) → "Flat for sale" (mapped to Spanish)
        tipo = _extract_tipo(soup)
        if tipo:
            data["tipo_propiedad"] = tipo

        # Address / barrio / municipio from #inmueble2_titulo2_subtitulo
        # (e.g. "El Puerto de Santa María, EL JUNCAL")
        direccion = _extract_direccion(soup)
        if direccion:
            data["direccion"] = direccion
            data.setdefault("municipio", _extract_municipio(direccion))
            if not data.get("barrio"):
                data["barrio"] = _extract_barrio(direccion)

        if not data.get("municipio"):
            data["municipio"] = "El Puerto de Santa María"

        # Description: #inmueble2_descripcion_aut then #inmueble2_datos_adicionales
        desc = _extract_descripcion(soup)
        if desc:
            data["descripcion"] = desc

        # Amenidades: property features list, mapped from English to Spanish
        amenidades = _extract_caracteristicas(soup)
        if amenidades:
            data["amenidades"] = amenidades

        # Energy certificate: #certificado_energetico_estado span → "In process"
        energia = _extract_energia(soup)
        if energia:
            data["certificado_energetico"] = energia

        # Reference: #referenceTop h4 → "220-UH0216"
        referencia = _extract_referencia(soup)
        if referencia:
            data["referencia"] = referencia

        # Photos: #carousel-img-principal .carousel-item img (img-gallery)
        fotos = _extract_fotos_detail(soup)
        if fotos:
            data["fotos"] = fotos

        # Photos fallback: generic extractor
        if not data.get("fotos"):
            fotos = extraer_fotos(html, url=url)
            if fotos:
                data["fotos"] = fotos

        # Coordinates from JavaScript
        lat, lng = _extract_coords_from_js(html)
        if lat is not None and lng is not None:
            data["latitud"] = lat
            data["longitud"] = lng

        # Zona fallback: URL first, then HTML
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data


# ── Module-level helpers ──────────────────────────────────────────────────────


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price string: '180.000' → 180000.0, '250.000,50' → 250000.5"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _extract_superficie_m2(soup: BeautifulSoup) -> Optional[float]:
    """Read the surface-area badge ('70 m<sup>2</sup>') inside #inmueble2_caracteristicas."""
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


def _extract_room_count(soup: BeautifulSoup, icon_class: str) -> Optional[int]:
    """Read the numeric badge next to a feature icon inside #inmueble2_caracteristicas.

    Scoped to that container because the 'similares' widget further down the
    page reuses the same fa-bed / fa-bath icon classes for other properties.
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


def _extract_tipo(soup: BeautifulSoup) -> Optional[str]:
    """Extract property type from #inmueble2_titulo2 (h4), e.g. 'Flat for sale' → 'piso'."""
    h4 = soup.select_one("#inmueble2_titulo2")
    if not h4:
        return None
    text = h4.get_text(strip=True).lower()
    m = re.search(r"(flat|apartment|house|villa|chalet|garage|plot|land|office|local|duplex|penthouse|atico)", text)
    if not m:
        return None
    tipo_map = {
        "flat": "piso",
        "apartment": "apartamento",
        "house": "casa",
        "villa": "chalet",
        "chalet": "chalet",
        "garage": "garaje",
        "plot": "terreno",
        "land": "terreno",
        "office": "oficina",
        "local": "local",
        "duplex": "dúplex",
        "penthouse": "ático",
        "atico": "ático",
    }
    return tipo_map.get(m.group(1), m.group(1))


def _extract_direccion(soup: BeautifulSoup) -> Optional[str]:
    """Extract the address line from #inmueble2_titulo2_subtitulo.

    The element contains a map button (#boton_modal_mapa) whose text ('map'/'mapa')
    must be excluded from the address.
    """
    p = soup.select_one("#inmueble2_titulo2_subtitulo")
    if not p:
        return None
    # Remove the map button before extracting text
    map_btn = p.select_one("#boton_modal_mapa")
    if map_btn:
        map_btn.decompose()
    text = p.get_text(strip=True)
    # Also strip trailing 'map'/'mapa' in case the selector didn't match
    text = re.sub(r"\s*mapa?\s*$", "", text, flags=re.IGNORECASE)
    return text or None


def _extract_municipio(direccion: str) -> Optional[str]:
    """Extract municipio from the address line 'El Puerto de Santa María, EL JUNCAL'."""
    if not direccion:
        return None
    # Normalize "El Puerto de Santa María" variants.
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
    """UriaHomes puts the description in p#inmueble2_descripcion_aut, with
    additional data in p#inmueble2_datos_adicionales."""
    container = soup.select_one("#inmueble2_descripcion_aut") or soup.select_one("#inmueble2_datos_adicionales")
    if not container:
        return None
    text = container.get_text(strip=True)
    if len(text) > 50:
        return text[:2000]
    # Fallback: try the other selector
    other = soup.select_one("#inmueble2_descripcion_aut" if container.get("id") == "inmueble2_datos_adicionales" else "#inmueble2_datos_adicionales")
    if other:
        text = other.get_text(strip=True)
        return text[:2000] if len(text) > 50 else None
    return None


def _extract_fotos_detail(soup: BeautifulSoup) -> List[str]:
    """Extract photo URLs from #carousel-img-principal .carousel-item img.img-gallery."""
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


def _extract_caracteristicas(soup: BeautifulSoup) -> List[str]:
    """Extract the property-features list (#inmueble2_caracteristicas_inmueble_container ul li)
    and map English labels to Spanish."""
    container = soup.select_one("#inmueble2_caracteristicas_inmueble_container")
    if not container:
        return []
    items: List[str] = []
    for li in container.find_all("li"):
        text = li.get_text(strip=True)
        if not text:
            continue
        items.append(_map_feature(text))
    return items


def _map_feature(text: str) -> str:
    """Map a single (possibly English) feature label to Spanish."""
    lower = text.lower().strip()
    mapped = _EN_FEATURE_MAP.get(lower)
    if mapped:
        return mapped
    # Fall back to a fuzzy lookup for phrases like "70 M2 Built" / "3 Bedrooms".
    for key, value in _EN_FEATURE_MAP.items():
        if key in lower:
            return value
    return text


def _extract_energia(soup: BeautifulSoup) -> Optional[str]:
    """Extract the energy certificate state from #certificado_energetico_estado span."""
    el = soup.select_one("#certificado_energetico_estado span")
    if not el:
        el = soup.select_one("#certificado_energetico_estado")
    if not el:
        return None
    return el.get_text(strip=True) or None


def _extract_referencia(soup: BeautifulSoup) -> Optional[str]:
    """Extract the property reference from #referenceTop h4, e.g. '220-UH0216'."""
    el = soup.select_one("#referenceTop h4")
    if not el:
        return None
    return el.get_text(strip=True) or None


def _extract_coords_from_js(html: str):
    """Extract lat/lng from cargar_mapa_ubicacion_aproximada(...) JavaScript.

    Pattern: cargar_mapa_ubicacion_aproximada("map2", 36.6085028, -6.2167529, ...)
    """
    if not html:
        return None, None
    m = re.search(
        r"cargar_mapa_ubicacion_aproximada\([^,]+,\s*([\d.-]+),\s*([\d.-]+)",
        html,
    )
    if not m:
        return None, None
    try:
        lat = float(m.group(1))
        lng = float(m.group(2))
    except (ValueError, TypeError):
        return None, None
    return lat, lng
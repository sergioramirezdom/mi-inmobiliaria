"""NEOPOLIS (Inmovilla CMS) detail scraper — neopolis.es.

Extraction keys off normalized Spanish label text (the
`span.caracteristica` / `span.valor` pairs inside
`ul.fichapropiedad-listadatos`), not CSS class names: NEOPOLIS classes were
never confirmed stable, but the visible labels are the site's real contract
with its own users.

`Antigüedad` is deliberately never extracted: `Propiedad` has no
`year_built` column, and mapping to it would repeat the dead-mapping bug in
`mobilia_scraper.py`.
"""

import logging
import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from .config import ScraperConfig
from .exceptions import ParsingException
from .foto_extractor import extraer_fotos
from .operacion_detector import detectar_operacion, es_garaje
from .zona_utils import extract_from_html as _zona_from_html
from .zona_utils import extract_from_url as _zona_from_url

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Normalized (lowercased, periods stripped) "caracteristica" label -> Propiedad field.
_FIELD_MAP = {
    "superficie construida": "superficie_m2",
    "superficie útil": "superficie_util_m2",
    "habitaciones": "habitaciones",
    "baños": "banos",
    "tipo de propiedad": "tipo_propiedad",
    "conservación": "estado",
    "gastos comunidad": "precio_comunidad",
    "ibi": "precio_ibi",
    "planta": "planta",
    "tipo calefacción": "calefaccion",
    "zona / ciudad": "direccion",
    "tipo operación": "tipo_operacion",
}

_OPERACION_VALUES = {"vender": "venta", "alquilar": "alquiler"}

_INT_FIELDS = {"habitaciones", "banos", "planta"}
_FLOAT_FIELDS = {"superficie_m2", "superficie_util_m2", "precio_comunidad", "precio_ibi"}

_ENERGIA_RE = re.compile(r"^eficiencia([A-G])$")


class NeopolisScraper:
    """Detail scraper for NEOPOLIS (neopolis.es), an Inmovilla-CMS-based portal."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)

    async def fetch_content(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers=BROWSER_HEADERS,
                http2=False,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except Exception as e:
            raise ParsingException(f"Failed to fetch {url}: {e}")

    async def scrape_property_details(self, property_url: str) -> dict:
        try:
            content = await self.fetch_content(property_url)
            soup = BeautifulSoup(content, "html.parser")

            data: dict = {}

            self._extract_titulo(soup, data)
            self._extract_precio(soup, data)
            self._extract_descripcion(soup, data)
            self._extract_caracteristicas(soup, data)
            self._extract_amenidades(soup, data)
            self._extract_certificado_energetico(soup, data)

            if not data.get("barrio"):
                data["barrio"] = (
                    _zona_from_url(property_url)
                    or self._barrio_from_direccion(data.get("direccion"))
                    or _zona_from_html(content, soup)
                )

            fotos = extraer_fotos(content, url=property_url)
            if fotos:
                data["fotos"] = fotos

            operacion = detectar_operacion(
                titulo=data.get("titulo"),
                precio=data.get("precio"),
                url=property_url,
                descripcion=data.get("descripcion"),
            ) or data.get("tipo_operacion")
            if operacion:
                data["tipo_operacion"] = operacion
                if operacion == "alquiler":
                    data["activa"] = False
                    data["estado"] = "Alquiler"
                    return data

            if es_garaje(
                titulo=data.get("titulo"),
                tipo_propiedad=data.get("tipo_propiedad"),
                url=property_url,
            ):
                data["tipo_propiedad"] = "garaje"

            return data

        except Exception as e:
            self.logger.error(f"Failed to extract NEOPOLIS details: {e}")
            raise ParsingException(f"Failed to extract property details: {e}")

    # ── Extraction helpers ──────────────────────────────────────────────

    def _extract_titulo(self, soup: BeautifulSoup, data: dict) -> None:
        meta_title = soup.find("meta", {"name": "title"})
        if meta_title and meta_title.get("content"):
            data["titulo"] = meta_title["content"].strip()
            return
        h1 = soup.select_one(".fichapropiedad-tituloprincipal h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

    def _extract_precio(self, soup: BeautifulSoup, data: dict) -> None:
        precio_div = soup.find("div", class_="fichapropiedad-precio")
        if not precio_div:
            return
        match = re.search(r"([\d.,]+)\s*€", precio_div.get_text(strip=True))
        if match:
            data["precio"] = self._parse_float(match.group(1))

    def _extract_descripcion(self, soup: BeautifulSoup, data: dict) -> None:
        desc_section = soup.find(id="fichapropiedad-bloquedescripcion")
        if desc_section:
            text = desc_section.get_text(separator=" ", strip=True)
            if text:
                data["descripcion"] = text
                return
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            data["descripcion"] = meta_desc["content"].strip()

    def _extract_caracteristicas(self, soup: BeautifulSoup, data: dict) -> None:
        container = soup.select_one("ul.fichapropiedad-listadatos")
        if not container:
            return

        for li in container.find_all("li"):
            label_span = li.find("span", class_="caracteristica")
            valor_span = li.find("span", class_="valor")
            if not label_span or not valor_span:
                continue

            label = re.sub(r"\s+", " ", label_span.get_text(strip=True)).lower()
            label = label.replace(".", "").strip()
            valor = valor_span.get_text(strip=True)
            if not valor:
                continue

            if "ascensor" in label:
                self._set_ascensor(data, valor)
                continue

            field_name = _FIELD_MAP.get(label)
            if not field_name or field_name in data:
                continue

            if field_name in _INT_FIELDS:
                parsed = self._parse_int(valor)
                if parsed is not None:
                    data[field_name] = parsed
            elif field_name in _FLOAT_FIELDS:
                parsed = self._parse_float(valor)
                if parsed is not None:
                    data[field_name] = parsed
            elif field_name == "tipo_propiedad":
                data[field_name] = valor.lower()
            elif field_name == "tipo_operacion":
                mapped = _OPERACION_VALUES.get(valor.lower())
                if mapped:
                    data[field_name] = mapped
            else:
                data[field_name] = valor

    def _set_ascensor(self, data: dict, valor: str) -> None:
        valor_lower = valor.lower()
        if "ascensor" not in data:
            if "sin" in valor_lower or valor_lower in ("no",):
                data["ascensor"] = False
            elif "con" in valor_lower or valor_lower in ("si", "sí"):
                data["ascensor"] = True

    def _extract_amenidades(self, soup: BeautifulSoup, data: dict) -> None:
        etiquetas = [
            b.get_text(strip=True)
            for b in soup.find_all("b", class_="etiqueta")
            if b.get_text(strip=True)
        ]
        if not etiquetas:
            return

        data["amenidades"] = etiquetas
        lowered = [e.lower() for e in etiquetas]

        if any(e.startswith("trastero") for e in lowered):
            data["trastero"] = True
        if any(e.startswith("terraza") for e in lowered):
            data["terraza"] = True
        if any("aire acondicionado" in e for e in lowered):
            data["aire_acondicionado"] = True
        if "calefaccion" not in data and any(e.startswith("calefacci") for e in lowered):
            data["calefaccion"] = "sí"

    def _extract_certificado_energetico(self, soup: BeautifulSoup, data: dict) -> None:
        cert_section = soup.find(id="fichapropiedad-certificacionenergetica")
        if not cert_section:
            return

        for tr in cert_section.find_all("tr"):
            if not tr.find(class_="flechaEficiencia"):
                continue
            for div in tr.find_all("div", class_=True):
                classes = div.get("class") or []
                for cls in classes:
                    match = _ENERGIA_RE.match(cls)
                    if match:
                        data["certificado_energetico"] = match.group(1)
                        return

    def _barrio_from_direccion(self, direccion: Optional[str]) -> Optional[str]:
        """`direccion` is 'Zona / Ciudad', e.g. 'Crevillet / El Puerto de Santa Maria'."""
        if not direccion or "/" not in direccion:
            return None
        zona = direccion.split("/", 1)[0].strip()
        return zona or None

    # ── Parsing helpers (mirrors mobilia_scraper.py) ────────────────────

    def _parse_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                cleaned = re.sub(r"m[²2]", "", value)
                cleaned = re.sub(r"[^\d.,]", "", cleaned)
                if "," in cleaned and "." in cleaned:
                    if cleaned.rindex(",") > cleaned.rindex("."):
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        cleaned = cleaned.replace(",", "")
                elif "." in cleaned and len(cleaned.split(".")[-1]) == 3:
                    cleaned = cleaned.replace(".", "")
                elif "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                return float(cleaned) if cleaned else None
            except ValueError:
                return None
        return None

    def _parse_int(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            digits = "".join(c for c in value if c.isdigit())
            return int(digits) if digits else None
        return None

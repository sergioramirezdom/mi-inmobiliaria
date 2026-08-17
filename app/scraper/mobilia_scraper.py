"""Mobilia Gestión CMS scraper - for inmobiliarias using mobiliagestion.es platform."""

import re
import logging
from typing import Optional, Any
from datetime import datetime
from bs4 import BeautifulSoup

from .exceptions import ParsingException
from .config import ScraperConfig
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
from .foto_extractor import extraer_fotos
from .operacion_detector import detectar_operacion, es_garaje
import httpx


class MobiliaScraper:
    """
    Detail scraper for inmobiliarias using Mobilia Gestión CMS (mobiliagestion.es).
    Used by Alpica and other agencies on this platform.
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)

    async def fetch_content(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers=self.config.headers or {},
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

            data = {}

            # Title from meta tag (more reliable than <title>)
            meta_title = soup.find("meta", {"name": "title"})
            if meta_title and meta_title.get("content"):
                data["titulo"] = meta_title["content"].strip()
            else:
                title_tag = soup.find("title")
                if title_tag:
                    data["titulo"] = title_tag.get_text(strip=True)

            # Description from meta tag
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc and meta_desc.get("content"):
                data["descripcion"] = meta_desc["content"].strip()

            # Price from span.IDPrecioBig
            precio_span = soup.find("span", class_="IDPrecioBig")
            if precio_span:
                texto = precio_span.get_text(strip=True)
                match = re.search(r"([\d.,]+)\s*€", texto.replace("\xa0", ""))
                if match:
                    data["precio"] = self._parse_float(match.group(1))

            # Main icons: superficie, habitaciones, baños
            # Structure: <i title="Metros construidos" class="fa fa-arrows-alt"><span class="spanIconosInmuebleBig">&nbsp;73 m²</span>
            for i_tag in soup.find_all("i", title=True):
                title = i_tag.get("title", "").lower()
                span = i_tag.find("span", class_="spanIconosInmuebleBig")
                if not span:
                    continue
                valor = span.get_text(strip=True).replace("\xa0", "").strip()

                if "metros construidos" in title or "superficie" in title:
                    m2_match = re.search(r"([\d.,]+)", valor)
                    if m2_match:
                        data["superficie_m2"] = self._parse_float(m2_match.group(1))
                elif "habitacion" in title or "dormitorio" in title or "bedroom" in title:
                    data["habitaciones"] = self._parse_int(valor)
                elif "baño" in title or "bano" in title or "bath" in title:
                    data["banos"] = self._parse_int(valor)

            # Detailed fields from div.IDPropiedadBig
            # Structure: <div class="IDPropiedadBig">Label <span class="pull-right"><strong>Value</strong></span></div>
            field_map = {
                "dormitorios": "habitaciones",
                "habitaciones": "habitaciones",
                "baños": "banos",
                "construidos": "superficie_m2",
                "útiles": "superficie_util_m2",
                "estado": "estado",
                "año de construcción": "year_built",
                "antigüedad": "year_built",
                "tipo": "tipo_propiedad",
                "zona": "barrio",
                "municipio": "municipio",
            }

            for div in soup.find_all("div", class_="IDPropiedadBig"):
                text = div.get_text(separator=" ").strip()
                strong = div.find("strong")
                if not strong:
                    continue
                valor = strong.get_text(strip=True)

                for keyword, field_name in field_map.items():
                    if keyword in text.lower() and field_name not in data:
                        if field_name in ("habitaciones", "banos"):
                            parsed = self._parse_int(valor)
                            if parsed is not None:
                                data[field_name] = parsed
                        elif field_name in ("superficie_m2", "superficie_util_m2"):
                            clean = re.sub(r"m[²2]", "", valor).strip()
                            parsed = self._parse_float(clean)
                            if parsed is not None:
                                data[field_name] = parsed
                        else:
                            data[field_name] = valor
                        break

            # Amenities: check for fa-check icons inside IDPropiedadBig
            amenidades = []
            for div in soup.find_all("div", class_="IDPropiedadBig"):
                if div.find("span", class_="fa-check"):
                    label_text = div.get_text(separator=" ").strip()
                    # Remove the value part (after the check icon)
                    parts = label_text.split()
                    amenidad = " ".join(p for p in parts if p not in ("", "✓"))
                    if amenidad:
                        amenidades.append(amenidad)
            if amenidades:
                data["amenidades"] = amenidades

            data["fecha_publicacion"] = datetime.utcnow().isoformat()

            if not data.get("barrio"):
                data["barrio"] = _zona_from_url(property_url) or _zona_from_html(content, soup)

            self.logger.debug(f"Extracted: {list(data.keys())}")
            if not data.get("fotos"):
                fotos = extraer_fotos(content, url=property_url)
                if fotos:
                    data["fotos"] = fotos

            # Detect operation type and garaje
            operacion = detectar_operacion(
                titulo=data.get("titulo"), precio=data.get("precio"),
                url=property_url, descripcion=data.get("descripcion"),
            )
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
            self.logger.error(f"Failed to extract Alpica details: {e}")
            raise ParsingException(f"Failed to extract property details: {e}")

    def _parse_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                cleaned = re.sub(r"[€$m²m2]", "", value).strip()
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

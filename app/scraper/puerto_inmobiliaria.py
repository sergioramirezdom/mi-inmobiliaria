"""Puerto Inmobiliaria specific scraper - extracts detail page information."""

import re
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup

from .exceptions import ParsingException
from .config import ScraperConfig
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
from .foto_extractor import extraer_fotos
import asyncio
import httpx


class PuertoInmobiliariaScraper:
    """Puerto Inmobiliaria detail scraper - enriches listings with detail page data."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        """Initialize scraper."""
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)

    async def fetch_content(self, url: str) -> str:
        """Fetch HTML content from URL."""
        if not url:
            raise ParsingException("URL cannot be empty")

        try:
            self.logger.debug(f"Fetching URL: {url[:60]}...")
            async with httpx.AsyncClient(
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
                headers=self.config.headers or {}
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                self.logger.info(f"✓ Fetched {len(response.text)} bytes")
                return response.text
        except Exception as e:
            raise ParsingException(f"Failed to fetch {url}: {e}")

    async def scrape_property_details(self, property_url: str) -> dict:
        """
        Scrape detailed information from a property's detail page.

        Args:
            property_url: Full URL to the property detail page

        Returns:
            Dictionary with enriched property data

        Raises:
            ParsingException: If parsing fails
        """
        try:
            # Fetch the detail page
            content = await self.fetch_content(property_url)
            soup = BeautifulSoup(content, "html.parser")

            enriched_data = {}

            # Detect sold/rented properties
            gestionada = soup.find("div", class_="visorficha-bg-estadogestionadas")
            if gestionada:
                estado_span = gestionada.find("span")
                estado_texto = estado_span.get_text(strip=True).lower() if estado_span else "vendida"
                self.logger.info(f"⚠️ Propiedad gestionada: '{estado_texto}' — marcando como inactiva")
                enriched_data["activa"] = False
                enriched_data["estado"] = estado_texto.capitalize()
                return enriched_data

            # Extract title
            titulo = self._extract_title(soup)
            if titulo:
                enriched_data["titulo"] = titulo

            # Extract prices
            precio_actual, precio_anterior = self._extract_prices(soup)
            if precio_actual:
                enriched_data["precio"] = precio_actual
            if precio_anterior:
                enriched_data["precio_anterior"] = precio_anterior

            # Extract description
            descripcion = self._extract_description(soup)
            if descripcion:
                enriched_data["descripcion"] = descripcion

            # Extract characteristics
            caracteristicas = self._extract_characteristics(soup)
            enriched_data.update(caracteristicas)

            # Extract amenities
            amenities = self._extract_amenities(soup)
            if amenities:
                enriched_data["amenidades"] = amenities

            # Add detection date (when we scraped it)
            enriched_data["fecha_publicacion"] = datetime.utcnow().isoformat()

            if not enriched_data.get("barrio"):
                enriched_data["barrio"] = _zona_from_url(property_url) or _zona_from_html(content, soup)

            if not enriched_data.get("fotos"):
                fotos = extraer_fotos(content, url=property_url)
                if fotos:
                    enriched_data["fotos"] = fotos

            self.logger.debug(f"✓ Extracted details: {list(enriched_data.keys())}")
            return enriched_data

        except Exception as e:
            self.logger.error(f"Failed to extract property details: {e}")
            raise ParsingException(f"Failed to extract property details: {e}")

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property title from h1."""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            return title if title else None
        return None

    def _extract_prices(self, soup: BeautifulSoup) -> tuple:
        """Extract current and previous prices."""
        precio_actual = None
        precio_anterior = None

        # Current price
        precio_div = soup.find("div", class_="fichapropiedad-precio")
        if precio_div:
            texto_precio = precio_div.get_text(strip=True)
            # Extract number from "116.500 €"
            match = re.search(r"([\d.,]+)\s*€", texto_precio)
            if match:
                precio_str = match.group(1)
                # Parse considering EU format (1.000,50 or 1000,50)
                precio_actual = self._parse_float(precio_str, "precio")

        # Previous price (reduced price)
        rebajado_div = soup.find("div", class_="rebajado")
        if rebajado_div:
            # Format: "Reduced Price 122.500 € - 5 %"
            texto = rebajado_div.get_text()
            match = re.search(r"([\d.,]+)\s*€", texto)
            if match:
                precio_str = match.group(1)
                precio_anterior = self._parse_float(precio_str, "precio_anterior")

        return precio_actual, precio_anterior

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract full property description."""
        desc_section = soup.find("section", id="fichapropiedad-bloquedescripcion")
        if desc_section:
            description = desc_section.get_text(strip=True)
            return description if description else None
        return None

    def _extract_characteristics(self, soup: BeautifulSoup) -> dict:
        """
        Extract characteristics from the property features list.

        Returns dict with extracted characteristics mapped to standard field names.
        """
        characteristics = {}

        # Map of Puerto Inmobiliaria characteristic names to our field names
        field_mapping = {
            "habitaciones": ["Bedrooms", "Dormitorios", "Habitaciones"],
            "banos": ["Bathrooms", "Baños"],
            "superficie_m2": ["Built Surface", "Superficie construida", "Superficie", "m²"],
            "superficie_util_m2": ["Net Internal Area", "Superficie útil"],
            "estado": ["Condition", "Estado"],
            "year_built": ["Year built", "Año de construcción"],
            "exterior_type": ["Exterior type", "Tipo exterior"],
            "precio_comunidad": ["Community fees", "Gastos de comunidad"],
            "tipo_propiedad": ["Type of property", "Tipo de propiedad"],
            "barrio": ["Zone / City", "Zona / Ciudad"],
        }

        # Try new structure first: div.paginacion-ficha-masdatos ul li.bloque-icono-name-valor1
        masdatos_div = soup.find("div", class_="paginacion-ficha-masdatos")
        if masdatos_div:
            for li in masdatos_div.find_all("li", class_="bloque-icono-name-valor1"):
                divs = li.find_all("div")
                if len(divs) >= 2:
                    # First div contains the label (span with "Habitaciones", "Baños", etc)
                    caracteristica_span = divs[0].find("span")
                    # Second div contains the value (span with "3", "1", etc)
                    valor_span = divs[1].find("span")

                    if caracteristica_span and valor_span:
                        caracteristica = caracteristica_span.get_text(strip=True)
                        valor = valor_span.get_text(strip=True)

                        # Try to map to our field names
                        for field_name, field_labels in field_mapping.items():
                            if any(label.lower() in caracteristica.lower() for label in field_labels):
                                if field_name in ["habitaciones", "banos"]:
                                    characteristics[field_name] = self._parse_int(valor, field_name)
                                elif field_name in ["superficie_m2", "superficie_util_m2"]:
                                    valor_clean = re.sub(r"m²|m2", "", valor).strip()
                                    characteristics[field_name] = self._parse_float(valor_clean, field_name)
                                elif field_name == "precio_comunidad":
                                    valor_clean = re.sub(r"€", "", valor).strip()
                                    characteristics[field_name] = self._parse_float(valor_clean, field_name)
                                else:
                                    characteristics[field_name] = valor
                                break

        # Fallback to old structure if nothing found
        if not characteristics:
            listados = soup.find("ul", class_="fichapropiedad-listadatos")
            if listados:
                for li in listados.find_all("li"):
                    caracteristica_span = li.find("span", class_="caracteristica")
                    valor_span = li.find("span", class_="valor")

                    if caracteristica_span and valor_span:
                        caracteristica = caracteristica_span.get_text(strip=True)
                        valor = valor_span.get_text(strip=True)

                        for field_name, field_labels in field_mapping.items():
                            if any(label.lower() in caracteristica.lower() for label in field_labels):
                                if field_name in ["habitaciones", "banos"]:
                                    characteristics[field_name] = self._parse_int(valor, field_name)
                                elif field_name in ["superficie_m2", "superficie_util_m2"]:
                                    valor_clean = re.sub(r"m²|m2", "", valor).strip()
                                    characteristics[field_name] = self._parse_float(valor_clean, field_name)
                                elif field_name == "precio_comunidad":
                                    valor_clean = re.sub(r"€", "", valor).strip()
                                    characteristics[field_name] = self._parse_float(valor_clean, field_name)
                                else:
                                    characteristics[field_name] = valor
                                break

        return characteristics

    def _extract_amenities(self, soup: BeautifulSoup) -> Optional[list]:
        """
        Extract amenities/qualities from the property.

        Examples: Elevator, Storage Room, Air Conditioning, etc.
        """
        amenities = []

        lista_calidades = soup.find("ul", class_="fichapropiedad-listacalidades")
        if not lista_calidades:
            return None

        for li in lista_calidades.find_all("li"):
            etiqueta = li.find("b", class_="etiqueta")
            if etiqueta:
                amenity = etiqueta.get_text(strip=True)
                if amenity:
                    amenities.append(amenity)

        return amenities if amenities else None

    def _parse_float(self, value: Any, field_name: str = "field") -> Optional[float]:
        """Safe parsing of float values."""
        if value is None or value == "":
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                # Remove currency symbols, units
                cleaned = value.replace("€", "").replace("$", "").strip()
                # Remove common units
                for unit in ["m²", "m2", "kg", "l", "ha"]:
                    cleaned = cleaned.replace(unit, "").strip()

                # Handle EU format (1.000,50 or 1000,50)
                if "," in cleaned and "." in cleaned:
                    comma_idx = cleaned.rindex(",")
                    dot_idx = cleaned.rindex(".")
                    if comma_idx > dot_idx:
                        # EU format
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        # US format
                        cleaned = cleaned.replace(",", "")
                elif "." in cleaned:
                    parts = cleaned.split(".")
                    if len(parts[-1]) == 3:
                        # EU thousands
                        cleaned = cleaned.replace(".", "")
                elif "," in cleaned:
                    parts = cleaned.split(",")
                    if len(parts[-1]) == 3:
                        # Thousands
                        cleaned = cleaned.replace(",", "")
                    else:
                        # Decimal
                        cleaned = cleaned.replace(",", ".")

                return float(cleaned) if cleaned else None
            except ValueError:
                self.logger.debug(f"Could not parse {field_name}: '{value}'")
                return None

        return None

    def _parse_int(self, value: Any, field_name: str = "field") -> Optional[int]:
        """Safe parsing of integer values."""
        if value is None or value == "":
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        if isinstance(value, str):
            try:
                # Extract only digits
                digits = "".join(c for c in value if c in "0123456789")
                return int(digits) if digits else None
            except (ValueError, AttributeError):
                self.logger.debug(f"Could not parse {field_name}: '{value}'")
                return None

        return None

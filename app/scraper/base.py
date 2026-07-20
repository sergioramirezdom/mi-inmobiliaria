"""Abstract base class for all scrapers."""

import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional

import httpx
from sqlmodel import Session

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Fuente, Propiedad
from .config import ScraperConfig
from .exceptions import (
    DeduplicationException,
    ParsingException,
    ScraperException,
    TimeoutException,
    ValidationException,
)
from .zona_normalizer import CatalogoInvalidoError, normalizar as normalizar_zona

logger = logging.getLogger(__name__)


class ScraperBase(ABC):
    """Abstract base class for all scraper implementations."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        """Initialize scraper with configuration."""
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

    # ============================================================
    # ABSTRACT METHODS (must be implemented by subclasses)
    # ============================================================

    @abstractmethod
    async def scrape(self, fuente: Fuente) -> List[dict]:
        """
        Execute scraping for a fuente and return raw property data.

        Args:
            fuente: Source configuration to scrape

        Returns:
            List of raw property dictionaries with extracted fields

        Raises:
            TimeoutException: If scraping times out
            ParsingException: If HTML parsing fails
            ValidationException: If fuente is invalid
            ScraperException: For other scraping errors
        """
        pass

    @abstractmethod
    def _parse_properties(self, content: str) -> List[Any]:
        """
        Parse HTML content and extract property elements.

        Args:
            content: HTML content as string

        Returns:
            List of property elements/objects

        Raises:
            ParsingException: If parsing fails
        """
        pass

    @abstractmethod
    def _extract_fields(self, element: Any) -> dict:
        """
        Extract fields from a single property element.

        Args:
            element: Single property element from parsed HTML

        Returns:
            Dictionary with extracted fields (precio, m2, habitaciones, etc)

        Raises:
            ParsingException: If field extraction fails
        """
        pass

    # ============================================================
    # CONCRETE HELPER METHODS (implementation provided)
    # ============================================================

    def validate_fuente(self, fuente: Fuente) -> bool:
        """
        Validate that fuente configuration is compatible with this scraper.

        Args:
            fuente: Source to validate

        Returns:
            True if valid, raises ValidationException if not

        Raises:
            ValidationException: If fuente is invalid
        """
        if not fuente:
            raise ValidationException("Fuente cannot be None")

        if not fuente.url:
            raise ValidationException("Fuente.url is required")

        if not fuente.url.startswith(("http://", "https://")):
            raise ValidationException(f"Invalid URL format: {fuente.url}")

        if not fuente.tipo_scraper:
            raise ValidationException("Fuente.tipo_scraper is required")

        self.logger.info(f"✓ Fuente '{fuente.nombre}' validated successfully")
        return True

    def calculate_hash(self, url_original: str) -> str:
        """
        Calculate SHA-256 hash of property URL for deduplication.

        Args:
            url_original: Original property URL

        Returns:
            SHA-256 hash as hexadecimal string

        Raises:
            DeduplicationException: If hash calculation fails
        """
        if not url_original:
            raise DeduplicationException("URL cannot be empty for hash calculation")

        try:
            hash_value = hashlib.sha256(url_original.encode("utf-8")).hexdigest()
            self.logger.debug(f"Hash calculated for URL: {url_original[:50]}... → {hash_value}")
            return hash_value
        except Exception as e:
            raise DeduplicationException(f"Failed to calculate hash: {e}")

    def normalize_property(self, raw_data: dict, fuente: Fuente) -> Propiedad:
        """
        Convert raw scraped data to Propiedad model.

        Args:
            raw_data: Raw dictionary from scraper with extracted fields
            fuente: Source fuente for metadata

        Returns:
            Propiedad model instance ready to save to DB

        Raises:
            ValidationException: If required fields are missing
            ParsingException: If field conversion fails
        """
        if not raw_data:
            raise ValidationException("raw_data cannot be empty")

        if not isinstance(raw_data, dict):
            raise ValidationException(f"raw_data must be dict, got {type(raw_data)}")

        try:
            url_original = raw_data.get("url_original") or raw_data.get("url")
            if not url_original:
                raise ValidationException("url_original is required in raw_data")

            hash_unico = self.calculate_hash(url_original)

            # Extract origen_web from fuente URL (hostname)
            from urllib.parse import urlparse

            origen_web = urlparse(fuente.url).netloc or "unknown"

            # Parse numeric fields safely
            precio = self._parse_float(raw_data.get("precio"), "precio")
            superficie_m2 = self._parse_float(raw_data.get("superficie_m2") or raw_data.get("m2"), "m2")
            habitaciones = self._parse_int(raw_data.get("habitaciones") or raw_data.get("rooms"), "habitaciones")
            banos = self._parse_int(raw_data.get("banos") or raw_data.get("bathrooms"), "banos")

            zona_match = normalizar_zona(
                barrio=raw_data.get("barrio"),
                direccion=raw_data.get("direccion") or raw_data.get("address"),
                titulo=raw_data.get("titulo") or raw_data.get("title"),
                descripcion=raw_data.get("descripcion") or raw_data.get("description"),
                url=raw_data.get("url_original") or raw_data.get("url"),
            )

            # Create Propiedad instance
            propiedad = Propiedad(
                hash_unico=hash_unico,
                url_original=url_original,
                fuente_id=fuente.id,
                origen_web=origen_web,
                titulo=raw_data.get("titulo") or raw_data.get("title") or "Sin título",
                precio=precio,
                precio_anterior=self._parse_float(raw_data.get("precio_anterior"), "precio_anterior"),
                tipo_propiedad=raw_data.get("tipo_propiedad") or raw_data.get("property_type"),
                superficie_m2=superficie_m2,
                habitaciones=habitaciones,
                banos=banos,
                aseos=self._parse_int(raw_data.get("aseos"), "aseos"),
                planta=self._parse_int(raw_data.get("planta") or raw_data.get("floor"), "planta"),
                total_plantas=self._parse_int(raw_data.get("total_plantas"), "total_plantas"),
                ascensor=self._parse_bool(raw_data.get("ascensor") or raw_data.get("elevator")),
                garaje=self._parse_bool(raw_data.get("garaje") or raw_data.get("garage")),
                trastero=self._parse_bool(raw_data.get("trastero")),
                terraza=self._parse_bool(raw_data.get("terraza")),
                balcon=self._parse_bool(raw_data.get("balcon")),
                patio=self._parse_bool(raw_data.get("patio")),
                piscina=self._parse_bool(raw_data.get("piscina")),
                aire_acondicionado=self._parse_bool(raw_data.get("aire_acondicionado")),
                calefaccion=raw_data.get("calefaccion"),
                amueblado=self._parse_bool(raw_data.get("amueblado")),
                mascotas=self._parse_bool(raw_data.get("mascotas")),
                estado=raw_data.get("estado") or raw_data.get("condition"),
                certificado_energetico=raw_data.get("certificado_energetico"),
                direccion=raw_data.get("direccion") or raw_data.get("address"),
                barrio=raw_data.get("barrio"),
                zona_normalizada=zona_match.zona,
                zona_confianza=zona_match.confianza,
                distrito=raw_data.get("distrito"),
                municipio=raw_data.get("municipio"),
                provincia=raw_data.get("provincia"),
                codigo_postal=raw_data.get("codigo_postal"),
                latitud=self._parse_float(raw_data.get("latitud"), "latitud"),
                longitud=self._parse_float(raw_data.get("longitud"), "longitud"),
                descripcion=raw_data.get("descripcion") or raw_data.get("description"),
                fotos=raw_data.get("fotos") or raw_data.get("images"),
                amenidades=raw_data.get("amenidades"),
                fecha_publicacion=raw_data.get("fecha_publicacion"),
            )

            self.logger.debug(f"✓ Property normalized: {propiedad.titulo} ({propiedad.hash_unico[:8]}...)")
            return propiedad

        except ValidationException:
            raise
        except CatalogoInvalidoError:
            raise
        except Exception as e:
            raise ParsingException(f"Failed to normalize property: {e}")

    async def fetch_content(self, url: str) -> str:
        """
        Download HTML content from URL with timeout and retries.

        Args:
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            TimeoutException: If request times out
            ScraperException: For other HTTP errors
        """
        if not url:
            raise ScraperException("URL cannot be empty")

        for attempt in range(self.config.retries):
            try:
                self.logger.debug(f"Fetching URL (attempt {attempt + 1}/{self.config.retries}): {url[:60]}...")

                default_headers = {
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                }
                default_headers.update(self.config.headers or {})

                async with httpx.AsyncClient(
                    timeout=self.config.timeout,
                    verify=self.config.verify_ssl,
                    headers=default_headers,
                    limits=httpx.Limits(max_keepalive_connections=5),
                    http2=False,
                    mounts={"https://": httpx.AsyncHTTPTransport(http2=False)}
                ) as client:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    content = response.text

                self.logger.info(f"✓ Fetched {len(content)} bytes from {url[:60]}...")
                return content

            except httpx.TimeoutException as e:
                self.logger.warning(f"⏱️ Timeout on attempt {attempt + 1}/{self.config.retries}: {e}")
                if attempt == self.config.retries - 1:
                    raise TimeoutException(f"Timeout fetching {url} after {self.config.retries} retries")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    self.logger.warning(f"Server error {e.response.status_code}, retrying...")
                    if attempt < self.config.retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                raise ScraperException(f"HTTP {e.response.status_code} fetching {url}: {e}")

            except httpx.RequestError as e:
                self.logger.error(f"Request error: {e}")
                if attempt < self.config.retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ScraperException(f"Failed to fetch {url}: {e}")

        raise ScraperException(f"Failed to fetch {url} after {self.config.retries} attempts")

    def log_execution(self, fuente: Fuente, status: str, message: Optional[str] = None, error: Optional[Exception] = None):
        """
        Log scraper execution with status and optional error.

        Args:
            fuente: Source that was scraped
            status: Status of execution (success, timeout, error, etc)
            message: Additional message to log
            error: Exception if execution failed
        """
        log_msg = f"[{fuente.nombre}] {status}"
        if message:
            log_msg += f": {message}"

        if error:
            self.logger.error(f"{log_msg} | Error: {error}")
        elif status == "success":
            self.logger.info(f"✓ {log_msg}")
        elif status in ("timeout", "error"):
            self.logger.warning(f"⚠️ {log_msg}")
        else:
            self.logger.info(log_msg)

    # ============================================================
    # PRIVATE HELPER METHODS
    # ============================================================

    def _parse_float(self, value: Any, field_name: str = "field") -> Optional[float]:
        """Safe parsing of float values (handles European and US formats)."""
        if value is None or value == "":
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                # Remove currency symbols, units, and common suffixes
                cleaned = value.replace("€", "").replace("$", "").strip()
                # Remove common units (m², m2, kg, etc)
                for unit in ["m²", "m2", "kg", "l", "ha", "ha.", "km", "cm", "mm"]:
                    cleaned = cleaned.replace(unit, "").strip()
                cleaned = cleaned.strip()

                # Handle different number formats:
                # US: 150,000.50 or 150.50
                # EU: 150.000,50 or 150,50
                # Simple: 150000 or 150.5 or 150,5

                if "," in cleaned and "." in cleaned:
                    # Both separators present
                    comma_idx = cleaned.rindex(",")
                    dot_idx = cleaned.rindex(".")
                    if comma_idx > dot_idx:
                        # EU format: 150.000,50 -> comma is decimal
                        cleaned = cleaned.replace(".", "").replace(",", ".")
                    else:
                        # US format: 150,000.50 -> dot is decimal
                        cleaned = cleaned.replace(",", "")

                elif "." in cleaned:
                    # Only dots
                    parts = cleaned.split(".")
                    if len(parts[-1]) == 3:
                        # EU thousands: 150.000 -> remove dot
                        cleaned = cleaned.replace(".", "")
                    # else: keep as is (150.50 or 150.5)

                elif "," in cleaned:
                    # Only commas: check if it's thousands or decimal
                    parts = cleaned.split(",")
                    if len(parts[-1]) == 3:
                        # Likely thousands separator (150,000)
                        cleaned = cleaned.replace(",", "")
                    else:
                        # Decimal separator (150,50 -> 150.50)
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
                # Extract only ASCII digits (0-9), ignoring superscripts like ²
                digits = "".join(c for c in value if c in "0123456789")
                return int(digits) if digits else None
            except (ValueError, AttributeError):
                self.logger.debug(f"Could not parse {field_name}: '{value}'")
                return None

        return None

    def _parse_bool(self, value: Any) -> Optional[bool]:
        """Safe parsing of boolean values."""
        if value is None or value == "":
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "si", "sí")

        return bool(value) if value else None

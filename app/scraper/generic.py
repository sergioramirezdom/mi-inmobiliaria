"""Generic scraper implementation using httpx and BeautifulSoup4."""

import re
from typing import Any, List, Optional

from bs4 import BeautifulSoup

from .base import ScraperBase
from .config import ScraperConfig
from .exceptions import ParsingException
from db.models import Fuente


class GenericScraper(ScraperBase):
    """Generic web scraper using CSS selectors or auto-detection."""

    def __init__(self, config: Optional[ScraperConfig] = None):
        """Initialize generic scraper with optional custom config."""
        super().__init__(config)

    async def scrape(self, fuente: Fuente) -> List[dict]:
        """
        Scrape a source and return raw property data.

        Args:
            fuente: Source configuration

        Returns:
            List of raw property dictionaries

        Raises:
            ValidationException: If fuente is invalid
            TimeoutException: If fetch times out
            ParsingException: If parsing fails
        """
        self.validate_fuente(fuente)

        try:
            self.logger.info(f"🔍 Starting scrape for {fuente.nombre}...")

            content = await self.fetch_content(fuente.url)
            properties = self._parse_properties(content)

            raw_data_list = []
            for prop_element in properties:
                try:
                    raw_data = self._extract_fields(prop_element)
                    if raw_data.get("url_original"):
                        raw_data_list.append(raw_data)
                except ParsingException as e:
                    self.logger.warning(f"⚠️ Failed to extract property: {e}")
                    continue

            self.logger.info(f"✓ Scraped {len(raw_data_list)} properties from {fuente.nombre}")
            return raw_data_list

        except Exception as e:
            self.logger.error(f"❌ Scrape failed for {fuente.nombre}: {e}")
            raise

    def _parse_properties(self, content: str) -> List[Any]:
        """
        Parse HTML content and extract property elements.

        Uses CSS selectors from config if available, otherwise attempts auto-detect.

        Args:
            content: HTML content as string

        Returns:
            List of BeautifulSoup elements (or strings in auto-detect fallback)

        Raises:
            ParsingException: If parsing fails
        """
        if not content:
            raise ParsingException("Content cannot be empty")

        try:
            soup = BeautifulSoup(content, "html.parser")

            container_selector = self.config.selectors.property_container

            if container_selector:
                self.logger.debug(f"Using CSS selector: {container_selector}")
                elements = soup.select(container_selector)
                if not elements:
                    self.logger.warning(f"⚠️ No elements found with selector: {container_selector}")
                    return []
                self.logger.debug(f"Found {len(elements)} property containers")
                return elements
            else:
                self.logger.debug("No selector configured, attempting auto-detect...")
                return self._auto_detect_properties(soup)

        except Exception as e:
            raise ParsingException(f"Failed to parse HTML: {e}")

    def _extract_fields(self, element: Any) -> dict:
        """
        Extract all fields from a property element.

        Tries CSS selectors first, then regex patterns as fallback.

        Args:
            element: BeautifulSoup element or string

        Returns:
            Dictionary with extracted fields

        Raises:
            ParsingException: If critical fields cannot be extracted
        """
        raw_data = {}

        try:
            # Convert string to BeautifulSoup element if needed
            if isinstance(element, str):
                element = BeautifulSoup(element, "html.parser")

            # === CRITICAL: Extract URL ===
            url_original = self._extract_field(element, "link")
            if not url_original:
                raise ParsingException("No URL found in property")
            raw_data["url_original"] = url_original

            # === OPTIONAL: Extract all other fields ===
            raw_data["titulo"] = self._extract_field(element, "title") or "Sin título"
            raw_data["precio"] = self._extract_field(element, "price")
            raw_data["m2"] = self._extract_field(element, "size")
            raw_data["rooms"] = self._extract_field(element, "rooms")
            raw_data["bathrooms"] = self._extract_field(element, "bathrooms")
            raw_data["address"] = self._extract_field(element, "address")
            raw_data["property_type"] = self._extract_field(element, "property_type")
            raw_data["floor"] = self._extract_field(element, "floor")
            raw_data["elevator"] = self._extract_field(element, "elevator")
            raw_data["garage"] = self._extract_field(element, "garage")
            raw_data["terraza"] = self._extract_field(element, "terraza")
            raw_data["piscina"] = self._extract_field(element, "piscina")
            raw_data["description"] = self._extract_field(element, "description")
            raw_data["images"] = self._extract_field(element, "images")

            self.logger.debug(f"Extracted fields: {list(raw_data.keys())}")
            return raw_data

        except ParsingException:
            raise
        except Exception as e:
            raise ParsingException(f"Failed to extract fields: {e}")

    # ============================================================
    # PRIVATE HELPER METHODS
    # ============================================================

    def _extract_field(self, element: Any, field_name: str) -> Optional[str]:
        """
        Extract a single field using CSS selector or regex pattern.

        Args:
            element: BeautifulSoup element
            field_name: Field to extract (e.g., "price", "rooms")

        Returns:
            Extracted value as string, or None if not found
        """
        # Try CSS selector first
        selector = getattr(self.config.selectors, field_name, None)
        if selector:
            try:
                found = element.select_one(selector)
                if found:
                    # For links, extract href attribute; for others, extract text
                    if field_name == "link":
                        href = found.get("href")
                        return href if href else None
                    else:
                        text = found.get_text(strip=True)
                        return text if text else None
            except Exception as e:
                self.logger.debug(f"Selector '{selector}' failed: {e}")

        # Fallback to regex pattern
        if field_name == "link":
            # For links, try multiple sources
            try:
                element_html = str(element)

                # Try href attribute first
                match = re.search(r'href=["\']([^"\']+)["\']', element_html)
                if match:
                    return match.group(1)

                # Try onclick attribute (common in dynamic sites)
                match = re.search(r"onclick=['\"].*?['\"]([^'\"]+)['\"]['\"]", element_html)
                if match:
                    return match.group(1)

                # Try onclick with location.href pattern
                match = re.search(r"onclick=['\"].*?location\.href=['\"]([^'\"]+)['\"][^'\"]*['\"]", element_html)
                if match:
                    return match.group(1)

                # Generic onclick URL extraction
                match = re.search(r"onclick=['\"].*?['\"]([^'\"]*(?:index|ficha|property|listing|detail)[^'\"]*)['\"]", element_html)
                if match:
                    return match.group(1)

            except Exception as e:
                self.logger.debug(f"Link regex failed: {e}")
        else:
            pattern = getattr(self.config.patterns, f"{field_name}_pattern", None)
            if pattern:
                try:
                    element_text = element.get_text() if hasattr(element, "get_text") else str(element)
                    match = re.search(pattern, element_text)
                    if match:
                        return match.group(1) if match.groups() else match.group(0)
                except Exception as e:
                    self.logger.debug(f"Pattern '{pattern}' failed: {e}")

        return None

    def _auto_detect_properties(self, soup: BeautifulSoup) -> List[Any]:
        """
        Attempt to auto-detect property containers in HTML.

        Looks for common patterns (divs with class names containing "property", "listing", etc).

        Args:
            soup: BeautifulSoup object

        Returns:
            List of detected elements
        """
        # Common container patterns
        patterns = [
            '[class*="property"]',
            '[class*="listing"]',
            '[class*="anuncio"]',
            'article[class*="item"]',
            'div[class*="resultado"]',
            'li[class*="property"]',
        ]

        for pattern in patterns:
            elements = soup.select(pattern)
            if len(elements) > 3:  # Must find at least 3 properties
                self.logger.info(f"✓ Auto-detected {len(elements)} properties with pattern: {pattern}")
                return elements

        self.logger.warning("Could not auto-detect property containers")
        return []

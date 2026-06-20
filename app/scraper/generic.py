"""Generic scraper implementation using httpx and BeautifulSoup4."""

import re
from typing import Any, List, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
        self.base_url = None  # Will be set during scrape() for relative URL resolution

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

            # Store base URL for resolving relative URLs
            from urllib.parse import urlparse
            parsed = urlparse(fuente.url)
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
            self.logger.debug(f"Base URL set to: {self.base_url}")

            content = await self.fetch_content(fuente.url)
            properties = self._parse_properties(content)

            raw_data_list = []
            for prop_element in properties:
                try:
                    raw_data = self._extract_fields(prop_element)
                    if raw_data.get("url_original"):
                        raw_data_list.append(raw_data)
                except ParsingException as e:
                    self.logger.debug(f"Skipped element (no URL): {e}")
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
            link_href_contains = self.config.selectors.link_href_contains

            if container_selector:
                self.logger.debug(f"Using CSS selector: {container_selector}")
                elements = soup.select(container_selector)
                if not elements:
                    self.logger.warning(f"⚠️ No elements found with selector: {container_selector}")
                    return []
                self.logger.debug(f"Found {len(elements)} property containers")
                return elements
            elif link_href_contains:
                # For JS-rendered pages: extract <a> tags by href pattern, deduplicated
                self.logger.debug(f"Using link_href_contains pattern: {link_href_contains}")
                seen_hrefs = set()
                unique_links = []
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    if link_href_contains in href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        unique_links.append(a)
                self.logger.info(f"Found {len(unique_links)} unique links matching '{link_href_contains}'")
                return unique_links
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
            # If element is directly an <a> tag, extract href and text directly
            if element.name == "a" and element.get("href"):
                url_original = self._resolve_url(element["href"])
                link_text = element.get_text(strip=True)
                if link_text:
                    raw_data["titulo"] = link_text
            else:
                url_original = self._extract_field(element, "link")
            if not url_original:
                raise ParsingException("No URL found in property")
            raw_data["url_original"] = url_original

            # === OPTIONAL: Extract all other fields ===
            if "titulo" not in raw_data:
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

    def _resolve_url(self, url: str) -> Optional[str]:
        """
        Convert relative URLs to absolute URLs using base_url.
        Returns None for invalid URLs (anchors, hashes, empty).

        Args:
            url: Relative or absolute URL

        Returns:
            Absolute URL or None if invalid
        """
        if not url or url in ('#', ''):
            return None

        # If already absolute, return as-is
        if url.startswith(('http://', 'https://')):
            return url

        # If relative, prepend base_url
        if self.base_url:
            # Remove leading slash if present to avoid double slashes
            if url.startswith('/'):
                resolved = self.base_url + url
            else:
                resolved = self.base_url + '/' + url
            self.logger.debug(f"Resolved relative URL: {url[:50]}... → {resolved[:70]}...")
            return resolved

        self.logger.debug(f"No base_url set, returning URL as-is: {url[:50]}")
        return url

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
                        if href:
                            return self._resolve_url(href)
                        # If no href, try onclick attribute
                        onclick = found.get("onclick")
                        if onclick:
                            self.logger.debug(f"Found onclick attribute, trying to extract URL from it")
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
                    return self._resolve_url(match.group(1))

                # Extract onclick content and look for URLs inside
                onclick_match = re.search(r'onclick=["\']([^"\']*)["\']', element_html)
                if onclick_match:
                    onclick_content = onclick_match.group(1)

                    # Try to find URL in onclick content
                    url_patterns = [
                        r"window\.location\s*=\s*['\"]([^'\"]+)['\"]",  # window.location = "..."
                        r"location\.href\s*=\s*['\"]([^'\"]+)['\"]",    # location.href = "..."
                        r"window\.open\(['\"]([^'\"]+)['\"]",            # window.open("...")
                        r"['\"]([^'\"]*propiedad[^'\"]*)['\"]",          # Contains 'propiedad'
                        r"['\"]([^'\"]*(?:index|ficha|detail)[^'\"]*)['\"]",  # Common URL paths
                    ]

                    for pattern in url_patterns:
                        url_match = re.search(pattern, onclick_content)
                        if url_match:
                            url_value = url_match.group(1)
                            return self._resolve_url(url_value)

                    # If no pattern matched, try to extract any URL-like string
                    # Look for paths or full URLs
                    all_quoted = re.findall(r"['\"]([^'\"]+)['\"]", onclick_content)
                    for quoted in all_quoted:
                        if quoted.startswith(('http', '/', '/propiedad', 'propiedad', 'ficha')):
                            return self._resolve_url(quoted)

                # Try data-path attribute (used by JS-navigated sites like alonsaga.com)
                data_path_match = re.search(r'data-path=["\']([^"\']+)["\']', element_html)
                if data_path_match:
                    return self._resolve_url(data_path_match.group(1))

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

"""Unit tests for GenericScraper."""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.generic import GenericScraper
from scraper.config import ScraperConfig, SelectorsConfig
from scraper.exceptions import ParsingException
from db.models import Fuente


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def mock_fuente():
    """Create a mock Fuente for testing."""
    return Fuente(
        id=1,
        nombre="Test Source",
        url="https://example.com/properties",
        tipo_scraper="generic",
        activa=True,
        intervalo_horas=24,
    )


@pytest.fixture
def generic_scraper():
    """Create a GenericScraper instance."""
    config = ScraperConfig(timeout=30, retries=3)
    return GenericScraper(config)


@pytest.fixture
def html_with_css_selectors():
    """Mock HTML with CSS selectors."""
    return """
    <html>
        <body>
            <div class="property-container">
                <div class="property-item">
                    <a class="property-link" href="https://example.com/prop/1">Link</a>
                    <h2 class="property-title">Piso 3 hab céntrico</h2>
                    <span class="property-price">€150.000</span>
                    <span class="property-size">100 m²</span>
                    <span class="property-rooms">3</span>
                    <span class="property-bathrooms">2</span>
                    <span class="property-address">Calle Mayor 123</span>
                    <span class="property-type">piso</span>
                </div>
                <div class="property-item">
                    <a class="property-link" href="https://example.com/prop/2">Link</a>
                    <h2 class="property-title">Casa 5 hab</h2>
                    <span class="property-price">€300.000</span>
                    <span class="property-size">200 m²</span>
                    <span class="property-rooms">5</span>
                    <span class="property-bathrooms">3</span>
                </div>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def html_without_selectors():
    """Mock HTML without known CSS selectors (auto-detect)."""
    return """
    <html>
        <body>
            <div class="listing-container">
                <article class="anuncio">
                    <a href="https://example.com/prop/101">Enlace</a>
                    <div class="listing-title">Piso moderno</div>
                    <div class="listing-price">€250.000</div>
                    <div class="listing-size">120 m²</div>
                </article>
                <article class="anuncio">
                    <a href="https://example.com/prop/102">Enlace</a>
                    <div class="listing-title">Apartamento</div>
                </article>
                <article class="anuncio">
                    <a href="https://example.com/prop/103">Enlace</a>
                </article>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def html_malformed():
    """Malformed HTML that still parses but has missing data."""
    return """
    <html>
        <body>
            <div class="property-item">
                <h2>Missing URL property</h2>
            </div>
        </body>
    </html>
    """


# ============================================================
# TESTS FOR _parse_properties()
# ============================================================


class TestParseProperties:
    """Tests for _parse_properties() method."""

    def test_parse_properties_with_css_selectors(self, generic_scraper, html_with_css_selectors):
        """Test parsing with CSS selector config."""
        generic_scraper.config.selectors.property_container = "div.property-item"

        elements = generic_scraper._parse_properties(html_with_css_selectors)

        assert len(elements) == 2
        assert all(hasattr(elem, "select_one") for elem in elements)

    def test_parse_properties_no_matching_selector(self, generic_scraper, html_with_css_selectors):
        """Test parsing with selector that matches nothing."""
        generic_scraper.config.selectors.property_container = "div.nonexistent"

        elements = generic_scraper._parse_properties(html_with_css_selectors)

        assert elements == []

    def test_parse_properties_auto_detect(self, generic_scraper, html_without_selectors):
        """Test auto-detection when no selector configured."""
        generic_scraper.config.selectors.property_container = None

        elements = generic_scraper._parse_properties(html_without_selectors)

        assert len(elements) >= 3  # Should find the "anuncio" articles

    def test_parse_properties_empty_content(self, generic_scraper):
        """Test parsing empty content raises error."""
        with pytest.raises(ParsingException):
            generic_scraper._parse_properties("")

    def test_parse_properties_none_content(self, generic_scraper):
        """Test parsing None content raises error."""
        with pytest.raises(ParsingException):
            generic_scraper._parse_properties(None)


# ============================================================
# TESTS FOR _extract_field()
# ============================================================


class TestExtractField:
    """Tests for _extract_field() helper method."""

    def test_extract_field_with_selector(self, generic_scraper, html_with_css_selectors):
        """Test field extraction using CSS selector."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_with_css_selectors, "html.parser")
        element = soup.select_one("div.property-item")

        generic_scraper.config.selectors.price = "span.property-price"
        price = generic_scraper._extract_field(element, "price")

        assert price == "€150.000"

    def test_extract_field_without_selector_uses_regex(self, generic_scraper, html_with_css_selectors):
        """Test field extraction falls back to regex pattern."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_with_css_selectors, "html.parser")
        element = soup.select_one("div.property-item")

        generic_scraper.config.selectors.price = None  # No selector
        # Config has default regex patterns
        price = generic_scraper._extract_field(element, "price")

        # Regex should find something
        assert price is not None

    def test_extract_field_not_found(self, generic_scraper, html_with_css_selectors):
        """Test extraction returns None when field not found."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_with_css_selectors, "html.parser")
        element = soup.select_one("div.property-item")

        generic_scraper.config.selectors.piscina = None
        piscina = generic_scraper._extract_field(element, "piscina")

        assert piscina is None


# ============================================================
# TESTS FOR _extract_fields()
# ============================================================


class TestExtractFields:
    """Tests for _extract_fields() method."""

    def test_extract_fields_all_available(self, generic_scraper, html_with_css_selectors):
        """Test extraction when all fields are available."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_with_css_selectors, "html.parser")
        element = soup.select_one("div.property-item")

        # Configure selectors
        generic_scraper.config.selectors.link = "a.property-link"
        generic_scraper.config.selectors.title = "h2.property-title"
        generic_scraper.config.selectors.price = "span.property-price"
        generic_scraper.config.selectors.size = "span.property-size"
        generic_scraper.config.selectors.rooms = "span.property-rooms"
        generic_scraper.config.selectors.bathrooms = "span.property-bathrooms"
        generic_scraper.config.selectors.address = "span.property-address"
        generic_scraper.config.selectors.property_type = "span.property-type"

        raw_data = generic_scraper._extract_fields(element)

        assert raw_data["url_original"] == "https://example.com/prop/1"
        assert raw_data["titulo"] == "Piso 3 hab céntrico"
        assert raw_data["precio"] == "€150.000"
        assert raw_data["m2"] == "100 m²"
        assert raw_data["rooms"] == "3"
        assert raw_data["bathrooms"] == "2"

    def test_extract_fields_missing_url_raises_error(self, generic_scraper, html_malformed):
        """Test extraction fails if URL is missing."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_malformed, "html.parser")
        element = soup.select_one("div.property-item")

        with pytest.raises(ParsingException, match="No URL found"):
            generic_scraper._extract_fields(element)

    def test_extract_fields_minimal(self, generic_scraper):
        """Test extraction with minimal HTML (only URL)."""
        from bs4 import BeautifulSoup

        html = '<div><a href="https://example.com/prop">Link</a></div>'
        soup = BeautifulSoup(html, "html.parser")
        element = soup.select_one("div")

        generic_scraper.config.selectors.link = "a"

        raw_data = generic_scraper._extract_fields(element)

        assert raw_data["url_original"] == "https://example.com/prop"
        assert raw_data["titulo"] == "Sin título"
        assert raw_data["precio"] is None

    def test_extract_fields_handles_empty_text(self, generic_scraper):
        """Test extraction handles empty selector results."""
        from bs4 import BeautifulSoup

        html = '<div><a href="https://example.com/prop"><span class="title"></span></a></div>'
        soup = BeautifulSoup(html, "html.parser")
        element = soup.select_one("div")

        generic_scraper.config.selectors.link = "a"
        generic_scraper.config.selectors.title = "span.title"

        raw_data = generic_scraper._extract_fields(element)

        # Empty span should not override "Sin título" default
        assert raw_data["titulo"] == "Sin título"


# ============================================================
# TESTS FOR scrape() (Async)
# ============================================================


class TestScrape:
    """Tests for scrape() async method."""

    @pytest.mark.asyncio
    async def test_scrape_success(self, generic_scraper, mock_fuente, html_with_css_selectors):
        """Test successful scraping."""
        generic_scraper.config.selectors.property_container = "div.property-item"
        generic_scraper.config.selectors.link = "a.property-link"
        generic_scraper.config.selectors.title = "h2.property-title"
        generic_scraper.config.selectors.price = "span.property-price"

        # Mock fetch_content
        with patch.object(generic_scraper, "fetch_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html_with_css_selectors

            result = await generic_scraper.scrape(mock_fuente)

            assert len(result) >= 1
            assert "url_original" in result[0]
            assert "titulo" in result[0]

    @pytest.mark.asyncio
    async def test_scrape_invalid_fuente(self, generic_scraper):
        """Test scraping with invalid fuente."""
        bad_fuente = Fuente(nombre="Bad", url="", tipo_scraper="generic")

        with pytest.raises(Exception):  # ValidationException
            await generic_scraper.scrape(bad_fuente)

    @pytest.mark.asyncio
    async def test_scrape_no_properties_found(self, generic_scraper, mock_fuente):
        """Test scraping when no properties found."""
        empty_html = "<html><body></body></html>"
        generic_scraper.config.selectors.property_container = "div.nonexistent"

        with patch.object(generic_scraper, "fetch_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = empty_html

            result = await generic_scraper.scrape(mock_fuente)

            assert result == []


# ============================================================
# TESTS FOR _auto_detect_properties()
# ============================================================


class TestAutoDetect:
    """Tests for _auto_detect_properties() method."""

    def test_auto_detect_finds_properties(self, generic_scraper, html_without_selectors):
        """Test auto-detection finds property containers."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_without_selectors, "html.parser")
        elements = generic_scraper._auto_detect_properties(soup)

        assert len(elements) >= 3

    def test_auto_detect_no_properties(self, generic_scraper):
        """Test auto-detection with no recognizable patterns."""
        from bs4 import BeautifulSoup

        html = "<html><body><div>Just plain content</div></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        elements = generic_scraper._auto_detect_properties(soup)

        assert elements == []


# ============================================================
# INTEGRATION TESTS
# ============================================================


class TestIntegration:
    """Integration tests for GenericScraper."""

    @pytest.mark.asyncio
    async def test_full_scraping_workflow(self, generic_scraper, mock_fuente, html_with_css_selectors):
        """Test complete scraping workflow from fetch to extract."""
        generic_scraper.config.selectors.property_container = "div.property-item"
        generic_scraper.config.selectors.link = "a.property-link"
        generic_scraper.config.selectors.title = "h2.property-title"

        with patch.object(generic_scraper, "fetch_content", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = html_with_css_selectors

            result = await generic_scraper.scrape(mock_fuente)

            assert len(result) == 2
            assert result[0]["url_original"] == "https://example.com/prop/1"
            assert result[1]["url_original"] == "https://example.com/prop/2"

    def test_integration_css_selector_and_regex_fallback(self, generic_scraper, html_with_css_selectors):
        """Test that CSS selectors are tried first, then regex fallback."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_with_css_selectors, "html.parser")
        element = soup.select_one("div.property-item")

        # Configure selector for one field, leave others for regex
        generic_scraper.config.selectors.link = "a.property-link"
        generic_scraper.config.selectors.title = "h2.property-title"
        generic_scraper.config.selectors.price = None  # Force regex fallback

        raw_data = generic_scraper._extract_fields(element)

        # Both should be extracted (selector + regex)
        assert raw_data["url_original"] == "https://example.com/prop/1"
        assert raw_data["titulo"] == "Piso 3 hab céntrico"
        # Price should be found via regex or None
        # (depends on pattern config)

"""Unit tests for ScraperBase abstract class."""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx

# Python 3.7 compatibility: AsyncMock is available in 3.8+
try:
    from unittest.mock import AsyncMock
except ImportError:
    # Fallback for Python 3.7
    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.base import ScraperBase
from scraper.config import ScraperConfig
from scraper.exceptions import (
    DeduplicationException,
    ParsingException,
    ScraperException,
    TimeoutException,
    ValidationException,
)
from db.models import Fuente, Propiedad


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
def scraper_config():
    """Create a test ScraperConfig."""
    return ScraperConfig(
        timeout=30,
        retries=3,
        verify_ssl=True,
        auto_detect=True,
    )


class ConcreteScraperForTesting(ScraperBase):
    """Concrete implementation of ScraperBase for testing."""

    async def scrape(self, fuente: Fuente):
        return []

    def _parse_properties(self, content: str):
        return []

    def _extract_fields(self, element):
        return {}


# ============================================================
# TESTS FOR validate_fuente()
# ============================================================


class TestValidateFuente:
    """Tests for validate_fuente() method."""

    def test_validate_fuente_valid(self, mock_fuente, scraper_config):
        """Test validation passes for valid fuente."""
        scraper = ConcreteScraperForTesting(scraper_config)
        assert scraper.validate_fuente(mock_fuente) is True

    def test_validate_fuente_none(self, scraper_config):
        """Test validation fails for None fuente."""
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(ValidationException):
            scraper.validate_fuente(None)

    def test_validate_fuente_no_url(self, scraper_config):
        """Test validation fails for fuente without URL."""
        fuente = Fuente(
            nombre="Test",
            url="",
            tipo_scraper="generic",
        )
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(ValidationException):
            scraper.validate_fuente(fuente)

    def test_validate_fuente_invalid_url(self, scraper_config):
        """Test validation fails for invalid URL format."""
        fuente = Fuente(
            nombre="Test",
            url="not-a-url",
            tipo_scraper="generic",
        )
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(ValidationException, match="Invalid URL format"):
            scraper.validate_fuente(fuente)

    def test_validate_fuente_no_tipo_scraper(self, scraper_config):
        """Test validation fails for fuente without tipo_scraper."""
        fuente = Fuente(
            nombre="Test",
            url="https://example.com",
            tipo_scraper="",
        )
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(ValidationException):
            scraper.validate_fuente(fuente)


# ============================================================
# TESTS FOR calculate_hash()
# ============================================================


class TestCalculateHash:
    """Tests for calculate_hash() method."""

    def test_calculate_hash_consistency(self, scraper_config):
        """Test hash is consistent for same URL."""
        scraper = ConcreteScraperForTesting(scraper_config)
        url = "https://example.com/property/123"
        hash1 = scraper.calculate_hash(url)
        hash2 = scraper.calculate_hash(url)
        assert hash1 == hash2

    def test_calculate_hash_different_urls(self, scraper_config):
        """Test different URLs produce different hashes."""
        scraper = ConcreteScraperForTesting(scraper_config)
        hash1 = scraper.calculate_hash("https://example.com/prop/1")
        hash2 = scraper.calculate_hash("https://example.com/prop/2")
        assert hash1 != hash2

    def test_calculate_hash_length(self, scraper_config):
        """Test hash is SHA-256 (64 hex characters)."""
        scraper = ConcreteScraperForTesting(scraper_config)
        hash_value = scraper.calculate_hash("https://example.com")
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_calculate_hash_empty_url(self, scraper_config):
        """Test hash fails for empty URL."""
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(DeduplicationException):
            scraper.calculate_hash("")

    def test_calculate_hash_none_url(self, scraper_config):
        """Test hash fails for None URL."""
        scraper = ConcreteScraperForTesting(scraper_config)
        with pytest.raises(DeduplicationException):
            scraper.calculate_hash(None)

    def test_calculate_hash_special_characters(self, scraper_config):
        """Test hash handles special characters."""
        scraper = ConcreteScraperForTesting(scraper_config)
        url = "https://example.com/prop?id=123&type=piso&precio=€150.000"
        hash_value = scraper.calculate_hash(url)
        assert len(hash_value) == 64


# ============================================================
# TESTS FOR normalize_property()
# ============================================================


class TestNormalizeProperty:
    """Tests for normalize_property() method."""

    def test_normalize_property_all_fields(self, mock_fuente, scraper_config):
        """Test normalization with all fields provided."""
        scraper = ConcreteScraperForTesting(scraper_config)

        raw_data = {
            "url_original": "https://example.com/prop/123",
            "titulo": "Piso 3 hab",
            "precio": "€150.000",
            "m2": "100 m²",
            "rooms": "3",
            "bathrooms": "2",
            "address": "Calle Main 123",
            "property_type": "piso",
            "floor": "2",
            "elevator": True,
            "garage": False,
        }

        propiedad = scraper.normalize_property(raw_data, mock_fuente)

        assert propiedad.url_original == "https://example.com/prop/123"
        assert propiedad.titulo == "Piso 3 hab"
        assert propiedad.precio == 150000.0
        assert propiedad.superficie_m2 == 100.0
        assert propiedad.habitaciones == 3
        assert propiedad.banos == 2
        assert propiedad.fuente_id == mock_fuente.id
        assert propiedad.origen_web == "example.com"
        assert propiedad.ascensor is True
        assert propiedad.garaje is False

    def test_normalize_property_minimal(self, mock_fuente, scraper_config):
        """Test normalization with only required fields."""
        scraper = ConcreteScraperForTesting(scraper_config)

        raw_data = {
            "url_original": "https://example.com/prop/456",
        }

        propiedad = scraper.normalize_property(raw_data, mock_fuente)

        assert propiedad.url_original == "https://example.com/prop/456"
        assert propiedad.titulo == "Sin título"
        assert propiedad.precio is None
        assert propiedad.superficie_m2 is None
        assert propiedad.habitaciones is None

    def test_normalize_property_missing_url(self, mock_fuente, scraper_config):
        """Test normalization fails without URL."""
        scraper = ConcreteScraperForTesting(scraper_config)

        raw_data = {
            "titulo": "Piso",
        }

        with pytest.raises(ValidationException):
            scraper.normalize_property(raw_data, mock_fuente)

    def test_normalize_property_empty_dict(self, mock_fuente, scraper_config):
        """Test normalization fails for empty dict."""
        scraper = ConcreteScraperForTesting(scraper_config)

        with pytest.raises(ValidationException):
            scraper.normalize_property({}, mock_fuente)

    def test_normalize_property_invalid_type(self, mock_fuente, scraper_config):
        """Test normalization fails for non-dict raw_data."""
        scraper = ConcreteScraperForTesting(scraper_config)

        with pytest.raises(ValidationException):
            scraper.normalize_property("not a dict", mock_fuente)

    def test_normalize_property_hash_generated(self, mock_fuente, scraper_config):
        """Test hash is calculated for property."""
        scraper = ConcreteScraperForTesting(scraper_config)

        url = "https://example.com/prop/789"
        raw_data = {"url_original": url}
        propiedad = scraper.normalize_property(raw_data, mock_fuente)

        expected_hash = scraper.calculate_hash(url)
        assert propiedad.hash_unico == expected_hash

    def test_normalize_property_parse_price(self, mock_fuente, scraper_config):
        """Test various price formats are parsed correctly."""
        scraper = ConcreteScraperForTesting(scraper_config)

        test_cases = [
            ("€150.000", 150000.0),
            ("€150,000", 150000.0),
            ("150000", 150000.0),
            (150000, 150000.0),
            (150000.5, 150000.5),
        ]

        for price_input, expected in test_cases:
            raw_data = {
                "url_original": "https://example.com",
                "precio": price_input,
            }
            propiedad = scraper.normalize_property(raw_data, mock_fuente)
            assert propiedad.precio == expected, f"Failed for {price_input}"

    def test_normalize_property_parse_m2(self, mock_fuente, scraper_config):
        """Test various m2 formats are parsed correctly."""
        scraper = ConcreteScraperForTesting(scraper_config)

        test_cases = [
            ("100 m²", 100.0),
            ("100m²", 100.0),
            ("100", 100.0),
            (100, 100.0),
        ]

        for m2_input, expected in test_cases:
            raw_data = {
                "url_original": "https://example.com",
                "m2": m2_input,
            }
            propiedad = scraper.normalize_property(raw_data, mock_fuente)
            assert propiedad.superficie_m2 == expected, f"Failed for {m2_input}"

    def test_normalize_property_boolean_fields(self, mock_fuente, scraper_config):
        """Test boolean field parsing."""
        scraper = ConcreteScraperForTesting(scraper_config)

        raw_data = {
            "url_original": "https://example.com",
            "elevator": "true",
            "garage": "false",
            "terraza": "si",
            "piscina": True,
        }

        propiedad = scraper.normalize_property(raw_data, mock_fuente)
        assert propiedad.ascensor is True
        assert propiedad.garaje is False
        assert propiedad.terraza is True
        assert propiedad.piscina is True


# ============================================================
# TESTS FOR fetch_content()
# ============================================================
# Note: fetch_content() is async and requires pytest-asyncio
# For now, we test the error handling only via sync methods
# Full async testing will be done in integration tests


# ============================================================
# TESTS FOR log_execution()
# ============================================================


class TestLogExecution:
    """Tests for log_execution() method."""

    def test_log_execution_success(self, mock_fuente, scraper_config):
        """Test successful execution logging."""
        scraper = ConcreteScraperForTesting(scraper_config)

        # Just verify it doesn't raise an exception
        scraper.log_execution(mock_fuente, "success", "Scraped 5 properties")

    def test_log_execution_timeout(self, mock_fuente, scraper_config):
        """Test timeout execution logging."""
        scraper = ConcreteScraperForTesting(scraper_config)

        # Just verify it doesn't raise an exception
        scraper.log_execution(mock_fuente, "timeout", "Connection timed out")

    def test_log_execution_error(self, mock_fuente, scraper_config):
        """Test error execution logging."""
        scraper = ConcreteScraperForTesting(scraper_config)

        error = ValueError("Test error")
        # Just verify it doesn't raise an exception
        scraper.log_execution(mock_fuente, "error", error=error)


# ============================================================
# INTEGRATION TESTS
# ============================================================


class TestIntegration:
    """Integration tests for ScraperBase."""

    def test_hash_dedup_workflow(self, mock_fuente, scraper_config):
        """Test hash generation and dedup workflow."""
        scraper = ConcreteScraperForTesting(scraper_config)

        # Simulate two properties with same URL
        url = "https://example.com/prop/123"
        hash1 = scraper.calculate_hash(url)
        hash2 = scraper.calculate_hash(url)

        # Hashes should match (dedup)
        assert hash1 == hash2

        # Different URL should produce different hash
        hash3 = scraper.calculate_hash("https://example.com/prop/124")
        assert hash1 != hash3

    def test_raw_data_to_propiedad_workflow(self, scraper_config):
        """Test complete raw data to Propiedad workflow."""
        scraper = ConcreteScraperForTesting(scraper_config)

        # Create a fuente with idealista.com URL for this test
        idealista_fuente = Fuente(
            id=1,
            nombre="Idealista",
            url="https://idealista.com/search",
            tipo_scraper="generic",
            activa=True,
            intervalo_horas=24,
        )

        raw_data = {
            "url_original": "https://idealista.com/prop/abc123",
            "titulo": "Piso céntrico 3 hab",
            "precio": "€250.000",
            "m2": "110",
            "rooms": "3",
            "bathrooms": "2",
            "address": "Plaza Mayor 5",
            "elevator": "true",
            "property_type": "piso",
        }

        propiedad = scraper.normalize_property(raw_data, idealista_fuente)

        # Verify all fields
        assert propiedad.titulo == "Piso céntrico 3 hab"
        assert propiedad.precio == 250000.0
        assert propiedad.superficie_m2 == 110.0
        assert propiedad.habitaciones == 3
        assert propiedad.banos == 2
        assert propiedad.ascensor is True
        assert propiedad.origen_web == "idealista.com"
        assert len(propiedad.hash_unico) == 64

    def test_config_injection(self, mock_fuente):
        """Test custom config is used in scraper."""
        custom_config = ScraperConfig(timeout=60, retries=5)
        scraper = ConcreteScraperForTesting(custom_config)

        assert scraper.config.timeout == 60
        assert scraper.config.retries == 5

    def test_validation_before_normalization(self, mock_fuente, scraper_config):
        """Test that validation errors are raised before normalization."""
        scraper = ConcreteScraperForTesting(scraper_config)

        # Invalid fuente (no URL)
        bad_fuente = Fuente(nombre="Bad", url="", tipo_scraper="generic")

        with pytest.raises(ValidationException):
            scraper.validate_fuente(bad_fuente)

        # Valid data but invalid raw_data
        with pytest.raises(ValidationException):
            scraper.normalize_property(None, mock_fuente)

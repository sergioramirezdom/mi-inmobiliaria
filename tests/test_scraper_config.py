"""Unit tests for ScraperConfig and related classes."""

import json
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scraper.config import (
    ScraperConfig,
    SelectorsConfig,
    PatternsConfig,
    get_default_config,
)
from app.scraper.exceptions import ValidationException


class TestSelectorsConfig:
    """Test SelectorsConfig dataclass."""

    def test_default_selectors(self):
        """Test default selectors are all None."""
        selectors = SelectorsConfig()
        assert selectors.property_container is None
        assert selectors.price is None
        assert selectors.size is None

    def test_custom_selectors(self):
        """Test custom selector values."""
        selectors = SelectorsConfig(
            property_container="div.property",
            price="span.price",
            size="span.m2",
        )
        assert selectors.property_container == "div.property"
        assert selectors.price == "span.price"
        assert selectors.size == "span.m2"

    def test_selectors_to_dict(self):
        """Test conversion to dict excludes None values."""
        selectors = SelectorsConfig(
            property_container="div.property",
            price="span.price",
        )
        data = selectors.to_dict()
        assert "property_container" in data
        assert "price" in data
        assert "size" not in data  # None should be excluded
        assert len(data) == 2

    def test_selectors_to_dict_empty(self):
        """Test empty selectors convert to empty dict."""
        selectors = SelectorsConfig()
        data = selectors.to_dict()
        assert data == {}


class TestPatternsConfig:
    """Test PatternsConfig dataclass."""

    def test_default_patterns(self):
        """Test default regex patterns are set."""
        patterns = PatternsConfig()
        assert patterns.price_pattern == r"€\s*([\d.,]+)"
        assert patterns.m2_pattern == r"(\d+)\s*m²"
        assert patterns.rooms_pattern == r"(\d+)\s*hab"

    def test_custom_patterns(self):
        """Test custom regex patterns."""
        patterns = PatternsConfig(price_pattern=r"PRICE:\s*(\d+)")
        assert patterns.price_pattern == r"PRICE:\s*(\d+)"
        assert patterns.m2_pattern == r"(\d+)\s*m²"  # default

    def test_patterns_to_dict(self):
        """Test conversion to dict includes all patterns."""
        patterns = PatternsConfig()
        data = patterns.to_dict()
        assert "price_pattern" in data
        assert "m2_pattern" in data
        assert "rooms_pattern" in data
        assert len(data) == 5  # 5 patterns defined


class TestScraperConfig:
    """Test ScraperConfig dataclass."""

    def test_default_config(self):
        """Test default config values."""
        config = ScraperConfig()
        assert config.timeout == 30
        assert config.retries == 3
        assert config.verify_ssl is True
        assert config.auto_detect is True
        assert config.min_confidence == 0.5
        assert isinstance(config.selectors, SelectorsConfig)
        assert isinstance(config.patterns, PatternsConfig)

    def test_custom_config(self):
        """Test config with custom values."""
        config = ScraperConfig(
            timeout=60,
            retries=5,
            verify_ssl=False,
            auto_detect=False,
        )
        assert config.timeout == 60
        assert config.retries == 5
        assert config.verify_ssl is False
        assert config.auto_detect is False

    def test_config_with_selectors(self):
        """Test config with custom selectors."""
        selectors = SelectorsConfig(
            property_container="div.property",
            price="span.price",
        )
        config = ScraperConfig(selectors=selectors)
        assert config.selectors.property_container == "div.property"
        assert config.selectors.price == "span.price"

    def test_config_to_dict(self):
        """Test conversion to dict."""
        config = ScraperConfig(timeout=60, retries=5)
        data = config.to_dict()
        assert data["timeout"] == 60
        assert data["retries"] == 5
        assert "selectors" in data
        assert "patterns" in data
        assert data["auto_detect"] is True

    def test_config_from_dict_empty(self):
        """Test creating config from empty dict."""
        config = ScraperConfig.from_dict({})
        assert config.timeout == 30
        assert config.retries == 3
        assert config.auto_detect is True

    def test_config_from_dict_with_values(self):
        """Test creating config from dict with values."""
        data = {
            "timeout": 60,
            "retries": 5,
            "auto_detect": False,
            "selectors": {
                "property_container": "div.property",
                "price": "span.price",
            },
        }
        config = ScraperConfig.from_dict(data)
        assert config.timeout == 60
        assert config.retries == 5
        assert config.auto_detect is False
        assert config.selectors.property_container == "div.property"
        assert config.selectors.price == "span.price"

    def test_config_from_dict_invalid_type(self):
        """Test from_dict raises ValidationException for invalid input."""
        with pytest.raises(ValidationException):
            ScraperConfig.from_dict("not a dict")

        with pytest.raises(ValidationException):
            ScraperConfig.from_dict(123)

    def test_config_from_dict_bad_selectors(self):
        """Test from_dict handles bad selector data."""
        data = {
            "selectors": {
                "property_container": "div.property",
                "invalid_field": "will_be_ignored",  # Extra fields should be ignored
            }
        }
        # Should not raise, extra fields are ignored by dataclass
        config = ScraperConfig.from_dict(data)
        assert config.selectors.property_container == "div.property"

    def test_config_from_json_str_empty(self):
        """Test creating config from empty/None JSON string."""
        config1 = ScraperConfig.from_json_str(None)
        assert config1.timeout == 30

        config2 = ScraperConfig.from_json_str("")
        assert config2.timeout == 30

    def test_config_from_json_str_valid(self):
        """Test creating config from valid JSON string."""
        json_str = json.dumps({
            "timeout": 60,
            "retries": 5,
            "selectors": {
                "property_container": "div.property",
                "price": "span.price",
            },
        })
        config = ScraperConfig.from_json_str(json_str)
        assert config.timeout == 60
        assert config.retries == 5
        assert config.selectors.property_container == "div.property"

    def test_config_from_json_str_invalid_json(self):
        """Test from_json_str raises ValidationException for invalid JSON."""
        with pytest.raises(ValidationException):
            ScraperConfig.from_json_str("not valid json {")

    def test_config_from_fuente_notas(self):
        """Test from_fuente_notas is alias for from_json_str."""
        json_str = json.dumps({"timeout": 45})
        config = ScraperConfig.from_fuente_notas(json_str)
        assert config.timeout == 45

    def test_config_round_trip(self):
        """Test config can be serialized and deserialized."""
        original = ScraperConfig(
            timeout=60,
            retries=5,
            selectors=SelectorsConfig(
                property_container="div.property",
                price="span.price",
            ),
        )
        data = original.to_dict()
        restored = ScraperConfig.from_dict(data)
        assert restored.timeout == original.timeout
        assert restored.retries == original.retries
        assert restored.selectors.property_container == original.selectors.property_container


class TestGetDefaultConfig:
    """Test get_default_config helper function."""

    def test_get_default_config(self):
        """Test helper function returns default config."""
        config = get_default_config()
        assert config.timeout == 30
        assert config.retries == 3
        assert config.auto_detect is True

    def test_default_configs_are_independent(self):
        """Test multiple default configs are independent."""
        config1 = get_default_config()
        config2 = get_default_config()
        config1.timeout = 60
        assert config2.timeout == 30  # Should not be affected


class TestIntegration:
    """Integration tests for config workflow."""

    def test_real_world_fuente_notas(self):
        """Test loading config from realistic Fuente.notas JSON."""
        # Simulate Fuente.notas from DB
        notas_json = json.dumps({
            "selectors": {
                "property_container": "article.property-card",
                "price": "span.price",
                "size": "span.m2",
                "rooms": "span.rooms",
                "bathrooms": "span.bathrooms",
                "address": "h3.address",
                "link": "a.property-link",
                "images": "img.thumbnail",
            },
            "auto_detect": True,
            "patterns": {
                "price_pattern": r"€\s*([\d.,]+)",
                "m2_pattern": r"(\d+)\s*m²",
            },
            "timeout": 45,
            "retries": 5,
        })

        config = ScraperConfig.from_fuente_notas(notas_json)
        assert config.timeout == 45
        assert config.retries == 5
        assert config.selectors.property_container == "article.property-card"
        assert config.selectors.price == "span.price"
        assert config.patterns.price_pattern == r"€\s*([\d.,]+)"

    def test_backwards_compatibility_no_config(self):
        """Test that missing Fuente.notas defaults gracefully."""
        # Simulate old source without config
        config = ScraperConfig.from_fuente_notas(None)
        assert config.timeout == 30
        assert config.auto_detect is True

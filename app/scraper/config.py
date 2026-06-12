"""Configuration schemas and utilities for scrapers."""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any
from .exceptions import ValidationException

logger = logging.getLogger(__name__)


@dataclass
class SelectorsConfig:
    """CSS selectors for extracting property elements and fields."""

    property_container: Optional[str] = None
    link_href_contains: Optional[str] = None  # Extract links directly by href pattern (for JS-rendered pages)
    price: Optional[str] = None
    size: Optional[str] = None
    rooms: Optional[str] = None
    bathrooms: Optional[str] = None
    address: Optional[str] = None
    property_type: Optional[str] = None
    images: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    floor: Optional[str] = None
    elevator: Optional[str] = None
    garage: Optional[str] = None
    heating: Optional[str] = None
    furniture: Optional[str] = None
    pets: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PatternsConfig:
    """Regex patterns for extracting data when CSS selectors are not available."""

    price_pattern: str = r"€\s*([\d.,]+)"
    m2_pattern: str = r"(\d+)\s*m²"
    rooms_pattern: str = r"(\d+)\s*hab"
    bathrooms_pattern: str = r"(\d+)\s*ba[ñn]o"
    floor_pattern: str = r"planta\s*(\d+)|piso\s*(\d+)"

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ScraperConfig:
    """Main configuration for scraper execution."""

    # HTTP settings
    timeout: int = 120  # seconds (increased for gzip decompression)
    retries: int = 2
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    verify_ssl: bool = True
    headers: Dict[str, str] = field(default_factory=dict)

    # Selectors and patterns
    selectors: SelectorsConfig = field(default_factory=SelectorsConfig)
    patterns: PatternsConfig = field(default_factory=PatternsConfig)

    # Auto-detect settings
    auto_detect: bool = True  # Try to detect properties even without selectors
    min_confidence: float = 0.5  # Minimum confidence score for auto-detected fields

    # Detail scraper type: "puerto" | "mobilia" | "puntohogar" | "guadalete" | None
    detail_scraper_type: Optional[str] = None

    # If set, skip properties whose scraped municipio doesn't match this value
    municipio_filter: Optional[str] = None

    # Pagination settings
    pagination_param: str = "pag"            # URL param name for page number
    pagination_start: int = 1               # First page param value (page 2 onwards)
    pagination_skip_first: bool = False     # If True, page 1 uses URL as-is (no param added)
    use_results_per_page: bool = True        # Whether to add &res=N to pagination URL
    max_pages: Optional[int] = None         # Override max pages to scrape

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeout": self.timeout,
            "retries": self.retries,
            "user_agent": self.user_agent,
            "verify_ssl": self.verify_ssl,
            "headers": self.headers,
            "selectors": self.selectors.to_dict(),
            "patterns": self.patterns.to_dict(),
            "auto_detect": self.auto_detect,
            "min_confidence": self.min_confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScraperConfig":
        """Create ScraperConfig from dictionary."""
        if not isinstance(data, dict):
            raise ValidationException(f"Expected dict, got {type(data)}")

        try:
            # Filter only valid SelectorsConfig fields
            selectors_data = data.get("selectors", {})
            valid_selector_fields = {f.name for f in SelectorsConfig.__dataclass_fields__.values()}
            selectors_data = {k: v for k, v in selectors_data.items() if k in valid_selector_fields}
            selectors = SelectorsConfig(**selectors_data)

            # Filter only valid PatternsConfig fields
            patterns_data = data.get("patterns", {})
            valid_pattern_fields = {f.name for f in PatternsConfig.__dataclass_fields__.values()}
            patterns_data = {k: v for k, v in patterns_data.items() if k in valid_pattern_fields}
            patterns = PatternsConfig(**patterns_data)

            return cls(
                timeout=data.get("timeout", 30),
                retries=data.get("retries", 3),
                user_agent=data.get("user_agent", cls().user_agent),
                verify_ssl=data.get("verify_ssl", True),
                headers=data.get("headers", {}),
                selectors=selectors,
                patterns=patterns,
                auto_detect=data.get("auto_detect", True),
                min_confidence=data.get("min_confidence", 0.5),
                detail_scraper_type=data.get("detail_scraper_type", None),
                municipio_filter=data.get("municipio_filter", None),
                pagination_param=data.get("pagination_param", "pag"),
                pagination_start=data.get("pagination_start", 1),
                pagination_skip_first=data.get("pagination_skip_first", False),
                use_results_per_page=data.get("use_results_per_page", True),
                max_pages=data.get("max_pages", None),
            )
        except TypeError as e:
            raise ValidationException(f"Invalid config data: {e}")

    @classmethod
    def from_json_str(cls, json_str: Optional[str]) -> "ScraperConfig":
        """Create ScraperConfig from JSON string (e.g., from Fuente.notas)."""
        if not json_str:
            logger.info("No config JSON provided, using defaults")
            return cls()

        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise ValidationException(f"Invalid JSON in config: {e}")

    @classmethod
    def from_fuente_notas(cls, notas: Optional[str]) -> "ScraperConfig":
        """Load config from Fuente.notas field (convenience alias)."""
        return cls.from_json_str(notas)


def get_default_config() -> ScraperConfig:
    """Get default ScraperConfig instance."""
    return ScraperConfig()

"""Scraper module for Mi Inmobiliaria Personal."""

from .exceptions import (
    ScraperException,
    TimeoutException,
    ParsingException,
    ValidationException,
    DeduplicationException,
)
from .config import ScraperConfig, SelectorsConfig, PatternsConfig

__all__ = [
    "ScraperException",
    "TimeoutException",
    "ParsingException",
    "ValidationException",
    "DeduplicationException",
    "ScraperConfig",
    "SelectorsConfig",
    "PatternsConfig",
]

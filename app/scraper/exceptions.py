"""Custom exceptions for scraper module."""


class ScraperException(Exception):
    """Base exception for all scraper-related errors."""

    pass


class TimeoutException(ScraperException):
    """Raised when HTTP request or scraping operation times out."""

    pass


class ParsingException(ScraperException):
    """Raised when HTML parsing or field extraction fails."""

    pass


class ValidationException(ScraperException):
    """Raised when fuente configuration or data validation fails."""

    pass


class DeduplicationException(ScraperException):
    """Raised when hash calculation or deduplication logic fails."""

    pass

"""Configuration module for Mi Inmobiliaria Personal."""

import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/inmobiliaria")

    # Telegram Bot
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # App settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Scraper settings
    SCRAPER_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30"))
    SCRAPER_RETRIES: int = int(os.getenv("SCRAPER_RETRIES", "3"))

    @classmethod
    def validate(cls):
        """Validate required settings."""
        if not cls.DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is required")
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN environment variable is required")
        if not cls.TELEGRAM_CHAT_ID:
            raise ValueError("TELEGRAM_CHAT_ID environment variable is required")


settings = Settings()

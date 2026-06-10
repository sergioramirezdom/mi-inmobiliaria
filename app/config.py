"""Configuration module for Mi Inmobiliaria Personal."""

import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str = "") -> str:
    """Read from st.secrets (Streamlit Cloud) or env vars (local)."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


class Settings:
    """Application settings — reads from st.secrets (cloud) or .env (local)."""

    @property
    def DATABASE_URL(self) -> str:
        return _get("DATABASE_URL", "postgresql://user:pass@localhost/inmobiliaria")

    @property
    def TELEGRAM_TOKEN(self) -> str:
        return _get("TELEGRAM_TOKEN", "")

    @property
    def TELEGRAM_CHAT_ID(self) -> str:
        return _get("TELEGRAM_CHAT_ID", "")

    @property
    def DEBUG(self) -> bool:
        return _get("DEBUG", "false").lower() == "true"

    @property
    def SCRAPER_TIMEOUT(self) -> int:
        return int(_get("SCRAPER_TIMEOUT", "120"))

    @property
    def SCRAPER_RETRIES(self) -> int:
        return int(_get("SCRAPER_RETRIES", "2"))


settings = Settings()

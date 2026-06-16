"""Monitoring scraper for manually-added properties."""

import logging
from typing import Any, Dict

from .config import ScraperConfig
from .url_extractor import extract_from_url

logger = logging.getLogger(__name__)


class ManualScraper:
    """
    Used by sold_checker for properties with detail_scraper_type="manual_auto".
    Detects 404 (gone), sold keywords, and price changes.
    """

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        result = await extract_from_url(url)

        if "error" in result:
            err = result["error"]
            if "404" in err or "Not Found" in err:
                logger.info(f"HTTP 404 — marcando como no disponible: {url}")
                return {"url_original": url, "activa": False, "estado": "No disponible"}
            logger.warning(f"No se pudo verificar {url}: {err}")
            return {"url_original": url, "activa": True}

        if not result.get("activa", True):
            return {
                "url_original": url,
                "activa": False,
                "estado": result.get("estado", "Vendida"),
            }

        data: Dict[str, Any] = {"url_original": url, "activa": True}
        if "precio" in result:
            data["precio"] = result["precio"]
        return data

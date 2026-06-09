"""Scraper orchestrator - chooses, runs, and saves scrapers."""

import logging
import time
from typing import Optional

from sqlmodel import Session, select

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Fuente, Propiedad
from db.database import PropiedadCRUD
from .base import ScraperBase
from .config import ScraperConfig
from .exceptions import ScraperException, ValidationException
from .generic import GenericScraper


class ScraperRunner:
    """Orchestrates scraper execution, deduplication, and DB persistence."""

    def __init__(self, db_session: Session, config: Optional[ScraperConfig] = None):
        """
        Initialize ScraperRunner.

        Args:
            db_session: SQLModel database session
            config: Optional custom ScraperConfig
        """
        self.db_session = db_session
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)

    async def run_scraper(self, fuente: Fuente) -> dict:
        """
        Execute scraper for a fuente, deduplicate, and save to DB.

        Args:
            fuente: Source to scrape

        Returns:
            Statistics dictionary with results

        Raises:
            ValidationException: If fuente is invalid
            ScraperException: If scraping fails
        """
        if not fuente:
            raise ValidationException("Fuente cannot be None")

        start_time = time.time()
        stats = {
            "fuente_id": fuente.id,
            "nombre": fuente.nombre,
            "nuevas": 0,
            "duplicadas": 0,
            "errores": 0,
            "tiempo_segundos": 0.0,
        }

        try:
            self.logger.info(f"🚀 Starting scraper for {fuente.nombre}...")

            # Get appropriate scraper
            scraper = self._get_scraper(fuente)

            # Execute scraper
            raw_data_list = await scraper.scrape(fuente)
            self.logger.info(f"📦 Scraped {len(raw_data_list)} properties from {fuente.nombre}")

            # Process each property
            for idx, raw_data in enumerate(raw_data_list, 1):
                try:
                    # Normalize raw data to Propiedad model
                    propiedad = scraper.normalize_property(raw_data, fuente)

                    # Check for duplicates
                    if self._check_duplicate(propiedad):
                        self.logger.debug(f"⏭️ Duplicate: {propiedad.titulo} ({propiedad.hash_unico[:8]}...)")
                        stats["duplicadas"] += 1
                        continue

                    # Save to database
                    self._save_propiedad(propiedad)
                    self.logger.debug(f"✓ Saved: {propiedad.titulo} ({propiedad.hash_unico[:8]}...)")
                    stats["nuevas"] += 1

                except Exception as e:
                    self.logger.warning(f"⚠️ Error processing property {idx}: {e}")
                    stats["errores"] += 1
                    continue

            # Calculate elapsed time
            elapsed = time.time() - start_time
            stats["tiempo_segundos"] = round(elapsed, 2)

            self.logger.info(
                f"✓ Scraper completed for {fuente.nombre}: "
                f"nuevas={stats['nuevas']}, duplicadas={stats['duplicadas']}, "
                f"errores={stats['errores']}, tiempo={stats['tiempo_segundos']}s"
            )

            return stats

        except Exception as e:
            elapsed = time.time() - start_time
            stats["tiempo_segundos"] = round(elapsed, 2)
            self.logger.error(f"❌ Scraper failed for {fuente.nombre}: {e}")
            stats["error"] = str(e)
            return stats

    # ============================================================
    # PRIVATE HELPER METHODS
    # ============================================================

    def _get_scraper(self, fuente: Fuente) -> ScraperBase:
        """
        Factory method to get correct scraper instance.

        Args:
            fuente: Source with tipo_scraper specified

        Returns:
            Scraper instance (GenericScraper or specific implementation)

        Raises:
            ValueError: If scraper type is unknown
        """
        scraper_type = fuente.tipo_scraper or "generic"

        if scraper_type == "generic":
            # Load config from Fuente.notas if available
            config = ScraperConfig.from_fuente_notas(fuente.notas) if fuente.notas else self.config
            return GenericScraper(config)

        # Future: Add specific scrapers
        # elif scraper_type == "idealista":
        #     return IdealistaScraper(config)
        # elif scraper_type == "fotocasa":
        #     return FotocasaScraper(config)

        raise ValueError(f"Unknown scraper type: {scraper_type}")

    def _check_duplicate(self, propiedad: Propiedad) -> bool:
        """
        Check if property already exists by hash.

        Args:
            propiedad: Property to check

        Returns:
            True if duplicate exists, False otherwise
        """
        try:
            stmt = select(Propiedad).where(Propiedad.hash_unico == propiedad.hash_unico)
            existing = self.db_session.exec(stmt).first()
            return existing is not None
        except Exception as e:
            self.logger.warning(f"Error checking duplicate: {e}")
            return False

    def _save_propiedad(self, propiedad: Propiedad) -> None:
        """
        Save property to database.

        Args:
            propiedad: Property model to save

        Raises:
            Exception: If DB save fails
        """
        try:
            self.db_session.add(propiedad)
            self.db_session.commit()
            self.db_session.refresh(propiedad)
        except Exception as e:
            self.db_session.rollback()
            raise Exception(f"Failed to save property: {e}")

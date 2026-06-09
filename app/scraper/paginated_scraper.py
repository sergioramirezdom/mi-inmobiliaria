"""Paginated scraper - handles multiple pages and deduplication."""

import logging
from typing import List, Optional, Dict
from sqlmodel import Session, select

from .base import ScraperBase
from .generic import GenericScraper
from .puerto_inmobiliaria import PuertoInmobiliariaScraper
from .config import ScraperConfig
from db.models import Fuente, Propiedad


class PaginatedScraper:
    """Scraper that handles pagination and smart deduplication."""

    def __init__(self, db_session: Session, config: Optional[ScraperConfig] = None):
        """Initialize paginated scraper."""
        self.db_session = db_session
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)
        self.generic_scraper = GenericScraper(config)
        self.detail_scraper = PuertoInmobiliariaScraper(config)

    async def scrape_all_pages(
        self,
        fuente: Fuente,
        results_per_page: int = 48,
        max_pages: Optional[int] = None
    ) -> dict:
        """
        Scrape all pages from a paginated source.

        Args:
            fuente: Source configuration
            results_per_page: Number of results per page (res parameter, default 48)
            max_pages: Maximum pages to scrape (None = all)

        Returns:
            Stats dictionary with results
        """
        stats = {
            "fuente_id": fuente.id,
            "nombre": fuente.nombre,
            "nuevas": 0,
            "duplicadas": 0,
            "errores": 0,
            "paginas_procesadas": 0,
            "urls_encontradas": 0,
        }

        # Load config from fuente.notas if available
        if fuente.notas:
            try:
                fuente_config = ScraperConfig.from_fuente_notas(fuente.notas)
                # Update generic scraper with fuente-specific config
                self.generic_scraper.config = fuente_config
            except Exception as e:
                self.logger.warning(f"Could not load config from fuente.notas: {e}")

        try:
            page = 1
            consecutive_empty_pages = 0

            while True:
                if max_pages and page > max_pages:
                    self.logger.info(f"Reached max pages limit: {max_pages}")
                    break

                self.logger.info(f"\n{'='*80}")
                self.logger.info(f"📄 Processing page {page}...")
                self.logger.info(f"{'='*80}")

                # Build URL with pagination parameters
                if "?" in fuente.url:
                    page_url = f"{fuente.url}&res={results_per_page}&pag={page}"
                else:
                    page_url = f"{fuente.url}?res={results_per_page}&pag={page}"

                # Scrape the page
                try:
                    # Create a temporary copy of fuente with the paginated URL
                    temp_fuente = Fuente(
                        id=fuente.id,
                        nombre=fuente.nombre,
                        url=page_url,
                        tipo_scraper=fuente.tipo_scraper,
                        activa=fuente.activa,
                        intervalo_horas=fuente.intervalo_horas,
                        notas=fuente.notas
                    )
                    urls_on_page = await self.generic_scraper.scrape(temp_fuente)
                except Exception as e:
                    self.logger.error(f"Error scraping page {page}: {e}")
                    break  # Stop pagination if we can't scrape

                if not urls_on_page:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 2:
                        self.logger.info(f"No properties found on page {page}, stopping pagination")
                        break
                    self.logger.info(f"Page {page} empty, trying next page...")
                    page += 1
                    continue

                # Reset empty page counter
                consecutive_empty_pages = 0
                self.logger.info(f"Found {len(urls_on_page)} properties on page {page}")
                stats["urls_encontradas"] += len(urls_on_page)

                # Check if we got fewer properties than expected (indicates last page)
                if len(urls_on_page) < results_per_page - 5:  # Allow 5 property margin
                    self.logger.info(f"Page {page} has fewer properties ({len(urls_on_page)} < {results_per_page}), likely last page")
                    will_continue_after = False
                else:
                    will_continue_after = True

                # Process each property
                for raw_data in urls_on_page:
                    try:
                        url_original = raw_data.get("url_original")
                        if not url_original:
                            stats["errores"] += 1
                            continue

                        # Check if already in DB
                        hash_unico = self.generic_scraper.calculate_hash(url_original)

                        stmt = select(Propiedad).where(Propiedad.hash_unico == hash_unico)
                        existing = self.db_session.exec(stmt).first()

                        if existing:
                            self.logger.debug(f"⏭️ Duplicate found: {existing.titulo}")
                            stats["duplicadas"] += 1
                            continue

                        # Enrich with details
                        self.logger.debug(f"Enriching new property: {url_original[:60]}...")
                        try:
                            details = await self.detail_scraper.scrape_property_details(url_original)
                            raw_data.update(details)
                        except Exception as e:
                            self.logger.warning(f"Could not enrich property: {e}")

                        # Normalize and save
                        propiedad = self.generic_scraper.normalize_property(raw_data, fuente)
                        self.db_session.add(propiedad)
                        self.db_session.commit()
                        self.db_session.refresh(propiedad)

                        self.logger.debug(f"✓ Saved new property: {propiedad.titulo}")
                        stats["nuevas"] += 1

                    except Exception as e:
                        self.logger.warning(f"Error processing property: {e}")
                        stats["errores"] += 1
                        continue

                stats["paginas_procesadas"] += 1

                # Stop after last page if detected
                if not will_continue_after:
                    self.logger.info(f"Reached last page ({page}), stopping pagination")
                    break

                page += 1

            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"✅ Pagination complete!")
            self.logger.info(f"   Total pages: {stats['paginas_procesadas']}")
            self.logger.info(f"   Total URLs: {stats['urls_encontradas']}")
            self.logger.info(f"   New properties: {stats['nuevas']}")
            self.logger.info(f"   Duplicates skipped: {stats['duplicadas']}")
            self.logger.info(f"{'='*80}")

            return stats

        except Exception as e:
            self.logger.error(f"❌ Pagination failed: {e}")
            stats["error"] = str(e)
            return stats

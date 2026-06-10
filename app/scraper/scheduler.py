"""Scheduler for automated scraping based on fuente intervals."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from db.database import engine
from db.models import Fuente, Propiedad, FiltroAlerta
from .runner import ScraperRunner
from notifications.telegram import TelegramNotifier
from notifications.filter_matcher import FilterMatcher

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Orchestrates scheduled scraping for multiple sources."""

    def __init__(self, check_interval_minutes: int = 1, results_per_page: int = 48):
        """
        Initialize scheduler.

        Args:
            check_interval_minutes: How often to check for due scrapes (default 1 min)
            results_per_page: Results per page for paginated scraping (default 48)
        """
        self.check_interval_minutes = check_interval_minutes
        self.results_per_page = results_per_page
        self.logger = logging.getLogger(__name__)

    async def start_daemon(self) -> None:
        """Start background scheduler daemon (runs continuously)."""
        self.logger.info("🚀 ScraperScheduler daemon started")
        self.logger.info(f"⏰ Check interval: {self.check_interval_minutes} minute(s)")

        try:
            while True:
                await self.check_and_scrape()
                await asyncio.sleep(self.check_interval_minutes * 60)
        except KeyboardInterrupt:
            self.logger.info("⏹️ ScraperScheduler daemon stopped (KeyboardInterrupt)")
        except Exception as e:
            self.logger.error(f"❌ ScraperScheduler error: {e}", exc_info=True)
            raise

    async def check_and_scrape(self) -> None:
        """Check all active fuentes and scrape if interval has passed."""
        try:
            with Session(engine) as session:
                # Get all active fuentes
                stmt = select(Fuente).where(Fuente.activa == True)
                fuentes = session.exec(stmt).all()

                if not fuentes:
                    self.logger.debug("No active fuentes found")
                    return

                self.logger.debug(f"🔍 Checking {len(fuentes)} active fuente(s)...")

                for fuente in fuentes:
                    if self._should_scrape(fuente):
                        await self._scrape_fuente(fuente)
                    else:
                        next_scrape = self._get_next_scrape_time(fuente)
                        time_until = self._format_time_delta(next_scrape)
                        self.logger.debug(
                            f"⏭️ {fuente.nombre}: Too soon (next in {time_until})"
                        )

        except Exception as e:
            self.logger.error(f"Error in check_and_scrape: {e}", exc_info=True)

    async def _scrape_fuente(self, fuente: Fuente) -> None:
        """Scrape a single fuente and send notifications based on filters."""
        try:
            self.logger.info(f"🚀 Starting scrape for {fuente.nombre}...")

            with Session(engine) as session:
                runner = ScraperRunner(session)

                # Run paginated scraper
                stats = await runner.run_paginated_scraper(
                    fuente,
                    results_per_page=self.results_per_page
                )

                # Log results
                nuevas = stats.get("nuevas", 0)
                duplicadas = stats.get("duplicadas", 0)
                errores = stats.get("errores", 0)
                paginas = stats.get("paginas_procesadas", 0)
                tiempo = stats.get("tiempo_segundos", 0)

                self.logger.info(
                    f"✅ Scrape completed: {fuente.nombre} | "
                    f"nuevas={nuevas}, duplicadas={duplicadas}, "
                    f"errores={errores}, páginas={paginas}, tiempo={tiempo}s"
                )

                # Update ultima_ejecucion in DB
                self._update_execution_time(fuente, session)

                # Send notifications if there are new properties
                if nuevas > 0:
                    self.logger.warning(
                        f"🎯 {fuente.nombre}: {nuevas} nuevas propiedades encontradas!"
                    )
                    await self._send_notifications(fuente, stats, session)

        except Exception as e:
            self.logger.error(f"❌ Error scraping {fuente.nombre}: {e}", exc_info=True)

    async def _send_notifications(
        self, fuente: Fuente, stats: dict, session: Session
    ) -> None:
        """Send Telegram notifications based on filters."""
        try:
            notifier = TelegramNotifier()

            # Get all active filters
            stmt = select(FiltroAlerta).where(FiltroAlerta.activo == True)
            filtros = session.exec(stmt).all()

            if not filtros:
                # No filters: send summary only
                self.logger.debug("No active filters, sending summary only")
                await notifier.send_scraping_summary(stats, fuente)
                return

            # Get newly added properties for this fuente
            nuevas_count = stats.get("nuevas", 0)
            if nuevas_count == 0:
                return

            stmt = (
                select(Propiedad)
                .where(Propiedad.fuente_id == fuente.id)
                .order_by(Propiedad.created_at.desc())
                .limit(nuevas_count)
            )
            nuevas_propiedades = session.exec(stmt).all()

            # Apply filters and collect matches
            filtro_matches = {}
            for filtro in filtros:
                matches = FilterMatcher.get_matching_properties(nuevas_propiedades, filtro)
                if matches:
                    filtro_matches[filtro] = matches
                    self.logger.info(
                        f"🎯 Filter '{filtro.nombre}': {len(matches)} propiedades coinciden"
                    )

            # Send notifications
            if filtro_matches:
                # Send summary with filter info + detailed alerts
                await notifier.send_filtered_summary(fuente, stats, filtro_matches)
            else:
                # New properties but no filter matches
                await notifier.send_no_matches_summary(fuente, stats, len(filtros))

        except Exception as e:
            self.logger.error(f"Error sending notifications: {e}", exc_info=True)

    def _should_scrape(self, fuente: Fuente) -> bool:
        """
        Determine if a fuente should be scraped now.

        Returns:
            True if enough time has passed since last execution, False otherwise
        """
        if not fuente.ultima_ejecucion:
            # Never been executed
            return True

        # Calculate how much time has passed
        time_passed = datetime.utcnow() - fuente.ultima_ejecucion
        time_needed = timedelta(hours=fuente.intervalo_horas)

        return time_passed >= time_needed

    def _get_next_scrape_time(self, fuente: Fuente) -> datetime:
        """Calculate when this fuente should be scraped next."""
        if not fuente.ultima_ejecucion:
            return datetime.utcnow()

        return fuente.ultima_ejecucion + timedelta(hours=fuente.intervalo_horas)

    def _format_time_delta(self, target_time: datetime) -> str:
        """Format time delta in human-readable format."""
        delta = target_time - datetime.utcnow()

        if delta.total_seconds() < 0:
            return "now"

        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _update_execution_time(self, fuente: Fuente, session: Session) -> None:
        """Update fuente.ultima_ejecucion in database."""
        try:
            fuente.ultima_ejecucion = datetime.utcnow()
            session.add(fuente)
            session.commit()
            self.logger.debug(f"✓ Updated ultima_ejecucion for {fuente.nombre}")
        except Exception as e:
            self.logger.warning(f"Could not update ultima_ejecucion: {e}")
            session.rollback()

"""Telegram notifications for property alerts."""

import os
import logging
from typing import List, Optional
from datetime import datetime

import httpx
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Propiedad, FiltroAlerta, Fuente
from .filter_matcher import FilterMatcher
from config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self):
        """Initialize Telegram notifier."""
        self.token = settings.TELEGRAM_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}"

        if not self.token or not self.chat_id:
            logger.warning(
                "⚠️ Telegram credentials not configured. "
                "Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env or st.secrets"
            )

    async def send_message(self, text: str) -> bool:
        """
        Send a message to Telegram.

        Args:
            text: Message text (supports Markdown)

        Returns:
            True if successful, False otherwise
        """
        if not self.token or not self.chat_id:
            logger.warning("Cannot send Telegram message: credentials not configured")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )

                if response.status_code == 200:
                    logger.debug("✓ Telegram message sent")
                    return True
                else:
                    logger.warning(
                        f"Telegram API error: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def send_test_message(self) -> bool:
        """Send a test message."""
        text = (
            "🧪 *Test Message*\n"
            f"✅ Telegram integration working!\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        return await self.send_message(text)

    async def send_scraping_summary(
        self,
        stats: dict,
        fuente: Fuente,
        filtros_aplicados: List[FiltroAlerta] = None,
    ) -> bool:
        """
        Send summary of scraping results.

        Args:
            stats: Statistics from scraper
            fuente: Fuente that was scraped
            filtros_aplicados: Active filters that found matches

        Returns:
            True if message sent
        """
        nuevas = stats.get("nuevas", 0)
        duplicadas = stats.get("duplicadas", 0)
        errores = stats.get("errores", 0)
        paginas = stats.get("paginas_procesadas", 0)
        tiempo = stats.get("tiempo_segundos", 0)

        # Build message
        text = f"🎯 *{fuente.nombre}*\n"
        text += f"✅ Nuevas: {nuevas}\n"
        text += f"⚠️ Duplicadas: {duplicadas}\n"
        text += f"❌ Errores: {errores}\n"

        if paginas > 0:
            text += f"📄 Páginas: {paginas}\n"

        text += f"⏱️ Tiempo: {tiempo}s\n"
        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"

        # Add filter info if applicable
        if filtros_aplicados:
            text += f"\n\n🔍 *Filtros Aplicados:*\n"
            for filtro in filtros_aplicados:
                text += f"• {filtro.nombre}\n"

        return await self.send_message(text)

    async def send_property_alerts(
        self,
        propiedades: List[Propiedad],
        filtro: FiltroAlerta,
        fuente: Fuente,
    ) -> bool:
        """
        Send detailed alerts for properties matching a filter.

        Args:
            propiedades: Properties that match the filter
            filtro: Filter that was applied
            fuente: Source of properties

        Returns:
            True if message sent
        """
        if not propiedades:
            return False

        # Build message header
        text = f"🏠 *{fuente.nombre} - {filtro.nombre}*\n"
        text += f"Found {len(propiedades)} matching properties:\n\n"

        # Add properties (limit to 5 to avoid message length issues)
        for i, prop in enumerate(propiedades[:5], 1):
            precio_str = f"€{prop.precio:,.0f}" if prop.precio else "N/A"
            m2_str = f"{prop.superficie_m2:.0f}m²" if prop.superficie_m2 else "N/A"
            hab_str = f"{prop.habitaciones} hab" if prop.habitaciones else "N/A"

            # Property line
            text += f"{i}. {prop.titulo or 'Sin título'}\n"
            text += f"   💰 {precio_str} | {m2_str} | {hab_str}\n"

            if prop.direccion:
                text += f"   📍 {prop.direccion}\n"

            # URL
            url_short = prop.url_original[:50] + "..." if len(prop.url_original) > 50 else prop.url_original
            text += f"   🔗 [Ver ficha]({prop.url_original})\n\n"

        if len(propiedades) > 5:
            text += f"... y {len(propiedades) - 5} más\n"

        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"

        return await self.send_message(text)

    async def send_filtered_summary(
        self,
        fuente: Fuente,
        stats: dict,
        filtro_matches: dict,  # {FiltroAlerta: [Propiedad]}
    ) -> bool:
        """
        Send comprehensive summary with filter results.

        Args:
            fuente: Source that was scraped
            stats: Overall scraping statistics
            filtro_matches: Dictionary mapping filters to matching properties

        Returns:
            True if any message sent
        """
        nuevas = stats.get("nuevas", 0)

        # If no new properties, don't send notifications
        if nuevas == 0:
            logger.debug("No new properties, skipping notifications")
            return False

        # Send main summary
        filtros_con_matches = [f for f, props in filtro_matches.items() if props]
        await self.send_scraping_summary(stats, fuente, filtros_con_matches)

        # Send detailed alerts for each filter with matches
        any_sent = False
        for filtro, propiedades in filtro_matches.items():
            if propiedades:
                sent = await self.send_property_alerts(propiedades, filtro, fuente)
                any_sent = any_sent or sent

        return any_sent

    async def send_price_drop_alerts(self, bajadas: list, fuente: Fuente) -> bool:
        """Send Telegram alerts for price drops."""
        if not bajadas:
            return False

        text = f"📉 *Bajadas de precio — {fuente.nombre}*\n\n"
        for b in bajadas[:10]:
            text += f"🏠 {b['titulo'][:50]}\n"
            text += f"   {b['precio_anterior']:,.0f}€ → *{b['precio_nuevo']:,.0f}€* (-{b['bajada_pct']}%)\n"
            text += f"   🔗 [Ver ficha]({b['url']})\n\n"

        if len(bajadas) > 10:
            text += f"_...y {len(bajadas) - 10} más_\n"

        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"
        return await self.send_message(text)

    async def send_no_matches_summary(
        self,
        fuente: Fuente,
        stats: dict,
        num_filtros: int,
    ) -> bool:
        """
        Send summary when there are new properties but no filter matches.

        Args:
            fuente: Source that was scraped
            stats: Scraping statistics
            num_filtros: Number of active filters

        Returns:
            True if message sent
        """
        nuevas = stats.get("nuevas", 0)

        if nuevas == 0:
            return False

        text = f"🎯 *{fuente.nombre}*\n"
        text += f"✅ Nuevas propiedades: {nuevas}\n"
        text += f"❌ Sin coincidencias con filtros ({num_filtros} activos)\n"
        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"

        return await self.send_message(text)

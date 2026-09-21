"""Telegram notifications for property alerts."""

import asyncio
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
from .alert_routing import resolve_chat_id
from config import settings
from logging_setup import install_log_redaction

logger = logging.getLogger(__name__)

# The bot token travels in the request URL: whatever process can send a
# message must never log it (issue #55). Idempotent; entrypoints call it too.
install_log_redaction()

_sleep = asyncio.sleep  # indirection so tests never really wait between retries

# Delivery policy: transient failures (429, 5xx, timeouts/network errors) are
# retried with exponential backoff; a 429 waits the server's retry_after, unless
# that is longer than MAX_RETRY_AFTER_SECONDS (then the send fails immediately).
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 30


def _error_description(response: httpx.Response) -> str:
    """Telegram's error ``description`` (falls back to the raw body)."""
    try:
        return str(response.json().get("description", ""))
    except Exception:
        return response.text


def _retry_after(response: httpx.Response) -> Optional[float]:
    """Seconds Telegram asks us to wait on a 429 (body parameter or header)."""
    try:
        value = response.json()["parameters"]["retry_after"]
    except Exception:
        value = response.headers.get("Retry-After")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self):
        """Initialize Telegram notifier."""
        self.token = settings.TELEGRAM_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        # Delivery results, so callers can report failed sends (a failed send
        # is otherwise only a False return value).
        self.sent_count = 0
        self.failed_count = 0

        if not self.token or not self.chat_id:
            logger.warning(
                "⚠️ Telegram credentials not configured. "
                "Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env or st.secrets"
            )

    async def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        """
        Send a message to Telegram.

        Markdown that Telegram cannot parse (a raw ``_``/``*``/``[`` in a
        scraped title) is re-sent as plain text; transient failures are
        retried with backoff (see ``MAX_ATTEMPTS``). Every outcome is counted
        in ``sent_count``/``failed_count`` and a final failure is logged at
        ERROR.

        Args:
            text: Message text (supports Markdown)
            chat_id: Optional chat id override. Defaults to the global
                ``settings.TELEGRAM_CHAT_ID`` when not provided.

        Returns:
            True if delivered, False otherwise
        """
        target_chat_id = chat_id or self.chat_id

        if not self.token or not target_chat_id:
            logger.warning("Cannot send Telegram message: credentials not configured")
            return False

        delivered = await self._deliver(text, target_chat_id)
        if delivered:
            self.sent_count += 1
        else:
            self.failed_count += 1
        return delivered

    async def _deliver(self, text: str, chat_id: str) -> bool:
        """POST the message, retrying transient failures (never logs the token)."""
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        attempt = 0

        async with httpx.AsyncClient() as client:
            while True:
                attempt += 1
                delay: Optional[float] = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
                try:
                    response = await client.post(
                        f"{self.api_url}/sendMessage", json=payload, timeout=10
                    )
                except httpx.TransportError as e:  # timeouts and network errors
                    reason = f"{type(e).__name__}: {e}"
                except Exception as e:
                    logger.error(f"Error sending Telegram message to {chat_id}: {e}")
                    return False
                else:
                    if response.status_code == 200:
                        logger.debug("✓ Telegram message sent")
                        return True

                    description = _error_description(response)
                    reason = f"HTTP {response.status_code} - {description}"

                    if (
                        response.status_code == 400
                        and "parse_mode" in payload
                        and "parse" in description.lower()
                    ):
                        # Unparseable Markdown: still deliver, as plain text.
                        logger.warning(
                            f"Telegram could not parse Markdown ({description}); "
                            "re-sending as plain text"
                        )
                        del payload["parse_mode"]
                        attempt -= 1
                        continue

                    if response.status_code == 429:
                        delay = _retry_after(response) or delay
                        if delay > MAX_RETRY_AFTER_SECONDS:
                            delay = None
                    elif response.status_code < 500:
                        delay = None  # 4xx that a retry cannot fix

                if delay is None or attempt >= MAX_ATTEMPTS:
                    logger.error(
                        f"Telegram delivery to {chat_id} failed after "
                        f"{attempt} attempt(s): {reason}"
                    )
                    return False

                logger.warning(
                    f"Telegram send attempt {attempt} failed ({reason}); "
                    f"retrying in {delay:g}s"
                )
                await _sleep(delay)

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
        text += f"{len(propiedades)} propiedad(es) encontrada(s):\n\n"

        # Add properties (limit to 5 to avoid message length issues)
        for i, prop in enumerate(propiedades[:5], 1):
            precio_str = f"€{prop.precio:,.0f}" if prop.precio else "N/A"
            m2_str = f"{prop.superficie_m2:.0f}m²" if prop.superficie_m2 else "N/A"
            hab_str = f"{prop.habitaciones} hab" if prop.habitaciones else "N/A"

            # Property line
            text += f"{i}. {prop.titulo or 'Sin título'}\n"
            text += f"   💰 {precio_str} | {m2_str} | {hab_str}\n"

            # Show zona_normalizada (canonical), barrio (raw) as fallback, then direccion
            location_parts = []
            if prop.zona_normalizada:
                location_parts.append(prop.zona_normalizada)
            if prop.barrio and prop.barrio != prop.zona_normalizada:
                location_parts.append(prop.barrio)
            if prop.direccion and prop.direccion != prop.barrio:
                location_parts.append(prop.direccion)
            if location_parts:
                text += f"   📍 {' · '.join(location_parts)}\n"

            # URL
            url_short = prop.url_original[:50] + "..." if len(prop.url_original) > 50 else prop.url_original
            text += f"   🔗 [Ver ficha]({prop.url_original})\n\n"

        if len(propiedades) > 5:
            text += f"... y {len(propiedades) - 5} más\n"

        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"

        chat_id = resolve_chat_id(
            getattr(filtro, "chat_id_telegram", None), self.chat_id
        )
        return await self.send_message(text, chat_id=chat_id)

    async def send_filtered_summary(
        self,
        fuente: Fuente,
        stats: dict,
        filtro_matches: list,  # [(FiltroAlerta, [Propiedad])]
    ) -> bool:
        """
        Send comprehensive summary with filter results.

        Args:
            fuente: Source that was scraped
            stats: Overall scraping statistics
            filtro_matches: List of (filtro, matching_properties) tuples

        Returns:
            True if any message sent
        """
        nuevas = stats.get("nuevas", 0)

        if nuevas == 0:
            logger.debug("No new properties, skipping notifications")
            return False

        filtros_con_matches = [f for f, _ in filtro_matches]
        await self.send_scraping_summary(stats, fuente, filtros_con_matches)

        any_sent = False
        for filtro, propiedades in filtro_matches:
            sent = await self.send_property_alerts(propiedades, filtro, fuente)
            any_sent = any_sent or sent

        return any_sent

    async def send_price_drop_alerts(
        self,
        bajadas: list,
        fuente: Optional[Fuente] = None,
        source_label: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Send Telegram alerts for price drops.

        The header source name is ``fuente.nombre`` when a ``fuente`` is given,
        otherwise the generic ``source_label`` (e.g. ``"favoritas"``). The body
        is identical regardless of source. ``chat_id`` overrides the target chat.
        """
        if not bajadas:
            return False

        source_name = fuente.nombre if fuente is not None else (source_label or "")
        text = f"📉 *Bajadas de precio — {source_name}*\n\n"
        for b in bajadas[:10]:
            text += f"🏠 {b['titulo'][:50]}\n"
            text += f"   {b['precio_anterior']:,.0f}€ → *{b['precio_nuevo']:,.0f}€* (-{b['bajada_pct']}%)\n"
            text += f"   🔗 [Ver ficha]({b['url']})\n\n"

        if len(bajadas) > 10:
            text += f"_...y {len(bajadas) - 10} más_\n"

        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"
        return await self.send_message(text, chat_id=chat_id)

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

    async def send_sold_properties_alert(self, vendidas: list) -> bool:
        """Send Telegram alert listing properties that were just marked as sold."""
        if not vendidas:
            return False

        text = f"🚫 *Propiedades vendidas/reservadas* ({len(vendidas)})\n\n"
        for v in vendidas[:10]:
            precio_str = f"{v['precio']:,.0f}€" if v.get("precio") else "N/A"
            text += f"🏠 {v['titulo'][:50]}\n"
            text += f"   Estado: *{v['estado']}* | Precio: {precio_str}\n"
            text += f"   🔗 [Ver ficha]({v['url']})\n\n"

        if len(vendidas) > 10:
            text += f"_...y {len(vendidas) - 10} más_\n"

        text += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"
        return await self.send_message(text)

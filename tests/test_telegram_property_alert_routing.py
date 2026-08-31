"""send_property_alerts routes to the alert's chat; no global retry on failure."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pytest

from notifications.telegram import TelegramNotifier


def _prop(i=1):
    return SimpleNamespace(
        titulo=f"Piso {i}",
        precio=100000,
        superficie_m2=90,
        habitaciones=3,
        zona_normalizada="Centro",
        barrio="Centro",
        direccion="Calle Falsa 123",
        url_original=f"https://example.com/p/{i}",
    )


def _notifier():
    n = TelegramNotifier()
    n.token = "TESTTOKEN"
    n.chat_id = "GLOBAL_CHAT"
    n.api_url = "https://api.telegram.org/botTESTTOKEN"
    return n


async def test_routes_to_filtro_chat_id_when_set():
    n = _notifier()
    calls = []

    async def fake_send(text, chat_id=None):
        calls.append(chat_id)
        return True

    n.send_message = fake_send
    filtro = SimpleNamespace(nombre="Mi alerta", chat_id_telegram="-100555")

    await n.send_property_alerts([_prop()], filtro, SimpleNamespace(nombre="Fuente X"))

    assert calls == ["-100555"]


async def test_routes_to_global_when_filtro_chat_id_empty():
    n = _notifier()
    calls = []

    async def fake_send(text, chat_id=None):
        calls.append(chat_id)
        return True

    n.send_message = fake_send
    filtro = SimpleNamespace(nombre="Mi alerta", chat_id_telegram="")

    await n.send_property_alerts([_prop()], filtro, SimpleNamespace(nombre="Fuente X"))

    assert calls == ["GLOBAL_CHAT"]


async def test_no_global_retry_when_configured_chat_send_fails():
    n = _notifier()
    calls = []

    async def fake_send(text, chat_id=None):
        calls.append(chat_id)
        return False  # Telegram API error for the configured (invalid) chat id

    n.send_message = fake_send
    filtro = SimpleNamespace(nombre="Mi alerta", chat_id_telegram="-100INVALID")

    result = await n.send_property_alerts(
        [_prop()], filtro, SimpleNamespace(nombre="Fuente X")
    )

    assert result is False
    assert calls == ["-100INVALID"]  # exactly one attempt, no fallback to GLOBAL_CHAT


async def test_filtered_summary_sends_general_summary_to_global_only_alerts_routed():
    n = _notifier()
    calls = []

    async def fake_send(text, chat_id=None):
        calls.append((text.split("\n", 1)[0], chat_id))
        return True

    n.send_message = fake_send
    fuente = SimpleNamespace(nombre="Fuente X")
    filtro = SimpleNamespace(nombre="Mi alerta", chat_id_telegram="-100555")

    await n.send_filtered_summary(
        fuente, {"nuevas": 1}, [(filtro, [_prop()])]
    )

    # First send is the general scraping summary -> global chat (no override).
    assert calls[0][1] is None
    # The per-filter detail block -> the alert's own chat.
    assert ("-100555" in [c[1] for c in calls[1:]])
    assert "GLOBAL_CHAT" not in [c[1] for c in calls]


async def test_price_drop_alerts_still_target_global_chat():
    n = _notifier()
    calls = []

    async def fake_send(text, chat_id=None):
        calls.append(chat_id)
        return True

    n.send_message = fake_send

    await n.send_price_drop_alerts(
        [
            {
                "titulo": "Piso",
                "url": "https://example.com/p/1",
                "precio_anterior": 200000,
                "precio_nuevo": 180000,
                "bajada_pct": 10,
            }
        ],
        SimpleNamespace(nombre="Fuente X"),
    )

    assert calls == [None]  # no override -> global chat

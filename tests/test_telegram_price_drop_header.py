"""send_price_drop_alerts header: fuente name vs generic source_label.

The message BODY must be identical regardless of which path produced the drop;
only the first (header) line differs.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from notifications.telegram import TelegramNotifier


def _notifier():
    n = TelegramNotifier()
    n.token = "TESTTOKEN"
    n.chat_id = "GLOBAL_CHAT"
    n.api_url = "https://api.telegram.org/botTESTTOKEN"
    return n


_BAJADAS = [
    {
        "titulo": "Piso en el centro",
        "url": "https://example.com/p/1",
        "precio_anterior": 200000,
        "precio_nuevo": 180000,
        "bajada_pct": 10,
    }
]


async def _capture(**kwargs):
    n = _notifier()
    sent = {}

    async def fake_send(text, chat_id=None):
        sent["text"] = text
        return True

    n.send_message = fake_send
    await n.send_price_drop_alerts(_BAJADAS, **kwargs)
    return sent["text"]


async def test_header_uses_fuente_name_when_fuente_given():
    text = await _capture(fuente=SimpleNamespace(nombre="Idealista Cádiz"))
    assert "Idealista Cádiz" in text.split("\n", 1)[0]


async def test_header_uses_source_label_when_no_fuente():
    text = await _capture(fuente=None, source_label="favoritas")
    assert "favoritas" in text.split("\n", 1)[0]


async def test_body_lines_identical_across_both_paths():
    from_fuente = await _capture(fuente=SimpleNamespace(nombre="Idealista"))
    from_label = await _capture(fuente=None, source_label="favoritas")
    body_fuente = from_fuente.split("\n", 1)[1]
    body_label = from_label.split("\n", 1)[1]
    # Timestamps ("HH:MM UTC") could differ across the two calls; compare the
    # property lines, which are the source-independent part.
    assert "180.000€" in body_fuente or "180,000€" in body_fuente
    assert body_fuente.split("🕐")[0] == body_label.split("🕐")[0]


async def test_default_call_is_backward_compatible_positional_fuente():
    # scheduler.py:177 calls send_price_drop_alerts(bajadas, fuente) positionally.
    n = _notifier()
    sent = {}

    async def fake_send(text, chat_id=None):
        sent["text"] = text
        return True

    n.send_message = fake_send
    result = await n.send_price_drop_alerts(_BAJADAS, SimpleNamespace(nombre="Fuente X"))
    assert result is True
    assert "Fuente X" in sent["text"].split("\n", 1)[0]

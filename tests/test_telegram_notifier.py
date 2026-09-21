"""Characterization + routing tests for TelegramNotifier.send_message.

The characterization tests (Global Chat Output Unchanged) pin the current
global-chat behavior. The routing tests cover the optional chat_id override
(Per-Alert Chat Routing).
"""
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import httpx
import pytest
import respx

import notifications.telegram as telegram_mod
from notifications.telegram import TelegramNotifier

SEND_MESSAGE_URL = "https://api.telegram.org/botTESTTOKEN/sendMessage"


@pytest.fixture(autouse=True)
def slept(monkeypatch):
    """Never really sleep between retries; record the requested delays."""
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(telegram_mod, "_sleep", fake_sleep)
    return delays


def _notifier(token="TESTTOKEN", chat_id="GLOBAL_CHAT"):
    n = TelegramNotifier()
    n.token = token
    n.chat_id = chat_id
    n.api_url = f"https://api.telegram.org/bot{token}"
    return n


# ── Characterization: current global-chat behavior ───────────────────────────


@respx.mock
async def test_send_message_posts_to_global_chat_with_markdown():
    route = respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(200))
    n = _notifier()

    result = await n.send_message("hello")

    assert result is True
    assert route.called
    payload = respx.calls.last.request
    import json

    body = json.loads(payload.content)
    assert body["chat_id"] == "GLOBAL_CHAT"
    assert body["text"] == "hello"
    assert body["parse_mode"] == "Markdown"


@respx.mock
async def test_send_message_returns_false_on_non_200():
    respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(400, text="bad"))
    n = _notifier()
    assert await n.send_message("hello") is False


@respx.mock
async def test_send_message_returns_false_on_transport_exception():
    respx.post(SEND_MESSAGE_URL).mock(side_effect=httpx.ConnectError("boom"))
    n = _notifier()
    assert await n.send_message("hello") is False


async def test_send_message_returns_false_without_token_and_makes_no_http():
    n = _notifier(token="", chat_id="GLOBAL_CHAT")
    with respx.mock:
        route = respx.post(url__regex=r".*").mock(return_value=httpx.Response(200))
        assert await n.send_message("hello") is False
        assert not route.called


async def test_send_message_returns_false_without_chat_id_and_makes_no_http():
    n = _notifier(token="TESTTOKEN", chat_id="")
    with respx.mock:
        route = respx.post(url__regex=r".*").mock(return_value=httpx.Response(200))
        assert await n.send_message("hello") is False
        assert not route.called


# ── Per-Alert Chat Routing: optional chat_id override ────────────────────────


@respx.mock
async def test_explicit_chat_id_overrides_payload_target():
    route = respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(200))
    n = _notifier()

    result = await n.send_message("hi", chat_id="-100555")

    assert result is True
    import json

    body = json.loads(respx.calls.last.request.content)
    assert body["chat_id"] == "-100555"


@respx.mock
async def test_none_chat_id_falls_back_to_global():
    respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(200))
    n = _notifier()

    await n.send_message("hi", chat_id=None)

    import json

    body = json.loads(respx.calls.last.request.content)
    assert body["chat_id"] == "GLOBAL_CHAT"


async def test_guard_honors_override_when_global_chat_missing():
    n = _notifier(token="TESTTOKEN", chat_id="")
    with respx.mock:
        route = respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(200))
        result = await n.send_message("hi", chat_id="-100555")
        assert result is True
        assert route.called
        import json

        body = json.loads(respx.calls.last.request.content)
        assert body["chat_id"] == "-100555"


# ── Delivery reliability: parse errors, retry/backoff, counters ──────────────

PARSE_ERROR = httpx.Response(
    400,
    json={"ok": False, "error_code": 400,
          "description": "Bad Request: can't parse entities: Can't find end of the entity"},
)
NASTY_TITLE = "Piso_con *raro* [texto] `code`"


def _bodies():
    return [json.loads(c.request.content) for c in respx.calls]


@respx.mock
async def test_markdown_parse_error_falls_back_to_plain_text_and_is_delivered():
    route = respx.post(SEND_MESSAGE_URL).mock(
        side_effect=[PARSE_ERROR, httpx.Response(200)]
    )
    n = _notifier()

    assert await n.send_message(NASTY_TITLE) is True

    first, second = _bodies()
    assert first["parse_mode"] == "Markdown"
    assert "parse_mode" not in second
    assert second["text"] == NASTY_TITLE
    assert route.call_count == 2


@respx.mock
async def test_property_alert_with_markdown_characters_in_title_is_delivered():
    respx.post(SEND_MESSAGE_URL).mock(side_effect=[PARSE_ERROR, httpx.Response(200)])
    n = _notifier()
    prop = SimpleNamespace(
        titulo=NASTY_TITLE, precio=1000, superficie_m2=50, habitaciones=2,
        zona_normalizada=None, barrio=None, direccion=None,
        url_original="https://example.com/a_b",
    )

    ok = await n.send_property_alerts(
        [prop], SimpleNamespace(nombre="F", chat_id_telegram=None),
        SimpleNamespace(nombre="Fuente"),
    )

    assert ok is True
    assert NASTY_TITLE in _bodies()[-1]["text"]


@respx.mock
async def test_429_honours_retry_after_then_succeeds(slept):
    respx.post(SEND_MESSAGE_URL).mock(side_effect=[
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 3}}),
        httpx.Response(200),
    ])
    n = _notifier()

    assert await n.send_message("hi") is True
    assert slept == [3]


@respx.mock
async def test_5xx_is_retried_with_backoff_then_succeeds(slept):
    respx.post(SEND_MESSAGE_URL).mock(side_effect=[
        httpx.Response(502), httpx.Response(503), httpx.Response(200),
    ])
    n = _notifier()

    assert await n.send_message("hi") is True
    assert len(slept) == 2 and slept[1] > slept[0] > 0


@respx.mock
async def test_timeout_is_retried(slept):
    respx.post(SEND_MESSAGE_URL).mock(side_effect=[
        httpx.ReadTimeout("slow"), httpx.Response(200),
    ])
    n = _notifier()

    assert await n.send_message("hi") is True
    assert len(slept) == 1


@respx.mock
async def test_persistent_5xx_gives_up_logs_error_and_counts_failure(caplog):
    route = respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(500))
    n = _notifier()

    with caplog.at_level(logging.ERROR):
        assert await n.send_message("hi") is False

    assert route.call_count == telegram_mod.MAX_ATTEMPTS
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    assert (n.sent_count, n.failed_count) == (0, 1)


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_client_errors_that_cannot_succeed_are_not_retried(status, slept):
    route = respx.post(SEND_MESSAGE_URL).mock(
        return_value=httpx.Response(status, json={"description": "chat not found"})
    )
    n = _notifier()

    assert await n.send_message("hi") is False
    assert route.call_count == 1
    assert slept == []
    assert n.failed_count == 1


@respx.mock
async def test_429_with_absurd_retry_after_is_not_waited_for(slept):
    route = respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(
        429, json={"parameters": {"retry_after": 86400}}
    ))
    n = _notifier()

    assert await n.send_message("hi") is False
    assert route.call_count == 1
    assert slept == []


@respx.mock
async def test_successful_sends_are_counted():
    respx.post(SEND_MESSAGE_URL).mock(return_value=httpx.Response(200))
    n = _notifier()

    await n.send_message("a")
    await n.send_message("b")

    assert (n.sent_count, n.failed_count) == (2, 0)


@respx.mock
async def test_token_is_never_logged_on_failure(caplog):
    respx.post(SEND_MESSAGE_URL).mock(side_effect=httpx.ConnectError("boom"))
    n = _notifier()

    with caplog.at_level(logging.DEBUG):
        await n.send_message("hi")

    assert "TESTTOKEN" not in caplog.text


# ── Truncated lists say how many were left out ───────────────────────────────


async def _capture_text(coro_factory):
    n = _notifier()
    sent = {}

    async def fake_send(text, chat_id=None):
        sent["text"] = text
        return True

    n.send_message = fake_send
    await coro_factory(n)
    return sent["text"]


async def test_property_alert_reports_how_many_matches_were_not_listed():
    props = [
        SimpleNamespace(
            titulo=f"P{i}", precio=1000, superficie_m2=50, habitaciones=2,
            zona_normalizada=None, barrio=None, direccion=None, url_original=f"http://x/{i}",
        )
        for i in range(7)
    ]
    text = await _capture_text(lambda n: n.send_property_alerts(
        props, SimpleNamespace(nombre="F", chat_id_telegram=None), SimpleNamespace(nombre="S")
    ))
    assert "y 2 más" in text


async def test_price_drop_alert_reports_how_many_drops_were_not_listed():
    drops = [
        {"titulo": f"P{i}", "url": f"http://x/{i}", "precio_anterior": 2000,
         "precio_nuevo": 1000, "bajada_pct": 50}
        for i in range(12)
    ]
    text = await _capture_text(lambda n: n.send_price_drop_alerts(drops, source_label="x"))
    assert "y 2 más" in text


async def test_sold_alert_reports_how_many_were_not_listed():
    vendidas = [
        {"titulo": f"P{i}", "url": f"http://x/{i}", "precio": 1000, "estado": "Vendida"}
        for i in range(12)
    ]
    text = await _capture_text(lambda n: n.send_sold_properties_alert(vendidas))
    assert "y 2 más" in text

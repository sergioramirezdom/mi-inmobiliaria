"""Characterization + routing tests for TelegramNotifier.send_message.

The characterization tests (Global Chat Output Unchanged) pin the current
global-chat behavior. The routing tests cover the optional chat_id override
(Per-Alert Chat Routing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import httpx
import pytest
import respx

from notifications.telegram import TelegramNotifier

SEND_MESSAGE_URL = "https://api.telegram.org/botTESTTOKEN/sendMessage"


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

"""Unit tests for app.notifications.alert_routing — pure chat-id resolution."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from notifications.alert_routing import resolve_chat_id


def test_non_empty_filtro_chat_id_wins():
    assert resolve_chat_id("-100999", "GLOBAL") == "-100999"


def test_none_filtro_chat_id_falls_back_to_global():
    assert resolve_chat_id(None, "GLOBAL") == "GLOBAL"


def test_empty_string_filtro_chat_id_falls_back_to_global():
    assert resolve_chat_id("", "GLOBAL") == "GLOBAL"


def test_whitespace_filtro_chat_id_falls_back_to_global():
    assert resolve_chat_id("   ", "GLOBAL") == "GLOBAL"


def test_filtro_chat_id_is_stripped_when_returned():
    assert resolve_chat_id("  -100999  ", "GLOBAL") == "-100999"


def test_inputs_are_not_mutated():
    filtro_chat_id = "  -100999  "
    global_chat_id = "GLOBAL"
    resolve_chat_id(filtro_chat_id, global_chat_id)
    assert filtro_chat_id == "  -100999  "
    assert global_chat_id == "GLOBAL"

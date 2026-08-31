"""Unit tests for app.notifications.alert_routing — pure chat-id resolution."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from notifications.alert_routing import resolve_chat_id, filter_favorite_drops


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


# ── filter_favorite_drops ────────────────────────────────────────────────────


def test_filter_favorite_drops_empty_list():
    assert filter_favorite_drops([]) == []


def test_filter_favorite_drops_all_favorite():
    bajadas = [
        {"titulo": "A", "favorita": True},
        {"titulo": "B", "favorita": True},
    ]
    assert filter_favorite_drops(bajadas) == bajadas


def test_filter_favorite_drops_mixed_keeps_only_favorites_in_order():
    a = {"titulo": "A", "favorita": True}
    b = {"titulo": "B", "favorita": False}
    c = {"titulo": "C", "favorita": True}
    assert filter_favorite_drops([a, b, c]) == [a, c]


def test_filter_favorite_drops_missing_key_is_not_favorite():
    a = {"titulo": "A"}
    b = {"titulo": "B", "favorita": True}
    assert filter_favorite_drops([a, b]) == [b]


def test_filter_favorite_drops_does_not_mutate_input():
    bajadas = [{"titulo": "A", "favorita": True}, {"titulo": "B", "favorita": False}]
    original = [dict(x) for x in bajadas]
    filter_favorite_drops(bajadas)
    assert bajadas == original

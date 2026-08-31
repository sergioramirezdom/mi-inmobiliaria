"""Tests for the edit-dialog sequential navigation (Propiedades 2.0 only).

`nav_step` is a pure, DB-free helper: `state = {"ids": [...], "idx": int}`.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from ui.property_dialogs import nav_step


# ── 3.1 / 3.2 / 3.3 — nav_step pure helper ────────────────────────────


def test_nav_step_advances_and_retreats_within_bounds():
    state = {"ids": [10, 20, 30], "idx": 1}

    forward = nav_step(state, +1)
    assert forward == {"ids": [10, 20, 30], "idx": 2}

    back = nav_step(state, -1)
    assert back == {"ids": [10, 20, 30], "idx": 0}


def test_nav_step_clamps_at_first_and_last_index():
    state = {"ids": [10, 20, 30], "idx": 0}
    assert nav_step(state, -1) == {"ids": [10, 20, 30], "idx": 0}  # no wraparound

    state_last = {"ids": [10, 20, 30], "idx": 2}
    assert nav_step(state_last, +1) == {"ids": [10, 20, 30], "idx": 2}  # no wraparound


def test_nav_step_closes_dialog_when_current_id_missing():
    # e.g. after marking the current property excluded mid-navigation —
    # its id is no longer in the page's live id list.
    state = {"ids": [10, 30], "idx": 5}  # idx 5 doesn't even exist in ids
    assert nav_step(state, +1) is None

    empty_state = {"ids": [], "idx": 0}
    assert nav_step(empty_state, +1) is None


# ── 4.1 / 4.2 — dialog mark/unmark action wiring ──────────────────────
#
# `@st.dialog`-decorated functions can't be unit-tested directly without
# Streamlit's AppTest harness (not used elsewhere in this codebase). The
# dialog's mark/unmark buttons call `_mark_excluida_action`, a thin,
# directly-importable wrapper — the same extraction pattern used for
# `nav_step` — so the wiring (which CRUD method gets called, with which
# args) is testable in isolation.


def test_mark_excluided_action_calls_marcar_excluida_true():
    from ui.property_dialogs import _mark_excluida_action

    session = MagicMock()
    with patch("ui.property_dialogs.PropiedadCRUD") as mock_crud:
        _mark_excluida_action(session, propiedad_id=42, excluir=True)
        mock_crud.marcar_excluida.assert_called_once_with(session, 42, True, now=None)


def test_unmark_excluided_action_calls_marcar_excluida_false():
    from ui.property_dialogs import _mark_excluida_action

    session = MagicMock()
    with patch("ui.property_dialogs.PropiedadCRUD") as mock_crud:
        _mark_excluida_action(session, propiedad_id=42, excluir=False)
        mock_crud.marcar_excluida.assert_called_once_with(session, 42, False, now=None)


# ── 4.4 — save auto-advances to next property in the nav list ─────────


def test_save_auto_advances_to_next_property_in_nav_list():
    nav_before = {"ids": [10, 20, 30], "idx": 0}
    nav_after = nav_step(nav_before, +1)
    assert nav_after == {"ids": [10, 20, 30], "idx": 1}
    assert nav_after["idx"] != nav_before["idx"]  # actually advanced, not a no-op


# ── 3.9 — v1 (`property_card.py` / `2_propiedades.py`) is unaffected ────


def test_v1_property_card_calls_edit_dialog_without_nav_kwarg():
    """v1's edit button call must NOT pass `nav=`, so it keeps the
    pre-existing (no navigation, no auto-advance) behaviour via the
    `nav=None` default on `edit_property_dialog`."""
    import inspect

    from ui import property_card

    source = inspect.getsource(property_card.render_card)
    assert "edit_property_dialog(prop, on_write=on_write)" in source
    assert "nav=" not in source


def test_edit_property_dialog_defaults_nav_to_none():
    import inspect

    from ui.property_dialogs import edit_property_dialog

    sig = inspect.signature(edit_property_dialog)
    assert sig.parameters["nav"].default is None

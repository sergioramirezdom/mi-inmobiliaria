"""Pure helpers for alert chat-id routing.

Stdlib only — no Streamlit, httpx, or DB imports — so the routing decision is
trivially unit-testable.
"""
from typing import List, Optional

# Recognized values for FiltroAlerta.tipo_alerta (consumed by the scheduler).
TIPO_NUEVAS = "nuevas"
TIPO_BAJADAS_FAVORITAS = "bajadas_favoritas"


def resolve_chat_id(filtro_chat_id: Optional[str], global_chat_id: str) -> str:
    """Return the per-alert chat id when set and non-blank, else the global chat.

    A non-empty ``filtro_chat_id`` (after stripping surrounding whitespace) wins.
    ``None``, an empty string, or whitespace-only falls back to ``global_chat_id``.
    Inputs are never mutated.
    """
    if filtro_chat_id is not None:
        stripped = filtro_chat_id.strip()
        if stripped:
            return stripped
    return global_chat_id


def filter_favorite_drops(bajadas: List[dict]) -> List[dict]:
    """Return only the price-drop entries whose ``favorita`` is truthy.

    Pure and DB-free. Order is preserved; a missing ``favorita`` key counts as
    not favourite. The input list and its dicts are never mutated.
    """
    return [b for b in bajadas if b.get("favorita")]

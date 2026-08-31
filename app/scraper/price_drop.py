"""Pure builder for a price-drop entry appended to ``stats["bajadas_precio"]``.

Stdlib only — no Streamlit, httpx, or DB imports — so both producers
(``paginated_scraper`` and ``sold_checker``) can share one constructor and the
shape stays trivially unit-testable.
"""


def build_price_drop_entry(propiedad, precio_anterior, precio_nuevo, bajada_pct) -> dict:
    """Build a single price-drop dict from an in-scope ``Propiedad`` ORM object.

    Keeps the legacy keys (``titulo``, ``url``, ``precio_anterior``,
    ``precio_nuevo``, ``bajada_pct``) and adds ``propiedad_id`` plus ``favorita``
    read from the property. ``favorita`` is bool-coerced; a missing attribute
    counts as not favourite.
    """
    return {
        "titulo": propiedad.titulo,
        "url": propiedad.url_original,
        "precio_anterior": precio_anterior,
        "precio_nuevo": precio_nuevo,
        "bajada_pct": bajada_pct,
        "propiedad_id": getattr(propiedad, "id", None),
        "favorita": bool(getattr(propiedad, "favorita", False)),
    }

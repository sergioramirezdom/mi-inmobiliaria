"""Componentes HTML reutilizables — Propiedades 2.0."""

import html as html_lib
from pathlib import Path

import streamlit as st


def inject_styles():
    """Inyecta el CSS global y el theme una sola vez por página."""
    from ui.theme import inject_theme

    inject_theme()

    css_path = Path(__file__).parent / "styles.css"
    if css_path.exists():
        css_text = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)


def skeleton_card() -> str:
    """Tarjeta de carga skeleton (shimmer animation)."""
    return (
        '<div class="v2-card" style="pointer-events:none;">'
        '<div class="v2-skeleton v2-skeleton-img"></div>'
        '<div style="padding:14px 16px;">'
        '<div class="v2-skeleton v2-skeleton-text long"></div>'
        '<div class="v2-skeleton v2-skeleton-text price"></div>'
        '<div class="v2-skeleton v2-skeleton-text medium" style="margin-top:12px;"></div>'
        '<div class="v2-skeleton v2-skeleton-text short" style="margin-top:8px;"></div>'
        '<div class="v2-skeleton v2-skeleton-text medium" style="margin-top:12px;"></div>'
        "</div>"
        "</div>"
    )


def skeleton_grid(n: int = 6):
    """Renderiza una grid de n tarjetas skeleton."""
    cols = st.columns(3)
    for i in range(n):
        with cols[i % 3]:
            st.markdown(skeleton_card(), unsafe_allow_html=True)


def empty_state(
    icon: str = "🔍",
    title: str = "Sin resultados",
    message: str = "No se encontraron propiedades con los filtros actuales.",
) -> str:
    """Estado vacío atractivo cuando no hay datos."""
    return (
        '<div class="v2-empty">'
        f'<div class="v2-empty-icon">{icon}</div>'
        f"<h3>{html_lib.escape(title)}</h3>"
        f"<p>{html_lib.escape(message)}</p>"
        "</div>"
    )


def header_v2(title: str, subtitle: str = "", icon: str = "🏘️") -> str:
    """Header con gradiente Esmerald Ink."""
    subtitle_html = f"<p>{html_lib.escape(subtitle)}</p>" if subtitle else ""
    return (
        '<div class="v2-header">'
        f"<h1>{icon} {html_lib.escape(title)}</h1>"
        f"{subtitle_html}"
        "</div>"
    )


def results_bar(total: int, filters_summary: str = "") -> str:
    """Barra de resultados con conteo y filtros activos."""
    filter_html = (
        f' <span style="font-weight:400;color:var(--slate);font-size:0.82rem;">'
        f'· 🔍 {html_lib.escape(filters_summary)}</span>'
        if filters_summary
        else ""
    )
    return (
        '<div class="v2-results-bar">'
        f'<div class="v2-results-count"><span>{total}</span> resultados{filter_html}</div>'
        "</div>"
    )


def filter_summary_bar(active_filters: list[dict]) -> str:
    """Barra de filtros activos con pills que se pueden quitar.

    Cada filtro es un dict con 'label' y 'key'.
    """
    if not active_filters:
        return ""

    pills = ""
    for f in active_filters:
        pills += (
            '<span class="v2-active-filter">'
            f"{html_lib.escape(f['label'])}"
            f'<span class="v2-active-filter-remove" '
            f'data-filter-key="{html_lib.escape(f["key"])}">✕</span>'
            "</span>"
        )

    return (
        '<div class="v2-active-filters">'
        '<span style="font-size:0.78rem;color:var(--slate);font-weight:500;">Filtros:</span>'
        f"{pills}"
        "</div>"
    )


def segmented_control_html(options: list[dict], active_key: str) -> str:
    """Segmented control custom HTML.

    Each option: {"key": "nuevas", "label": "🆕 Nuevas", "count": 5}
    """
    segments = ""
    for opt in options:
        active_class = "active" if opt["key"] == active_key else ""
        count_html = (
            f'<span class="seg-count">({opt["count"]})</span>'
            if opt.get("count") is not None
            else ""
        )
        segments += (
            f'<button class="v2-segment {active_class}" '
            f'data-seg-key="{html_lib.escape(opt["key"])}">'
            f'{html_lib.escape(opt["label"])}{count_html}'
            "</button>"
        )

    return f'<div class="v2-segments">{segments}</div>'


def render_pagination(page: int, total_pages: int) -> int | None:
    """Paginación con botones Streamlit reales — sin HTML decorativo muerto.

    Ventana de páginas ±2 alrededor de la actual, más primera/última con
    "…" cuando hace falta. Devuelve la página elegida, o None si no se
    tocó nada en este render.
    """
    if total_pages <= 1:
        return None

    window = sorted(
        {1, total_pages, page}
        | {p for p in range(page - 2, page + 3) if 1 <= p <= total_pages}
    )
    labels: list[str | int] = []
    prev_p = 0
    for p in window:
        if p - prev_p > 1:
            labels.append("…")
        labels.append(p)
        prev_p = p

    slots = ["←"] + labels + ["→"]
    result = None
    with st.container(key="v2_pagination_container"):
        cols = st.columns(len(slots))
        for col, slot in zip(cols, slots):
            if slot == "…":
                col.markdown(
                    '<div style="text-align:center;color:var(--slate);padding-top:6px;">…</div>',
                    unsafe_allow_html=True,
                )
            elif slot == "←":
                if col.button("←", key="v2_pg_prev", disabled=page <= 1, use_container_width=True):
                    result = page - 1
            elif slot == "→":
                if col.button("→", key="v2_pg_next", disabled=page >= total_pages, use_container_width=True):
                    result = page + 1
            elif col.button(
                str(slot),
                key=f"v2_pg_{slot}",
                type="primary" if slot == page else "secondary",
                use_container_width=True,
            ):
                result = slot
    return result


def loading_overlay(text: str = "Cargando...") -> str:
    """Overlay de carga semitransparente."""
    return (
        '<div style="position:fixed;top:0;left:0;right:0;bottom:0;'
        "background:rgba(253,248,240,0.85);"
        "display:flex;align-items:center;justify-content:center;z-index:9999;"
        'backdrop-filter:blur(2px);">'
        '<div style="text-align:center;">'
        '<div style="font-size:2rem;margin-bottom:8px;">⏳</div>'
        f'<div style="color:var(--primary);font-weight:600;">{html_lib.escape(text)}</div>'
        "</div>"
        "</div>"
    )

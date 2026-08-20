"""Filtros modernos — Propiedades 2.0."""

import streamlit as st

from ui.property_queries import CARACTERISTICAS

DEFAULT_FILTERS = {
    "precio_min": 0,
    "precio_max": 0,
    "m2_min": 0,
    "hab_min": 0,
    "banos_min": 0,
    "tipos": [],
    "distritos": [],
    "caracteristicas": [],
    "search": "",
    "tipo_operacion": "",
    "solo_bajadas": False,
}

WIDGET_KEYS = [
    "v2_f_precio_min",
    "v2_f_precio_max",
    "v2_f_m2_min",
    "v2_f_hab_min",
    "v2_f_banos_min",
    "v2_f_tipos",
    "v2_f_distritos",
    "v2_f_caracteristicas",
    "v2_f_search",
    "v2_f_tipo_operacion",
    "v2_f_solo_bajadas",
]


def _fmt_price(v: int) -> str:
    if not v:
        return ""
    return f"{v:,.0f} €".replace(",", ".")


def _active_filter_items(filters: dict) -> list[tuple[str, dict]]:
    """Lista (etiqueta, patch) de cada filtro activo.

    `patch` es lo que hay que aplicar sobre una copia de `filters` para
    quitar ESE filtro puntual (sin tocar los demás).
    """
    items: list[tuple[str, dict]] = []
    if filters.get("precio_min"):
        items.append((f"≥ {_fmt_price(filters['precio_min'])}", {"precio_min": 0}))
    if filters.get("precio_max"):
        items.append((f"≤ {_fmt_price(filters['precio_max'])}", {"precio_max": 0}))
    if filters.get("m2_min"):
        items.append((f"≥ {filters['m2_min']} m²", {"m2_min": 0}))
    if filters.get("hab_min"):
        items.append((f"≥ {filters['hab_min']} hab", {"hab_min": 0}))
    if filters.get("banos_min"):
        items.append((f"≥ {filters['banos_min']} baños", {"banos_min": 0}))
    if filters.get("tipo_operacion"):
        items.append((filters["tipo_operacion"].capitalize(), {"tipo_operacion": ""}))
    for t in filters.get("tipos", []):
        items.append((t, {"tipos": [x for x in filters["tipos"] if x != t]}))
    for d in filters.get("distritos", []):
        items.append((d, {"distritos": [x for x in filters["distritos"] if x != d]}))
    for c in filters.get("caracteristicas", []):
        items.append(
            (c, {"caracteristicas": [x for x in filters["caracteristicas"] if x != c]})
        )
    if filters.get("search"):
        items.append((f"«{filters['search']}»", {"search": ""}))
    if filters.get("solo_bajadas"):
        items.append(("📉 Bajadas", {"solo_bajadas": False}))
    return items


def render_filter_summary(filters: dict) -> str:
    """Devuelve HTML con pills de filtros activos (solo lectura).

    Usado como fallback/preview; para poder quitarlos con un click ver
    `render_active_filters`.
    """
    items = _active_filter_items(filters)
    if not items:
        return ""
    pills = "".join(f'<span class="v2-active-filter">{label}</span>' for label, _ in items)
    return (
        '<div class="v2-active-filters">'
        '<span style="font-size:0.78rem;color:var(--slate);font-weight:500;">Filtros:</span>'
        f'{pills}'
        '</div>'
    )


def render_active_filters(filters: dict) -> dict | None:
    """Filtros activos como pills QUITABLES (botón real, no HTML muerto).

    Devuelve el dict de filtros ya actualizado si se quitó uno; None si no
    hubo cambios.
    """
    items = _active_filter_items(filters)
    if not items:
        return None

    result = None
    with st.container(key="v2_active_filters_container"):
        st.caption("Filtros activos — tocá ✕ para quitar uno")
        cols = st.columns(len(items))
        for i, (col, (label, patch)) in enumerate(zip(cols, items)):
            if col.button(f"✕ {label}", key=f"v2_rm_{i}", use_container_width=True):
                result = {**filters, **patch}
    return result


def render_full_filters(tipos_opts: list, distritos_opts: list) -> dict | None:
    """Panel completo de filtros en expander. Devuelve dict al aplicar o None."""
    with st.expander("🔍 Filtros avanzados", expanded=False):
        with st.form("v2_filtros", border=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.number_input("Precio mín (€)", min_value=0, step=10_000, key="v2_f_precio_min")
            c2.number_input("Precio máx (€)", min_value=0, step=10_000, key="v2_f_precio_max")
            c3.number_input("m² mín", min_value=0, step=10, key="v2_f_m2_min")
            c4.number_input("Hab. mín", min_value=0, step=1, key="v2_f_hab_min")
            c5.number_input("Baños mín", min_value=0, step=1, key="v2_f_banos_min")

            c6, c7 = st.columns(2)
            c6.multiselect("Tipo", tipos_opts, key="v2_f_tipos")
            c7.multiselect("Distrito", distritos_opts, key="v2_f_distritos")

            st.multiselect(
                "Características (debe tener todas)",
                list(CARACTERISTICAS.keys()),
                key="v2_f_caracteristicas",
            )

            st.checkbox("📉 Solo bajadas de precio", key="v2_f_solo_bajadas",
                        help="Mostrar solo propiedades cuyo precio ha bajado respecto al anterior")

            c8, c9 = st.columns(2)
            c8.selectbox(
                "Operación",
                ["", "Venta", "Alquiler"],
                key="v2_f_tipo_operacion",
                format_func=lambda x: "Todas" if x == "" else x,
            )
            c9.text_input("Buscar en título/descripción", key="v2_f_search")

            col_apply, col_clear = st.columns([1, 1])
            aplicar = col_apply.form_submit_button("✅ Aplicar", type="primary", use_container_width=True)
            limpiar = col_clear.form_submit_button("🧹 Limpiar", use_container_width=True)

    if aplicar:
        return build_filters_from_state()
    if limpiar:
        _clear_filters()
        st.rerun()
    return None


def build_filters_from_state() -> dict:
    """Construye el dict de filtros desde session_state."""
    return {
        "precio_min": st.session_state.get("v2_f_precio_min", 0),
        "precio_max": st.session_state.get("v2_f_precio_max", 0),
        "m2_min": st.session_state.get("v2_f_m2_min", 0),
        "hab_min": st.session_state.get("v2_f_hab_min", 0),
        "banos_min": st.session_state.get("v2_f_banos_min", 0),
        "tipos": st.session_state.get("v2_f_tipos", []),
        "distritos": st.session_state.get("v2_f_distritos", []),
        "caracteristicas": st.session_state.get("v2_f_caracteristicas", []),
        "search": st.session_state.get("v2_f_search", "").strip(),
        "tipo_operacion": (
            st.session_state.get("v2_f_tipo_operacion", "").lower()
            if st.session_state.get("v2_f_tipo_operacion")
            else ""
        ),
        "solo_bajadas": st.session_state.get("v2_f_solo_bajadas", False),
    }


def sync_widget_state(filters: dict) -> None:
    """Sincroniza los widgets del form de "Filtros avanzados" con `filters`.

    Hace falta llamarla cuando los filtros cambian por fuera del form (chips
    rápidos, quitar una pill) — si no, al abrir el panel y tocar "Aplicar"
    el form pisaría el cambio con su estado viejo. Debe llamarse ANTES de
    que `render_full_filters` instancie esos widgets en el mismo render.
    """
    st.session_state["v2_f_precio_min"] = filters.get("precio_min", 0)
    st.session_state["v2_f_precio_max"] = filters.get("precio_max", 0)
    st.session_state["v2_f_m2_min"] = filters.get("m2_min", 0)
    st.session_state["v2_f_hab_min"] = filters.get("hab_min", 0)
    st.session_state["v2_f_banos_min"] = filters.get("banos_min", 0)
    st.session_state["v2_f_tipos"] = filters.get("tipos", [])
    st.session_state["v2_f_distritos"] = filters.get("distritos", [])
    st.session_state["v2_f_caracteristicas"] = filters.get("caracteristicas", [])
    st.session_state["v2_f_search"] = filters.get("search", "")
    st.session_state["v2_f_tipo_operacion"] = (filters.get("tipo_operacion") or "").capitalize()
    st.session_state["v2_f_solo_bajadas"] = filters.get("solo_bajadas", False)


def _clear_filters():
    """Limpia todos los filtros y sus widgets."""
    for k in WIDGET_KEYS:
        st.session_state.pop(k, None)
    st.session_state.filters = dict(DEFAULT_FILTERS)
    st.session_state.page = 1

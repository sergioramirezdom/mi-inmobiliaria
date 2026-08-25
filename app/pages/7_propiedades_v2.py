"""Propiedades 2.0: vista moderna y dinámica."""

import json
import math
import sys
from pathlib import Path

import streamlit as st
from sqlalchemy import distinct, update as sa_update
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine
from db.models import Propiedad
from ui.property_card_v2 import render_card_v2
from ui.property_dialogs import add_url_dialog, get_or_create_fuente_manual, render_edit_dialog_host
from ui.property_queries import (
    CARACTERISTICAS,
    SORT_OPTIONS,
    bajada_total_map,
    build_stmt,
    counts_from_rows,
    filter_conditions,
    prop_to_dict,
    tab_conditions,
)

st.set_page_config(page_title="Propiedades 2.0", page_icon="🏘️", layout="wide")

# ── Inyectar estilos v2 ───────────────────────────────────────────────
from ui.components_v2 import inject_styles, empty_state, results_bar, render_pagination
from ui.filter_bar_v2 import (
    DEFAULT_FILTERS,
    render_active_filters,
    render_full_filters,
    sync_widget_state,
)
from ui.theme import inject_theme, COLORS

inject_theme()
inject_styles()

PAGE_SIZE = 12
TABS = {
    "nuevas": "🆕 Nuevas",
    "todas": "📋 Todas",
    "favoritas": "❤️ Favoritas",
    "descartadas": "❌ Descartadas",
    "visitadas": "🏠 Visitadas",
    "vendidas": "🚫 Vendidas",
}


# ── Fetches cacheados ─────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def fetch_props(tab: str, filters_json: str, sort_key: str) -> list[dict]:
    filters = json.loads(filters_json)
    with Session(engine) as session:
        fuente_manual_id = get_or_create_fuente_manual(session)
        props = session.exec(build_stmt(tab, filters, sort_key)).all()
        bmap = bajada_total_map(session, [p.id for p in props])
        return [prop_to_dict(p, fuente_manual_id, bajada_map=bmap) for p in props]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_counts() -> dict:
    with Session(engine) as session:
        rows = session.exec(
            select(
                Propiedad.activa,
                Propiedad.vista,
                Propiedad.visitada,
                Propiedad.descartada,
                Propiedad.favorita,
            )
        ).all()
    return counts_from_rows(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_filter_options() -> tuple[list, list]:
    with Session(engine) as session:
        tipos = session.exec(
            select(distinct(Propiedad.tipo_propiedad)).where(
                Propiedad.tipo_propiedad != None
            ).limit(50)
        ).all()
        distritos = session.exec(
            select(distinct(Propiedad.distrito)).where(
                Propiedad.distrito != None
            ).limit(50)
        ).all()
    return sorted(t for t in tipos if t), sorted(d for d in distritos if d)


def clear_prop_caches():
    fetch_props.clear()
    fetch_counts.clear()


def reset_page():
    st.session_state.page = 1


def filtros_activos_resumen(f: dict) -> str:
    parts = []
    if f.get("precio_min"):
        parts.append(f"≥{f['precio_min']:,.0f} €".replace(",", "."))
    if f.get("precio_max"):
        parts.append(f"≤{f['precio_max']:,.0f} €".replace(",", "."))
    if f.get("m2_min"):
        parts.append(f"≥{f['m2_min']} m²")
    if f.get("hab_min"):
        parts.append(f"≥{f['hab_min']} hab")
    if f.get("banos_min"):
        parts.append(f"≥{f['banos_min']} baños")
    if f.get("tipo_operacion"):
        parts.append(f["tipo_operacion"].capitalize())
    parts += f.get("tipos", []) + f.get("distritos", []) + f.get("caracteristicas", [])
    if f.get("search"):
        parts.append(f"«{f['search']}»")
    return " · ".join(parts)


# ── Estado ────────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state.page = 1
if "filters" not in st.session_state:
    st.session_state.filters = dict(DEFAULT_FILTERS)
if "bulk_discard_confirm" not in st.session_state:
    st.session_state.bulk_discard_confirm = False

try:
    # ── Cabecera con gradiente ────────────────────────────────────────
    st.markdown(
        """
        <div class="v2-header">
            <h1>🏘️ Propiedades 2.0</h1>
            <p>Explora y gestiona tus propiedades de forma inteligente</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Pestañas de estado + acción principal ──────────────────────────
    # "➕ Añadir URL" va junto a las tabs (su barra de herramientas natural)
    # en vez de flotando suelto al lado del título.
    counts = fetch_counts()

    tab_col, add_col = st.columns([5, 1], vertical_alignment="center")
    with tab_col:
        tab = st.segmented_control(
            "Estado",
            options=list(TABS.keys()),
            format_func=lambda k: f"{TABS[k]} ({counts[k]})",
            default="nuevas",
            key="tab",
            label_visibility="collapsed",
            on_change=reset_page,
            required=True,
        ) or "nuevas"
    with add_col:
        with st.container(key="v2_add_url_container"):
            if st.button("➕ Añadir URL", use_container_width=True, type="primary"):
                add_url_dialog(on_write=clear_prop_caches)

    # ── Filtros ───────────────────────────────────────────────────────
    tipos_opts, distritos_opts = fetch_filter_options()

    # Filtros activos como pills QUITABLES (antes era HTML sin click).
    pill_filters = render_active_filters(st.session_state.filters)
    if pill_filters is not None:
        sync_widget_state(pill_filters)
        st.session_state.filters = pill_filters
        st.session_state.page = 1

    # Panel completo de filtros
    new_filters = render_full_filters(tipos_opts, distritos_opts)
    if new_filters is not None:
        st.session_state.filters = new_filters
        st.session_state.page = 1

    filters = st.session_state.filters

    # ── Barra de resultados ───────────────────────────────────────────
    props = fetch_props(
        tab,
        json.dumps(filters, sort_keys=True),
        st.session_state.get("sort", "Más reciente"),
    )
    total = len(props)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(st.session_state.page, total_pages)
    st.session_state.page = page

    col_sort, col_info = st.columns([1, 3], vertical_alignment="bottom")
    with col_sort:
        st.selectbox(
            "Ordenar por",
            list(SORT_OPTIONS.keys()),
            key="sort",
            on_change=reset_page,
        )
    with col_info:
        resumen = filtros_activos_resumen(filters)
        st.markdown(results_bar(total, resumen), unsafe_allow_html=True)

    # ── Grid de tarjetas ──────────────────────────────────────────────
    if not props:
        st.markdown(
            empty_state(
                "🏠",
                "No hay propiedades",
                "No se encontraron propiedades en esta pestaña con los filtros actuales. Prueba a cambiar de pestaña o ajustar los filtros.",
            ),
            unsafe_allow_html=True,
        )
    else:
        page_items = props[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

        # Las alturas quedan iguales por CSS (altura fija de card-body +
        # chips/badges limitados a una fila) — no hace falta JS.
        page_ids = [p["id"] for p in page_items]
        cols = st.columns(4)
        for i, p in enumerate(page_items):
            with cols[i % 4]:
                render_card_v2(p, on_write=clear_prop_caches, index=i, page_ids=page_ids)

        # ── Diálogo de edición con navegación (fuera de los fragments) ──
        render_edit_dialog_host(page_ids, on_write=clear_prop_caches)

        # ── Paginación ────────────────────────────────────────────────
        st.caption(f"Página {page} de {total_pages} · {total} propiedades")
        new_page = render_pagination(page, total_pages)
        if new_page is not None:
            st.session_state.page = new_page
            st.rerun()

        if tab == "nuevas" and st.button(
            "✓ Visto todo (esta página)", use_container_width=True
        ):
            with Session(engine) as session:
                session.execute(
                    sa_update(Propiedad)
                    .where(Propiedad.id.in_([p["id"] for p in page_items]))
                    .values(vista=True)
                )
                session.commit()
            clear_prop_caches()
            st.rerun()

    # ── Herramientas ──────────────────────────────────────────────────
    with st.expander("⚙️ Herramientas"):
        st.subheader("🗑️ Descarte masivo")
        st.caption(
            "Descarta todas las propiedades activas que coinciden con los filtros aplicados."
        )
        with Session(engine) as session:
            bulk_stmt = select(Propiedad.id)
            for cond in tab_conditions(tab) + filter_conditions(filters):
                bulk_stmt = bulk_stmt.where(cond)
            bulk_ids = list(session.exec(bulk_stmt).all())

        if not bulk_ids:
            st.caption("Ninguna propiedad activa sin descartar con el filtro actual.")
        elif not st.session_state.bulk_discard_confirm:
            if st.button(f"🗑️ Descartar todas ({len(bulk_ids)})"):
                st.session_state.bulk_discard_confirm = True
                st.rerun()
        else:
            st.warning(f"⚠️ ¿Marcar {len(bulk_ids)} propiedades como descartadas?")
            col_yes, col_no = st.columns(2)
            if col_yes.button("✅ Sí, descartar", type="primary", use_container_width=True):
                with Session(engine) as session:
                    session.execute(
                        sa_update(Propiedad)
                        .where(Propiedad.id.in_(bulk_ids))
                        .values(descartada=True, vista=True)
                    )
                    session.commit()
                st.session_state.bulk_discard_confirm = False
                clear_prop_caches()
                st.success(f"✅ {len(bulk_ids)} descartadas")
                st.rerun()
            if col_no.button("❌ Cancelar", use_container_width=True):
                st.session_state.bulk_discard_confirm = False
                st.rerun()

        st.divider()
        st.subheader("🔍 Verificar vendidas")
        with Session(engine) as session:
            active_count = len(
                session.exec(
                    select(Propiedad.id).where(Propiedad.activa == True)
                ).all()
            )
        st.caption(
            f"{active_count} propiedades activas a verificar."
        )
        if st.button("🔍 Verificar ahora", key="v2_verify_sold_btn"):
            import asyncio
            from scraper.sold_checker import check_sold_properties as _check_sold

            with st.spinner(
                f"Verificando {active_count} propiedades... (puede tardar)"
            ):
                with Session(engine) as verify_session:
                    sold_stats = asyncio.run(_check_sold(verify_session))
            st.success(
                f"✅ Completado — {sold_stats.get('vendidas', 0)} vendidas, "
                f"{sold_stats.get('errores', 0)} errores"
            )
            clear_prop_caches()
            st.rerun()

except Exception as e:
    st.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

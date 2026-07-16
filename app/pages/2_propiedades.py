"""Propiedades 2.0: triaje por pestañas, tarjetas visuales, filtros en formulario."""

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
from ui.property_card import render_card
from ui.property_dialogs import add_url_dialog, get_or_create_fuente_manual
from ui.property_queries import (
    CARACTERISTICAS,
    SORT_OPTIONS,
    build_stmt,
    counts_from_rows,
    filter_conditions,
    prop_to_dict,
    tab_conditions,
)

st.set_page_config(page_title="Propiedades", page_icon="🏘️", layout="wide")

PAGE_SIZE = 12
TABS = {
    "nuevas": "🆕 Nuevas",
    "todas": "📋 Todas",
    "favoritas": "❤️ Favoritas",
    "descartadas": "❌ Descartadas",
    "vendidas": "🚫 Vendidas",
}
DEFAULT_FILTERS = {
    "precio_min": 0, "precio_max": 0, "m2_min": 0, "hab_min": 0, "banos_min": 0,
    "tipos": [], "distritos": [], "caracteristicas": [], "search": "",
}
FILTER_WIDGET_KEYS = [
    "f_precio_min", "f_precio_max", "f_m2_min", "f_hab_min", "f_banos_min",
    "f_tipos", "f_distritos", "f_caracteristicas", "f_search",
]


# ── Fetches cacheados ─────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def fetch_props(tab: str, filters_json: str, sort_key: str) -> list[dict]:
    filters = json.loads(filters_json)
    with Session(engine) as session:
        fuente_manual_id = get_or_create_fuente_manual(session)
        props = session.exec(build_stmt(tab, filters, sort_key)).all()
        return [prop_to_dict(p, fuente_manual_id) for p in props]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_counts() -> dict:
    with Session(engine) as session:
        rows = session.exec(
            select(Propiedad.activa, Propiedad.vista, Propiedad.descartada, Propiedad.favorita)
        ).all()
    return counts_from_rows(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_filter_options() -> tuple[list, list]:
    with Session(engine) as session:
        tipos = session.exec(
            select(distinct(Propiedad.tipo_propiedad)).where(Propiedad.tipo_propiedad != None).limit(50)
        ).all()
        distritos = session.exec(
            select(distinct(Propiedad.distrito)).where(Propiedad.distrito != None).limit(50)
        ).all()
    return sorted(t for t in tipos if t), sorted(d for d in distritos if d)


def clear_prop_caches():
    fetch_props.clear()
    fetch_counts.clear()


def reset_page():
    st.session_state.page = 1


def filtros_activos_resumen(f: dict) -> str:
    parts = []
    if f["precio_min"]:
        parts.append(f"≥{f['precio_min']:,.0f} €".replace(",", "."))
    if f["precio_max"]:
        parts.append(f"≤{f['precio_max']:,.0f} €".replace(",", "."))
    if f["m2_min"]:
        parts.append(f"≥{f['m2_min']} m²")
    if f["hab_min"]:
        parts.append(f"≥{f['hab_min']} hab")
    if f["banos_min"]:
        parts.append(f"≥{f['banos_min']} baños")
    parts += f["tipos"] + f["distritos"] + f["caracteristicas"]
    if f["search"]:
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
    # ── Cabecera ──────────────────────────────────────────────────────
    col_title, col_add = st.columns([5, 1], vertical_alignment="bottom")
    with col_title:
        st.title("🏘️ Propiedades")
    with col_add:
        if st.button("➕ Añadir URL", use_container_width=True):
            add_url_dialog(on_write=clear_prop_caches)

    # ── Pestañas de estado ────────────────────────────────────────────
    counts = fetch_counts()
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

    # ── Filtros ───────────────────────────────────────────────────────
    tipos_opts, distritos_opts = fetch_filter_options()
    with st.expander("🔍 Filtros", expanded=False):
        with st.form("filtros", border=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.number_input("Precio mín (€)", min_value=0, step=10_000, key="f_precio_min")
            c2.number_input("Precio máx (€)", min_value=0, step=10_000, key="f_precio_max")
            c3.number_input("m² mín", min_value=0, step=10, key="f_m2_min")
            c4.number_input("Hab. mín", min_value=0, step=1, key="f_hab_min")
            c5.number_input("Baños mín", min_value=0, step=1, key="f_banos_min")
            c6, c7 = st.columns(2)
            c6.multiselect("Tipo", tipos_opts, key="f_tipos")
            c7.multiselect("Distrito", distritos_opts, key="f_distritos")
            st.multiselect("Características (debe tener todas)", list(CARACTERISTICAS.keys()), key="f_caracteristicas")
            st.text_input("Buscar en título/descripción", key="f_search")

            col_apply, col_clear = st.columns([1, 1])
            aplicar = col_apply.form_submit_button("Aplicar", type="primary", use_container_width=True)
            limpiar = col_clear.form_submit_button("Limpiar", use_container_width=True)

    if aplicar:
        st.session_state.filters = {
            "precio_min": st.session_state.f_precio_min,
            "precio_max": st.session_state.f_precio_max,
            "m2_min": st.session_state.f_m2_min,
            "hab_min": st.session_state.f_hab_min,
            "banos_min": st.session_state.f_banos_min,
            "tipos": st.session_state.f_tipos,
            "distritos": st.session_state.f_distritos,
            "caracteristicas": st.session_state.f_caracteristicas,
            "search": st.session_state.f_search.strip(),
        }
        st.session_state.page = 1
    if limpiar:
        st.session_state.filters = dict(DEFAULT_FILTERS)
        st.session_state.page = 1
        for k in FILTER_WIDGET_KEYS:
            st.session_state.pop(k, None)
        st.rerun()

    filters = st.session_state.filters

    # ── Barra de resultados ───────────────────────────────────────────
    props = fetch_props(tab, json.dumps(filters, sort_keys=True), st.session_state.get("sort", "Más reciente"))
    total = len(props)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(st.session_state.page, total_pages)
    st.session_state.page = page

    col_sort, col_info = st.columns([1, 3], vertical_alignment="bottom")
    with col_sort:
        st.selectbox("Ordenar por", list(SORT_OPTIONS.keys()), key="sort", on_change=reset_page)
    with col_info:
        resumen = filtros_activos_resumen(filters)
        st.markdown(f"**{total}** resultados" + (f" &nbsp;·&nbsp; 🔍 {resumen}" if resumen else ""))

    st.divider()

    # ── Grid de tarjetas ──────────────────────────────────────────────
    if not props:
        st.info("No hay propiedades en esta pestaña con los filtros actuales.")
    else:
        page_items = props[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        cols = st.columns(3)
        for i, p in enumerate(page_items):
            with cols[i % 3]:
                render_card(p, on_write=clear_prop_caches)

        # ── Paginación + visto todo ───────────────────────────────────
        col_prev, col_mid, col_next = st.columns([1, 2, 1])
        if col_prev.button("← Anterior", disabled=page <= 1, use_container_width=True):
            st.session_state.page = page - 1
            st.rerun()
        with col_mid:
            st.caption(f"Página {page} de {total_pages} · {total} propiedades")
            if tab == "nuevas" and st.button("✓ Visto todo (esta página)", use_container_width=True):
                with Session(engine) as session:
                    session.execute(
                        sa_update(Propiedad)
                        .where(Propiedad.id.in_([p["id"] for p in page_items]))
                        .values(vista=True)
                    )
                    session.commit()
                clear_prop_caches()
                st.rerun()
        if col_next.button("Siguiente →", disabled=page >= total_pages, use_container_width=True):
            st.session_state.page = page + 1
            st.rerun()

    # ── Herramientas ──────────────────────────────────────────────────
    with st.expander("⚙️ Herramientas"):
        st.subheader("🗑️ Descarte masivo")
        st.caption("Descarta todas las propiedades activas que coinciden con los filtros aplicados (todas las páginas).")
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
                        sa_update(Propiedad).where(Propiedad.id.in_(bulk_ids)).values(descartada=True, vista=True)
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
            active_count = len(session.exec(select(Propiedad.id).where(Propiedad.activa == True)).all())
        st.caption(f"{active_count} propiedades activas a verificar. Descarga cada ficha y marca como vendidas las que estén reservadas o vendidas.")
        if st.button("🔍 Verificar ahora", key="verify_sold_btn"):
            import asyncio
            from scraper.sold_checker import check_sold_properties as _check_sold
            with st.spinner(f"Verificando {active_count} propiedades... (puede tardar varios minutos)"):
                with Session(engine) as verify_session:
                    sold_stats = asyncio.run(_check_sold(verify_session))
            st.success(f"✅ Completado — {sold_stats.get('vendidas', 0)} vendidas, {sold_stats.get('errores', 0)} errores")
            clear_prop_caches()
            st.rerun()

except Exception as e:
    st.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

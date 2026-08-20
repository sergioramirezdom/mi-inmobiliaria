"""Tarjeta de propiedad rediseñada — "Propiedades 2.0".

Estructura por cada columna:
  1. HTML puro (imagen + body) — renderizado via st.markdown
  2. Botones de acción Streamlit — debajo del HTML, dentro del mismo container

Altura uniforme: el card-body tiene height fijo + overflow hidden.
Las acciones van en un container Streamlit con border que simula el pie de la tarjeta.
"""

import html as html_lib

import streamlit as st
from sqlmodel import Session

from db.database import engine, PropiedadCRUD
from db.models import Propiedad


# ── Formatting ─────────────────────────────────────────────────────────


def fmt_eur(v) -> str:
    """245000 -> '245.000 €'"""
    try:
        return f"{float(v):,.0f}".replace(",", ".") + " €"
    except (TypeError, ValueError):
        return "— €"


# ── Image ──────────────────────────────────────────────────────────────

_PLACEHOLDER_EMOJI = "🏠"


def _foto_html(p: dict) -> str:
    fotos = p.get("fotos") or []
    if fotos:
        src = html_lib.escape(str(fotos[0]), quote=True)
        inner = (
            f'<img class="v2-card-img" src="{src}" '
            'onerror="this.style.display=\'none\';'
            "this.nextElementSibling.style.display='flex';\">"
            '<div class="v2-card-img-placeholder" '
            "style=\"display:none;\">{e}</div>".format(e=_PLACEHOLDER_EMOJI)
        )
    else:
        inner = f'<div class="v2-card-img-placeholder">{_PLACEHOLDER_EMOJI}</div>'
    return f'<div class="v2-card-img-wrapper">{inner}</div>'


# ── Overlay ────────────────────────────────────────────────────────────


def _overlay_html(p: dict) -> str:
    precio = fmt_eur(p.get("precio")) if p.get("precio") is not None else "Precio N/D"
    bajada = ""
    bv = p.get("bajada")
    if bv:
        bajada = (
            f'<span class="v2-card-overlay-price-drop">↓ -{fmt_eur(bv)}</span>'
        )
    return (
        f'<div class="v2-card-overlay">'
        f'<span class="v2-card-overlay-price">{precio}</span>{bajada}</div>'
    )


# ── Badges ─────────────────────────────────────────────────────────────


def _badges_html(p: dict) -> str:
    badges = []
    if p.get("favorita"):
        badges.append('<span class="v2-badge favorite">❤️ Favorita</span>')
    if p.get("descartada"):
        badges.append('<span class="v2-badge discarded">❌ Descartada</span>')
    if p.get("visitada"):
        badges.append('<span class="v2-badge visited">🏠 Visitada</span>')
    if p.get("oferta_realizada"):
        resp = p.get("respuesta_oferta")
        if resp:
            badges.append(
                f'<span class="v2-badge offer">💰 {html_lib.escape(str(resp))}</span>'
            )
        else:
            badges.append('<span class="v2-badge offer">💰 Oferta</span>')
    if not p.get("activa", True):
        est = html_lib.escape(str(p.get("estado") or "Vendida"))
        badges.append(f'<span class="v2-badge inactive">🚫 {est}</span>')
    if not badges:
        return ""
    return f'<div class="v2-badges">{"".join(badges)}</div>'


# ── Chips ──────────────────────────────────────────────────────────────


def _chips_html(p: dict) -> str:
    chips = p.get("chips") or []
    if not chips:
        return ""
    items = "".join(
        f'<span class="v2-chip">{html_lib.escape(str(c))}</span>' for c in chips
    )
    return f'<div class="v2-chips">{items}</div>'


# ── Meta ───────────────────────────────────────────────────────────────


def _meta_html(p: dict) -> str:
    items = []
    origen = p.get("origen")
    if origen:
        items.append(
            f'<span class="v2-meta-item">🌐 {html_lib.escape(str(origen))}</span>'
        )
    dias = p.get("dias")
    if dias is not None:
        label = "hoy" if dias == 0 else f"hace {dias}d"
        items.append(f'<span class="v2-meta-item">🗓 {label}</span>')
    if p.get("es_manual"):
        items.append('<span class="v2-meta-item">📌 Manual</span>')
    if not items:
        return ""
    return f'<div class="v2-meta">{"".join(items)}</div>'


# ── Card HTML (solo visual, sin botones) ──────────────────────────────


def card_html(p: dict, index: int = 0) -> str:
    """HTML de la tarjeta: imagen + overlay + body con contenido fijo."""

    # Título (1 línea)
    titulo = html_lib.escape((p.get("titulo") or "Sin título")[:55])
    title_cls = "v2-card-title"
    if not p.get("activa", True):
        title_cls += " inactive"

    # Precio/m²
    precio_m2 = ""
    if p.get("precio_m2") is not None:
        precio_m2 = f'<div class="v2-price-m2">{fmt_eur(p["precio_m2"])} /m²</div>'

    # Detalles
    parts = [
        f'{p["superficie"]:.0f} m²' if p.get("superficie") is not None else None,
        f'{p["habitaciones"]} hab' if p.get("habitaciones") is not None else None,
        f'{p["banos"]} baños' if p.get("banos") is not None else None,
    ]
    detail = " · ".join(x for x in parts if x)

    # Ubicación (1 línea, truncada)
    ub_parts = [
        html_lib.escape(str(x))
        for x in [p.get("barrio"), p.get("municipio")]
        if x
    ]
    ub_text = ", ".join(ub_parts)
    if len(ub_text) > 30:
        ub_text = ub_text[:28] + "…"

    delay = f"{max(float(index), 0) * 0.05:.2f}s"
    return (
        f'<div class="v2-card v2-stagger" style="animation-delay:{delay};">'
        # Imagen + overlay precio
        f'{_foto_html(p)}'
        f'{_overlay_html(p)}'
        # Body con altura fija
        f'<div class="v2-card-body">'
        f'<div class="{title_cls}">{titulo}</div>'
        f'{precio_m2}'
        + (f'<div class="v2-card-summary">{detail}</div>' if detail else "")
        + (f'<div class="v2-card-location">📍 {ub_text}</div>' if ub_text else "")
        + _chips_html(p)
        + _badges_html(p)
        + _meta_html(p)
        + '</div>'
        + '</div>'
    )


# ── Persistencia ──────────────────────────────────────────────────────


def _write(p: dict, on_write, **fields):
    try:
        with Session(engine) as session:
            PropiedadCRUD.update(session, p["id"], **fields)
        p.update(fields)
        if on_write:
            on_write()
        st.rerun(scope="fragment")
    except Exception as e:
        st.error(f"Error al guardar: {e}")


# ── Fragment principal ─────────────────────────────────────────────────


@st.fragment
def render_card_v2(p: dict, on_write, index: int = 0):
    """Renderiza la tarjeta completa: HTML + botones Streamlit.

    El HTML da la estructura visual (imagen, body, badges).
    Los botones Streamlit se renderizan debajo del HTML pero visualmente
    integrados via CSS (mismo borde, misma sombra).
    """
    from ui.property_dialogs import (
        calculadora_modal,
        edit_property_dialog,
        fotos_dialog,
        buscar_fotos_dialog,
    )

    prop_id = p["id"]

    # 1. HTML puro: imagen + body + badges (sin botones interactivos)
    st.markdown(card_html(p, index=index), unsafe_allow_html=True)

    # 2. Botones de acción: Streamlit widgets fuera del HTML
    #    Pero visualmente integrados con CSS via la clase v2-card-actions-streamlit
    #
    #    favorita/descartar/visitada van agrupadas en el popover "⚙️ Estado"
    #    (mismo patrón que property_card.py v1) en vez de un botón suelto por
    #    cada una — con 4 tarjetas por fila, 7 botones sueltos quedaban
    #    diminutos e incómodos de tocar.
    st.markdown('<div class="v2-actions-streamlit">', unsafe_allow_html=True)

    b1, b2, b3, b4, b5 = st.columns(5)

    # Estado: favorita / descartar / visitada agrupados en popover
    with b1.popover("⚙️", help="Estado de la propiedad", use_container_width=True):
        st.markdown("**Estado**")
        cols = st.columns(2)

        if not p.get("favorita"):
            if cols[0].button("🤍 Favorita", key=f"v2_fav_{prop_id}", use_container_width=True):
                _write(p, on_write, favorita=True, vista=True)
        else:
            if cols[0].button("❤️ Quitar fav", key=f"v2_fav_{prop_id}", use_container_width=True):
                _write(p, on_write, favorita=False)

        if not p.get("descartada"):
            if cols[1].button("❌ Descartar", key=f"v2_disc_{prop_id}", use_container_width=True):
                _write(p, on_write, descartada=True, vista=True)
        else:
            if cols[1].button("↩️ Restaurar", key=f"v2_disc_{prop_id}", use_container_width=True):
                _write(p, on_write, descartada=False)

        visit_label = "📝 Editar visita" if p.get("visitada") else "🏠 Marcar visitada"
        if st.button(visit_label, key=f"v2_visit_{prop_id}", use_container_width=True):
            from ui.property_dialogs import visita_dialog
            with Session(engine) as session:
                prop = session.get(Propiedad, prop_id)
            visita_dialog(prop, on_write=on_write)

    # Editar
    if b2.button("✏️", key=f"v2_edit_{prop_id}",
                 help="Editar", use_container_width=True):
        with Session(engine) as session:
            prop = session.get(Propiedad, prop_id)
        edit_property_dialog(prop, on_write=on_write)

    # Calculadora
    if b3.button("🧮", key=f"v2_calc_{prop_id}",
                 help="Calculadora", use_container_width=True):
        with Session(engine) as session:
            prop = session.get(Propiedad, prop_id)
        calculadora_modal(prop)

    # Fotos
    if p.get("fotos"):
        if b4.button("📸", key=f"v2_fotos_{prop_id}",
                     help="Ver fotos", use_container_width=True):
            st.session_state[f"foto_idx_{prop_id}"] = 0
            with Session(engine) as session:
                prop = session.get(Propiedad, prop_id)
            fotos_dialog(prop)
    else:
        if b4.button("🔍", key=f"v2_buscar_{prop_id}",
                     help="Buscar fotos", use_container_width=True):
            with Session(engine) as session:
                prop = session.get(Propiedad, prop_id)
            buscar_fotos_dialog(prop, on_write=on_write)

    # URL externo
    b5.link_button("🔗", p.get("url", "#"), help="Abrir anuncio", use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

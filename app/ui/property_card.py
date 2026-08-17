"""Tarjeta visual de propiedad: HTML puro + fragment de acciones."""

import html as html_lib

import streamlit as st
from sqlmodel import Session

from db.database import engine, PropiedadCRUD
from db.models import Propiedad

_PLACEHOLDER = (
    '<div style="width:100%;aspect-ratio:16/9;{display}align-items:center;'
    'justify-content:center;background:#f0f2f6;border-radius:8px;font-size:2.5rem;">🏠</div>'
)

_CHIP = (
    '<span style="display:inline-block;background:#eef1f6;border-radius:12px;'
    'padding:1px 10px;margin:2px 4px 2px 0;font-size:0.78rem;">{label}</span>'
)


def fmt_eur(v) -> str:
    return f"{v:,.0f}".replace(",", ".") + " €"


def _foto_html(p: dict) -> str:
    if p["fotos"]:
        return (
            f'<img src="{html_lib.escape(p["fotos"][0], quote=True)}" '
            'style="width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;" '
            "onerror=\"this.style.display='none';this.nextElementSibling.style.display='flex';\">"
            + _PLACEHOLDER.format(display="display:none;")
        )
    return _PLACEHOLDER.format(display="display:flex;")


def card_html(p: dict) -> str:
    """HTML completo de una tarjeta a partir del dict de prop_to_dict."""
    titulo = html_lib.escape((p["titulo"] or "Sin título")[:80])
    if not p["activa"]:
        titulo = f"<s>{titulo}</s> 🚫 {html_lib.escape(p['estado'] or 'Vendida')}"

    precio = fmt_eur(p["precio"]) if p["precio"] is not None else "Precio N/D"
    bajada = (
        f' <span style="color:#21a366;font-size:0.95rem;font-weight:600;">↓ −{fmt_eur(p["bajada"])}</span>'
        if p["bajada"] else ""
    )
    m2_line = (
        f'<div style="color:#6b7280;font-size:0.85rem;">{fmt_eur(p["precio_m2"])[:-2]} €/m²</div>'
        if p["precio_m2"] is not None else ""
    )

    resumen = " · ".join(
        x for x in [
            html_lib.escape(p["tipo"]) if p["tipo"] else None,
            f'{p["superficie"]:.0f} m²' if p["superficie"] is not None else None,
            f'{p["habitaciones"]} hab' if p["habitaciones"] is not None else None,
            f'{p["banos"]} baños' if p["banos"] is not None else None,
        ] if x
    )
    ubicacion = ", ".join(html_lib.escape(x) for x in [p["barrio"], p["municipio"]] if x)
    chips = "".join(_CHIP.format(label=html_lib.escape(c)) for c in p["chips"])

    meta = []
    if p["origen"]:
        meta.append(f"🌐 {html_lib.escape(p['origen'])}")
    if p["dias"] is not None:
        meta.append("hoy" if p["dias"] == 0 else f"hace {p['dias']}d")
    if p["es_manual"]:
        meta.append("📌 Manual")

    return (
        f"{_foto_html(p)}"
        f'<div style="font-weight:600;margin-top:6px;line-height:1.3;">{titulo}</div>'
        f'<div style="font-size:1.35rem;font-weight:700;margin-top:2px;">{precio}{bajada}</div>'
        f"{m2_line}"
        f'<div style="font-size:0.9rem;margin-top:4px;">{resumen}</div>'
        + (f'<div style="font-size:0.85rem;color:#6b7280;">📍 {ubicacion}</div>' if ubicacion else "")
        + (f'<div style="margin-top:4px;">{chips}</div>' if chips else "")
        + (f'<div style="font-size:0.78rem;color:#9ca3af;margin-top:4px;">{" · ".join(meta)}</div>' if meta else "")
    )


def _write(p: dict, on_write, **fields):
    """Escribe campos en BD, actualiza el dict local y re-renderiza solo la tarjeta."""
    try:
        with Session(engine) as session:
            PropiedadCRUD.update(session, p["id"], **fields)
        p.update(fields)
        on_write()
        st.rerun(scope="fragment")
    except Exception as e:
        st.error(f"Error al guardar: {e}")


@st.fragment
def render_card(p: dict, on_write):
    """Tarjeta completa: HTML + fila de acciones. Cada acción re-ejecuta solo este fragment."""
    from ui.property_dialogs import calculadora_modal, edit_property_dialog, fotos_dialog, buscar_fotos_dialog

    with st.container(border=True):
        st.markdown(card_html(p), unsafe_allow_html=True)

        b = st.columns(7)
        if b[0].button("❤️" if p["favorita"] else "🤍", key=f"fav_{p['id']}", help="Favorita"):
            _write(p, on_write, favorita=not p["favorita"], vista=True)
        if b[1].button("↩️" if p["descartada"] else "❌", key=f"disc_{p['id']}",
                       help="Restaurar" if p["descartada"] else "Descartar"):
            _write(p, on_write, descartada=not p["descartada"], vista=True)
        if b[2].button("✏️", key=f"edit_{p['id']}", help="Editar"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            edit_property_dialog(prop, on_write=on_write)
        if b[3].button("🧮", key=f"calc_{p['id']}", help="Calculadora"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            calculadora_modal(prop)
        if p["fotos"]:
            if b[4].button("📸", key=f"fotos_{p['id']}", help="Ver fotos"):
                st.session_state[f"foto_idx_{p['id']}"] = 0
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                fotos_dialog(prop)
        else:
            if b[4].button("🔍", key=f"buscar_fotos_{p['id']}", help="Buscar fotos"):
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                buscar_fotos_dialog(prop, on_write=on_write)
        b[5].link_button("🔗", p["url"], help="Abrir anuncio")
        if b[6].button("✓" if p["vista"] else "👁", key=f"view_{p['id']}", help="Marcar vista"):
            _write(p, on_write, vista=not p["vista"])

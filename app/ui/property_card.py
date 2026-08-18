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

    # Status chips
    status_chips = []
    if p.get("favorita"):
        status_chips.append("❤️ Favorita")
    if p.get("descartada"):
        status_chips.append("❌ Descartada")
    if p.get("visitada"):
        status_chips.append("🏠 Visitada")
        if p.get("oferta_realizada"):
            if p.get("respuesta_oferta"):
                status_chips.append(f"💰 Oferta: {p['respuesta_oferta']}")
            else:
                status_chips.append("💰 Oferta realizada")
        if p.get("precio_oferta"):
            status_chips.append(f"→ {fmt_eur(p['precio_oferta'])}")
    if not p.get("activa"):
        status_chips.append(f"🚫 {p.get('estado') or 'Vendida'}")

    chips_html = ""
    if status_chips:
        chips_html = " ".join(
            f'<span style="display:inline-block;background:#fef3c7;border-radius:12px;padding:1px 8px;margin:2px 4px 2px 0;font-size:0.75rem;">{html_lib.escape(c)}</span>'
            for c in status_chips
        )

    return (
        f"{_foto_html(p)}"
        f'<div style="font-weight:600;margin-top:6px;line-height:1.3;">{titulo}</div>'
        f'<div style="font-size:1.35rem;font-weight:700;margin-top:2px;">{precio}{bajada}</div>'
        f"{m2_line}"
        f'<div style="font-size:0.9rem;margin-top:4px;">{resumen}</div>'
        + (f'<div style="font-size:0.85rem;color:#6b7280;">📍 {ubicacion}</div>' if ubicacion else "")
        + (f'<div style="margin-top:4px;">{chips}</div>' if chips else "")
        + (f'<div style="font-size:0.78rem;color:#9ca3af;margin-top:4px;">{" · ".join(meta)}</div>' if meta else "")
        + (f'<div style="margin-top:4px;">{chips_html}</div>' if chips_html else "")
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

        b = st.columns(5)

        # b[0]: Status dropdown
        status_options = []
        status_labels = {}

        # Always available
        status_options.append("none_reset")  # hidden default
        status_labels["none_reset"] = "⚙️ Estado..."

        if not p["favorita"]:
            status_labels["fav"] = "🤍 Marcar favorita"
            status_options.append("fav")
        else:
            status_labels["unfav"] = "❤️ Quitar favorita"
            status_options.append("unfav")

        if not p["descartada"]:
            status_labels["discard"] = "❌ Descartar"
            status_options.append("discard")
        else:
            status_labels["restore"] = "↩️ Restaurar"
            status_options.append("restore")

        if not p["vista"]:
            status_labels["viewed"] = "👁 Marcar vista"
            status_options.append("viewed")

        if not p.get("visitada"):
            status_labels["visited"] = "🏠 Marcar visitada"
            status_options.append("visited")
        else:
            status_labels["unvisited"] = "📝 Editar visita"
            status_options.append("unvisited")

        selected = b[0].selectbox(
            "Estado",
            options=status_options,
            format_func=lambda x: status_labels.get(x, x),
            key=f"status_{p['id']}",
            label_visibility="collapsed",
        )

        if selected == "fav":
            _write(p, on_write, favorita=True, vista=True)
        elif selected == "unfav":
            _write(p, on_write, favorita=False)
        elif selected == "discard":
            _write(p, on_write, descartada=True, vista=True)
        elif selected == "restore":
            _write(p, on_write, descartada=False)
        elif selected == "viewed":
            _write(p, on_write, vista=True)
        elif selected == "visited":
            from ui.property_dialogs import visita_dialog
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            visita_dialog(prop, on_write=on_write)
        elif selected == "unvisited":
            from ui.property_dialogs import visita_dialog
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            visita_dialog(prop, on_write=on_write)

        # b[1]: edit
        if b[1].button("✏️", key=f"edit_{p['id']}", help="Editar"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            edit_property_dialog(prop, on_write=on_write)
        # b[2]: calculator
        if b[2].button("🧮", key=f"calc_{p['id']}", help="Calculadora"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            calculadora_modal(prop)
        # b[3]: photos
        if p["fotos"]:
            if b[3].button("📸", key=f"fotos_{p['id']}", help="Ver fotos"):
                st.session_state[f"foto_idx_{p['id']}"] = 0
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                fotos_dialog(prop)
        else:
            if b[3].button("🔍", key=f"buscar_fotos_{p['id']}", help="Buscar fotos"):
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                buscar_fotos_dialog(prop, on_write=on_write)
        # b[4]: link
        b[4].link_button("🔗", p["url"], help="Abrir anuncio")
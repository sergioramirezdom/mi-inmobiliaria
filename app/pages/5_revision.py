"""Revisión y enriquecimiento de propiedades con datos incompletos."""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from sqlalchemy import or_

from db.database import engine, PropiedadCRUD
from db.models import Propiedad
from scraper.description_enricher import extract_suggestions

st.set_page_config(page_title="Revisión", page_icon="🔎", layout="wide")
st.title("🔎 Revisión de propiedades")
st.caption("Sugerencias de datos extraídas de la descripción. Aprueba o rechaza cada una antes de guardar.")

FIELD_LABELS = {
    "ascensor": "Ascensor",
    "garaje": "Garaje",
    "terraza": "Terraza",
    "balcon": "Balcón",
    "piscina": "Piscina",
    "trastero": "Trastero",
    "aire_acondicionado": "Aire A/C",
    "habitaciones": "Habitaciones",
    "banos": "Baños",
    "barrio": "Barrio/Zona",
    "zona_normalizada": "Zona canónica",
    "superficie_m2": "Superficie m²",
}

BOOL_DISPLAY = {True: "✅ Sí", False: "❌ No"}


def val_display(v):
    if isinstance(v, bool):
        return BOOL_DISPLAY[v]
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


try:
    with Session(engine) as session:
        # Load active, non-discarded properties with description and at least one empty field
        propiedades = session.exec(
            select(Propiedad)
            .where(
                Propiedad.activa == True,
                Propiedad.descartada == False,
                Propiedad.descripcion != None,
                or_(
                    Propiedad.ascensor == None,
                    Propiedad.garaje == None,
                    Propiedad.terraza == None,
                    Propiedad.balcon == None,
                    Propiedad.piscina == None,
                    Propiedad.trastero == None,
                    Propiedad.aire_acondicionado == None,
                    Propiedad.habitaciones == None,
                    Propiedad.banos == None,
                    Propiedad.barrio == None,
                    Propiedad.zona_normalizada == None,
                    Propiedad.superficie_m2 == None,
                ),
            )
            .order_by(Propiedad.fecha_scraping.desc())
            .limit(300)
        ).all()

    # Extract suggestions (outside the session context)
    pending = [(p, extract_suggestions(p)) for p in propiedades]
    pending = [(p, s) for p, s in pending if s]

    if not pending:
        st.success("✅ No hay propiedades pendientes de revisión")
        st.stop()

    # ── Summary ──────────────────────────────────────────────────────────
    total_suggestions = sum(len(s) for _, s in pending)
    st.info(
        f"**{len(pending)}** propiedades con sugerencias • "
        f"**{total_suggestions}** campos propuestos en total"
    )

    # ── Sidebar: bulk actions + field filter ─────────────────────────────
    with st.sidebar:
        st.title("🔧 Opciones")

        field_filter = st.multiselect(
            "Filtrar por campo sugerido",
            options=list(FIELD_LABELS.keys()),
            format_func=lambda k: FIELD_LABELS[k],
            default=[],
        )

        show_max = st.slider("Propiedades a mostrar", 5, 50, 20)

        st.divider()
        st.subheader("⚡ Acción masiva")
        st.caption("Acepta todas las sugerencias de todas las propiedades mostradas.")
        if st.button("✅ Aplicar TODAS las sugerencias", type="primary", use_container_width=True):
            applied = 0
            with Session(engine) as bulk_session:
                for prop, suggestions in pending:
                    updates = {f: v for f, (v, _) in suggestions.items()}
                    if updates:
                        PropiedadCRUD.update(bulk_session, prop.id, **updates)
                        applied += 1
            st.success(f"✅ {applied} propiedades actualizadas")
            st.rerun()

    # Apply field filter
    if field_filter:
        pending = [(p, {f: v for f, v in s.items() if f in field_filter}) for p, s in pending]
        pending = [(p, s) for p, s in pending if s]

    # ── Individual cards ─────────────────────────────────────────────────
    for prop, suggestions in pending[:show_max]:
        with st.container(border=True):
            col_hdr, col_link = st.columns([5, 1])
            with col_hdr:
                tipo_icon = {"piso": "🏢", "casa": "🏠", "ático": "🏙️", "bajo": "🏪"}.get(
                    (prop.tipo_propiedad or "").lower(), "🏘️"
                )
                st.markdown(f"{tipo_icon} **{prop.titulo[:90]}**")
                meta = []
                if prop.precio:
                    meta.append(f"€{prop.precio:,.0f}")
                if prop.superficie_m2:
                    meta.append(f"{prop.superficie_m2:.0f}m²")
                if prop.habitaciones:
                    meta.append(f"{prop.habitaciones} hab")
                meta.append(prop.origen_web or "")
                st.caption(" · ".join(m for m in meta if m))
            with col_link:
                st.link_button("🔗 Ficha", prop.url_original, use_container_width=True)

            # Description excerpt
            if prop.descripcion:
                with st.expander("📄 Ver descripción"):
                    st.caption(prop.descripcion[:600] + ("…" if len(prop.descripcion) > 600 else ""))

            # Suggestions as checkboxes in columns
            n_cols = min(len(suggestions), 5)
            cols = st.columns(n_cols)
            accepted: dict = {}
            for idx, (field, (value, reason)) in enumerate(suggestions.items()):
                with cols[idx % n_cols]:
                    label = FIELD_LABELS.get(field, field)
                    display = val_display(value)
                    checked = st.checkbox(
                        f"**{label}**: {display}",
                        value=True,
                        key=f"chk_{prop.id}_{field}",
                        help=reason,
                    )
                    accepted[field] = (checked, value)

            col_apply, col_skip, _ = st.columns([1, 1, 3])
            with col_apply:
                if st.button(
                    "💾 Guardar seleccionadas",
                    key=f"apply_{prop.id}",
                    use_container_width=True,
                    type="primary",
                ):
                    updates = {f: v for f, (chk, v) in accepted.items() if chk}
                    if updates:
                        with Session(engine) as upd_session:
                            PropiedadCRUD.update(upd_session, prop.id, **updates)
                        labels = [FIELD_LABELS.get(f, f) for f in updates]
                        st.success(f"✅ Guardado: {', '.join(labels)}")
                        st.rerun()
                    else:
                        st.warning("Ningún campo seleccionado")
            with col_skip:
                if st.button(
                    "⏭️ Ignorar",
                    key=f"skip_{prop.id}",
                    use_container_width=True,
                ):
                    # Mark descripcion as reviewed by setting a flag — simplest way:
                    # just rerun (no persistent skip, property will reappear only if still incomplete)
                    st.rerun()

except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

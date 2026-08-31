"""Página de gestión de filtros y alertas."""

import logging
import streamlit as st
import sys
import json
from pathlib import Path
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

from db.database import engine, PropiedadCRUD
from db.models import FiltroAlerta, Propiedad
from notifications.filter_matcher import FilterMatcher
from notifications.alert_routing import TIPO_NUEVAS, TIPO_BAJADAS_FAVORITAS
from scraper.zona_normalizer import cargar_catalogo

TIPO_ALERTA_OPTS = [TIPO_NUEVAS, TIPO_BAJADAS_FAVORITAS]
TIPO_ALERTA_LABELS = {
    TIPO_NUEVAS: "🆕 Nuevas propiedades (con criterios)",
    TIPO_BAJADAS_FAVORITAS: "📉 Bajadas de precio de favoritas (sin criterios)",
}

st.set_page_config(page_title="Gestión de Alertas", page_icon="🔔", layout="wide")

TIPOS_PROPIEDAD = ["", "Piso", "Apartamento", "Casa", "Dúplex", "Estudio", "Local", "Parcela", "Garaje"]
ESTADOS = ["", "Nueva", "Buen estado", "Para reformar", "Reformado", "En construcción"]
AMENIDADES_OPTS = ["Ascensor", "Garaje", "Piscina", "Terraza", "Balcón", "Aire acondicionado",
                   "Amueblado", "Trastero", "Patio", "Calefacción"]


@st.cache_data(ttl=300)
def get_distinct_zonas_cached() -> list[str]:
    """Cached list of zona_normalizada values from DB, used as multiselect suggestions."""
    try:
        with Session(engine) as session:
            return PropiedadCRUD.get_distinct_zonas_normalizadas(session)
    except Exception as e:
        logger.warning(f"Could not load zona suggestions: {e}")
        return []


def build_criteria(precio_min, precio_max, m2_min, m2_max, habitaciones, banos,
                   barrio, tipo_propiedad, estado, amenidades,
                   ascensor, garaje, terraza, piscina):
    """Build criteria dict from form values."""
    return FilterMatcher.create_criteria_dict(
        precio_min=precio_min if precio_min > 0 else None,
        precio_max=precio_max if precio_max > 0 else None,
        m2_min=m2_min if m2_min > 0 else None,
        m2_max=m2_max if m2_max > 0 else None,
        habitaciones=habitaciones if habitaciones > 0 else None,
        banos=banos if banos > 0 else None,
        barrio=", ".join(z.strip() for z in barrio if z.strip()) if barrio else None,
        tipo_propiedad=tipo_propiedad if tipo_propiedad else None,
        estado=estado if estado else None,
        amenidades=",".join(amenidades) if amenidades else None,
    )


def resolve_criterios_json(tipo_alerta: str, criterios: dict):
    """Serialise criteria for persistence given the alert type.

    A ``bajadas_favoritas`` alert has no criteria — it is a pure switch — so its
    ``criterios_json`` is stored as ``None``. Switching an existing ``nuevas``
    alert to ``bajadas_favoritas`` therefore clears its criteria destructively;
    switching back does not restore them (the form starts empty).
    """
    if tipo_alerta == TIPO_BAJADAS_FAVORITAS:
        return None
    return json.dumps(criterios)


def criteria_form(prefix: str, defaults: dict = None):
    """Render reusable criteria form fields. Returns dict of values."""
    d = defaults or {}

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        precio_min = st.number_input("Precio mínimo (€)", min_value=0, step=10000,
                                     value=int(d.get("precio_min", 0)), key=f"{prefix}_pmin")
    with col_p2:
        precio_max = st.number_input("Precio máximo (€)", min_value=0, step=10000,
                                     value=int(d.get("precio_max", 0)), key=f"{prefix}_pmax")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        m2_min = st.number_input("m² mínimos", min_value=0, step=10,
                                  value=int(d.get("m2_min", 0)), key=f"{prefix}_m2min")
    with col_m2:
        m2_max = st.number_input("m² máximos", min_value=0, step=10,
                                  value=int(d.get("m2_max", 0)), key=f"{prefix}_m2max")

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        habitaciones = st.number_input("Mín. habitaciones", min_value=0, max_value=10,
                                       value=int(d.get("habitaciones", 0)), key=f"{prefix}_hab")
    with col_h2:
        banos = st.number_input("Mín. baños", min_value=0, max_value=5,
                                value=int(d.get("banos", 0)), key=f"{prefix}_ban")

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        tipo_opts = TIPOS_PROPIEDAD
        tipo_val = d.get("tipo_propiedad", "")
        tipo_idx = tipo_opts.index(tipo_val) if tipo_val in tipo_opts else 0
        tipo_propiedad = st.selectbox("Tipo de propiedad", tipo_opts,
                                      index=tipo_idx, key=f"{prefix}_tipo")
    with col_t2:
        estado_opts = ESTADOS
        estado_val = d.get("estado", "")
        estado_idx = estado_opts.index(estado_val) if estado_val in estado_opts else 0
        estado = st.selectbox("Estado", estado_opts, index=estado_idx, key=f"{prefix}_estado")

    zonas_existentes = get_distinct_zonas_cached()
    barrio_val = d.get("barrio", "")
    barrio_default = [b.strip() for b in barrio_val.split(",") if b.strip()] if barrio_val else []
    barrio = st.multiselect(
        "Zona (una o varias — coincide con cualquiera)",
        options=sorted(
            set(cargar_catalogo()) | set(zonas_existentes) | set(barrio_default)
        ),
        default=barrio_default,
        accept_new_options=True,
        key=f"{prefix}_barrio",
        help="Selecciona zonas normalizadas del catálogo. También puedes escribir libremente.",
    )

    amenidades_val = d.get("amenidades", "")
    amenidades_default = [a.strip() for a in amenidades_val.split(",") if a.strip()] if amenidades_val else []
    amenidades = st.multiselect("Amenidades requeridas", AMENIDADES_OPTS,
                                default=amenidades_default, key=f"{prefix}_amen")

    st.caption("Características booleanas:")
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    with col_c1:
        ascensor = st.checkbox("Ascensor", key=f"{prefix}_asc")
    with col_c2:
        garaje = st.checkbox("Garaje", key=f"{prefix}_gar")
    with col_c3:
        terraza = st.checkbox("Terraza", key=f"{prefix}_ter")
    with col_c4:
        piscina = st.checkbox("Piscina", key=f"{prefix}_pis")

    return dict(precio_min=precio_min, precio_max=precio_max, m2_min=m2_min, m2_max=m2_max,
                habitaciones=habitaciones, banos=banos, barrio=barrio, tipo_propiedad=tipo_propiedad,
                estado=estado, amenidades=amenidades, ascensor=ascensor, garaje=garaje,
                terraza=terraza, piscina=piscina)


@st.dialog("✏️ Editar alerta", width="large")
def edit_alert_dialog(filtro: FiltroAlerta):
    """Modal de edición de alerta."""
    criterios = FilterMatcher.parse_criteria(filtro.criterios_json)

    nombre = st.text_input("Nombre", value=filtro.nombre)
    chat_id = st.text_input("Chat ID Telegram (opcional)", value=filtro.chat_id_telegram or "",
                            help="Deja vacío para usar el chat ID por defecto del .env")

    tipo_actual = getattr(filtro, "tipo_alerta", TIPO_NUEVAS) or TIPO_NUEVAS
    tipo_alerta = st.selectbox(
        "Tipo de alerta",
        TIPO_ALERTA_OPTS,
        index=TIPO_ALERTA_OPTS.index(tipo_actual) if tipo_actual in TIPO_ALERTA_OPTS else 0,
        format_func=lambda t: TIPO_ALERTA_LABELS.get(t, t),
        key="edit_tipo_alerta",
    )

    es_favoritas = tipo_alerta == TIPO_BAJADAS_FAVORITAS
    if es_favoritas:
        st.info("Esta alerta notifica bajadas de precio de propiedades marcadas como favoritas. No usa criterios.")
        if criterios:
            st.warning("Al guardar como *bajadas de favoritas* se borrarán los criterios actuales.")
        vals = None
    else:
        st.markdown("### Criterios")
        vals = criteria_form("edit", criterios)

    if es_favoritas and not (chat_id or "").strip():
        st.caption("Sin Chat ID: los avisos irán al chat global (duplican el aviso de bajadas global).")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Guardar", type="primary", use_container_width=True):
            nuevos_criterios = build_criteria(**vals) if vals is not None else {}
            with Session(engine) as session:
                f = session.get(FiltroAlerta, filtro.id)
                f.nombre = nombre or filtro.nombre
                f.tipo_alerta = tipo_alerta
                f.criterios_json = resolve_criterios_json(tipo_alerta, nuevos_criterios)
                f.chat_id_telegram = chat_id.strip() or None
                session.add(f)
                session.commit()
            st.success("✅ Alerta actualizada")
            st.rerun()
    with col2:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()


@st.dialog("🔍 Propiedades coincidentes", width="large")
def test_alert_dialog(filtro: FiltroAlerta):
    """Muestra propiedades actuales que coinciden con el filtro."""
    criterios = FilterMatcher.parse_criteria(filtro.criterios_json)
    st.caption(f"Filtro: **{filtro.nombre}** — {FilterMatcher.format_criteria(criterios)}")

    with Session(engine) as session:
        propiedades = session.exec(
            select(Propiedad).where(Propiedad.activa == True).limit(500)
        ).all()

    matches = FilterMatcher.get_matching_properties(propiedades, filtro)

    if not matches:
        st.warning("Ninguna propiedad actual coincide con estos criterios.")
        return

    st.success(f"✅ **{len(matches)}** propiedades coinciden")
    st.divider()

    for prop in matches[:20]:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{prop.titulo[:70]}**")
                parts = []
                if prop.precio:
                    parts.append(f"💰 €{prop.precio:,.0f}")
                if prop.superficie_m2:
                    parts.append(f"📐 {prop.superficie_m2:.0f}m²")
                if prop.habitaciones:
                    parts.append(f"🛏️ {prop.habitaciones} hab")
                if prop.barrio:
                    parts.append(f"📍 {prop.barrio}")
                st.caption(" • ".join(parts))
            with col2:
                st.link_button("🔗 Ver", prop.url_original, use_container_width=True)

    if len(matches) > 20:
        st.caption(f"... y {len(matches) - 20} más. Ve a Propiedades para ver todas.")


# ─── PÁGINA PRINCIPAL ─────────────────────────────────────────────────────────

st.title("🔔 Gestión de Alertas")
st.markdown("Crea filtros para recibir notificaciones en Telegram cuando aparezcan propiedades que coincidan.")

col_form, col_list = st.columns([1, 2])

# ─── FORMULARIO CREAR ────────────────────────────────────────────────────────
with col_form:
    st.subheader("➕ Nueva alerta")

    # Rendered OUTSIDE st.form so the criteria block can react to the selection
    # immediately (forms do not rerun on widget change until submit).
    tipo_alerta_create = st.selectbox(
        "Tipo de alerta",
        TIPO_ALERTA_OPTS,
        format_func=lambda t: TIPO_ALERTA_LABELS.get(t, t),
        key="create_tipo_alerta",
    )
    crear_favoritas = tipo_alerta_create == TIPO_BAJADAS_FAVORITAS
    if crear_favoritas:
        st.info("Notifica bajadas de precio de propiedades favoritas. No usa criterios.")

    with st.form("create_alert_form", clear_on_submit=True):
        nombre = st.text_input("Nombre *", placeholder="ej: Piso barato en Centro")
        chat_id = st.text_input("Chat ID Telegram (opcional)",
                                help="Deja vacío para usar el del .env")

        if crear_favoritas:
            vals = None
            st.caption("Sin criterios: se avisa de cualquier favorita que baje de precio.")
        else:
            st.markdown("### Criterios")
            vals = criteria_form("create")

        if st.form_submit_button("✅ Crear alerta", use_container_width=True):
            if not nombre.strip():
                st.error("El nombre es obligatorio")
            else:
                criterios = build_criteria(**vals) if vals is not None else {}
                with Session(engine) as session:
                    session.add(FiltroAlerta(
                        nombre=nombre.strip(),
                        tipo_alerta=tipo_alerta_create,
                        criterios_json=resolve_criterios_json(tipo_alerta_create, criterios),
                        chat_id_telegram=chat_id.strip() or None,
                        activo=True,
                    ))
                    session.commit()
                st.success(f"✅ Alerta '{nombre}' creada")
                st.rerun()

# ─── LISTA DE ALERTAS ─────────────────────────────────────────────────────────
with col_list:
    st.subheader("📋 Alertas configuradas")

    try:
        with Session(engine) as session:
            filtros = session.exec(
                select(FiltroAlerta).order_by(FiltroAlerta.created_at.desc())
            ).all()

        # Get property count for matching stats
        with Session(engine) as session:
            todas_props = session.exec(
                select(Propiedad).where(Propiedad.activa == True).limit(500)
            ).all()

        if not filtros:
            st.info("No hay alertas. Crea una en el formulario de la izquierda.")
        else:
            st.write(f"**{len(filtros)} alerta(s)**")
            st.divider()

            for filtro in filtros:
                _tipo = getattr(filtro, "tipo_alerta", TIPO_NUEVAS) or TIPO_NUEVAS
                if _tipo == TIPO_BAJADAS_FAVORITAS:
                    matches_count = None
                else:
                    matches_count = len(FilterMatcher.get_matching_properties(todas_props, filtro))

                with st.container(border=True):
                    col_name, col_badge, col_actions = st.columns([3, 1, 2])

                    with col_name:
                        icon = "🟢" if filtro.activo else "🔴"
                        tipo = getattr(filtro, "tipo_alerta", TIPO_NUEVAS) or TIPO_NUEVAS
                        es_favoritas = tipo == TIPO_BAJADAS_FAVORITAS
                        badge = " `📉 favoritas`" if es_favoritas else ""
                        st.markdown(f"### {icon} {filtro.nombre}{badge}")
                        criterios = FilterMatcher.parse_criteria(filtro.criterios_json)
                        if es_favoritas:
                            st.caption("Bajadas de precio de favoritas (sin criterios)")
                        else:
                            st.caption(FilterMatcher.format_criteria(criterios))
                        if filtro.chat_id_telegram:
                            st.caption(f"📱 Chat: `{filtro.chat_id_telegram}`")
                        elif es_favoritas:
                            st.caption("📱 Chat global (duplica el aviso de bajadas global)")

                    with col_badge:
                        st.metric("Coinciden", "—" if matches_count is None else matches_count)

                    with col_actions:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("🔍 Probar", key=f"test_{filtro.id}",
                                         use_container_width=True, help="Ver propiedades que coinciden ahora"):
                                test_alert_dialog(filtro)

                            if st.button("✏️ Editar", key=f"edit_{filtro.id}",
                                         use_container_width=True):
                                edit_alert_dialog(filtro)

                        with c2:
                            toggle_label = "⏸ Pausar" if filtro.activo else "▶ Activar"
                            if st.button(toggle_label, key=f"toggle_{filtro.id}",
                                         use_container_width=True):
                                with Session(engine) as s:
                                    f = s.get(FiltroAlerta, filtro.id)
                                    f.activo = not f.activo
                                    s.add(f)
                                    s.commit()
                                st.rerun()

                            if st.button("🗑️ Eliminar", key=f"del_{filtro.id}",
                                         use_container_width=True):
                                with Session(engine) as s:
                                    s.delete(s.get(FiltroAlerta, filtro.id))
                                    s.commit()
                                st.rerun()

                    with st.expander("Ver criterios JSON"):
                        st.json(criterios)

    except Exception as e:
        st.error(f"❌ Error: {e}")

# ─── AYUDA ────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("💡 Cómo funcionan las alertas"):
    st.markdown("""
**Flujo automático:**
1. El scheduler scrapeea nuevas propiedades según el intervalo de cada fuente
2. Cada nueva propiedad se compara contra todos los filtros activos
3. Si coincide, se envía un mensaje Telegram con los datos de la propiedad

**Botón "Probar":** Ejecuta el filtro contra las propiedades ya guardadas en la BD y muestra las coincidencias en tiempo real.

**Chat ID Telegram:** Si lo dejas vacío, las notificaciones van al chat configurado en `.env`. Si lo rellenas, esa alerta envía al chat específico (útil para compartir alertas con otras personas).

**Criterios combinados:** Todos los criterios son AND — la propiedad debe cumplir TODOS para coincidir.
""")

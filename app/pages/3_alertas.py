"""Página de gestión de filtros y alertas."""

import streamlit as st
import sys
import json
from pathlib import Path
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine
from db.models import FiltroAlerta
from notifications.filter_matcher import FilterMatcher

# Page config
st.set_page_config(
    page_title="Gestión de Alertas",
    page_icon="🔔",
    layout="wide"
)

st.title("🔔 Gestión de Alertas")
st.markdown("Crea filtros para recibir notificaciones en Telegram de propiedades que coincidan con tus criterios.")

# Create two columns
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("➕ Crear Nueva Alerta")

    with st.form("create_alert_form", clear_on_submit=True):
        nombre = st.text_input(
            "Nombre de la alerta",
            placeholder="ej: Apartamento barato en Centro",
            help="Nombre descriptivo para identificar la alerta"
        )

        st.markdown("### Criterios de Búsqueda")

        # Price
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            precio_min = st.number_input(
                "Precio mínimo (€)",
                min_value=0,
                value=0,
                step=10000,
                help="Dejar en 0 para sin límite"
            )
        with col_p2:
            precio_max = st.number_input(
                "Precio máximo (€)",
                min_value=0,
                value=200000,
                step=10000,
                help="Dejar en 0 para sin límite"
            )

        # Size
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            m2_min = st.number_input(
                "m² mínimos",
                min_value=0,
                value=0,
                step=10,
                help="Dejar en 0 para sin límite"
            )
        with col_m2:
            m2_max = st.number_input(
                "m² máximos",
                min_value=0,
                value=0,
                step=10,
                help="Dejar en 0 para sin límite"
            )

        # Rooms
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            habitaciones = st.number_input(
                "Mínimo de habitaciones",
                min_value=0,
                value=0,
                max_value=10,
                help="0 = sin límite"
            )
        with col_h2:
            banos = st.number_input(
                "Mínimo de baños",
                min_value=0,
                value=0,
                max_value=5,
                help="0 = sin límite"
            )

        # Location & Type
        barrio = st.text_input(
            "Zona/Barrio (opcional)",
            placeholder="ej: Centro, Crevillet, etc.",
            help="Búsqueda parcial, no es exacta"
        )

        tipo_propiedad = st.selectbox(
            "Tipo de propiedad (opcional)",
            ["Todas", "Piso", "Apartamento", "Casa", "Duplex", "Estudio"],
            help="Selecciona el tipo deseado"
        )

        estado = st.selectbox(
            "Estado (opcional)",
            ["Todos", "Nueva", "Buen estado", "Para reformar"],
            help="Condición de la propiedad"
        )

        # Amenities
        amenidades = st.multiselect(
            "Amenidades deseadas (opcional)",
            ["Ascensor", "Garaje", "Piscina", "Terraza", "Balcón", "Aire acondicionado"],
            help="Deja vacío para cualquier amenidad"
        )

        submitted = st.form_submit_button("✅ Crear Alerta", use_container_width=True)

        if submitted:
            if not nombre.strip():
                st.error("❌ El nombre de la alerta es obligatorio")
            else:
                try:
                    # Build criteria dictionary
                    criterios = FilterMatcher.create_criteria_dict(
                        precio_min=precio_min if precio_min > 0 else None,
                        precio_max=precio_max if precio_max > 0 else None,
                        m2_min=m2_min if m2_min > 0 else None,
                        m2_max=m2_max if m2_max > 0 else None,
                        habitaciones=habitaciones if habitaciones > 0 else None,
                        banos=banos if banos > 0 else None,
                        barrio=barrio.strip() if barrio.strip() else None,
                        tipo_propiedad=tipo_propiedad if tipo_propiedad != "Todas" else None,
                        estado=estado if estado != "Todos" else None,
                        amenidades=",".join(amenidades) if amenidades else None,
                    )

                    with Session(engine) as session:
                        filtro = FiltroAlerta(
                            nombre=nombre.strip(),
                            criterios_json=json.dumps(criterios),
                            activo=True
                        )
                        session.add(filtro)
                        session.commit()

                        st.success(f"✅ Alerta '{nombre}' creada correctamente")
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error al crear la alerta: {e}")

with col2:
    st.subheader("📋 Alertas Activas")

    try:
        with Session(engine) as session:
            stmt = select(FiltroAlerta).order_by(FiltroAlerta.created_at.desc())
            filtros = session.exec(stmt).all()

            if not filtros:
                st.info("📌 No hay alertas configuradas. Crea una en el formulario de la izquierda.")
            else:
                st.write(f"**Total: {len(filtros)} alerta(s)**")
                st.divider()

                for filtro in filtros:
                    with st.container(border=True):
                        # Header
                        col_name, col_status, col_actions = st.columns([2, 0.8, 1.2])

                        with col_name:
                            status_icon = "🟢" if filtro.activo else "🔴"
                            st.markdown(f"### {status_icon} {filtro.nombre}")

                        with col_status:
                            st.caption(
                                f"📅 {filtro.created_at.strftime('%d/%m/%y')}"
                            )

                        with col_actions:
                            col_toggle, col_delete = st.columns(2)

                            with col_toggle:
                                if st.button(
                                    "✓ Activa" if not filtro.activo else "✗ Desactiva",
                                    key=f"toggle_{filtro.id}",
                                    use_container_width=True,
                                    type="secondary"
                                ):
                                    with Session(engine) as s:
                                        f = s.get(FiltroAlerta, filtro.id)
                                        f.activo = not f.activo
                                        s.add(f)
                                        s.commit()
                                    st.rerun()

                            with col_delete:
                                if st.button(
                                    "🗑️ Eliminar",
                                    key=f"delete_{filtro.id}",
                                    use_container_width=True
                                ):
                                    with Session(engine) as s:
                                        s.delete(s.get(FiltroAlerta, filtro.id))
                                        s.commit()
                                    st.success("Alerta eliminada")
                                    st.rerun()

                        # Criteria
                        criterios = FilterMatcher.parse_criteria(filtro.criterios_json)
                        criteria_text = FilterMatcher.format_criteria(criterios)
                        st.markdown(f"📋 {criteria_text}")

                        # Show example of what would match (optional)
                        with st.expander("📝 Ver criterios JSON"):
                            st.json(criterios)

    except Exception as e:
        st.error(f"❌ Error al cargar alertas: {e}")

st.divider()
st.markdown("""
### 💡 Cómo Funcionan las Alertas

1. **Crear Alerta**: Define criterios (precio, zona, habitaciones, etc.)
2. **Automático**: Cuando el scheduler scrapeea, verifica nuevas propiedades
3. **Telegram**: Si encuentran propiedades que coinciden, ¡recibes una notificación! 📱

### 🔧 Ejemplos de Filtros

- **Apartamento barato en Centro**: Precio máx €150k, zona Centro
- **Casa espaciosa**: Mínimo 100m², 3+ habitaciones, precio máx €300k
- **Inversor**: Precio máx €100k, sin criterios de tamaño
- **Lujo**: Precio mín €500k, zona premium, ascensor obligatorio

### ⚠️ Nota
Las alertas solo funcionan si:
- El **scheduler está corriendo** (automático o en background)
- Tienes configuradas las **credenciales de Telegram** (.env)
- La alerta **está activada** (🟢 verde)
""")

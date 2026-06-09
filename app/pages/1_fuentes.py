"""Página de gestión de fuentes (URLs de inmobiliarias)."""

import streamlit as st
import logging
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


@st.cache_resource
def get_database_resources():
    """Cache database imports to avoid SQLAlchemy reload issues."""
    from db.database import engine, FuenteCRUD
    from db.models import Fuente, Propiedad
    from scraper.runner import ScraperRunner
    from scraper.config import ScraperConfig

    return {
        "engine": engine,
        "FuenteCRUD": FuenteCRUD,
        "Fuente": Fuente,
        "Propiedad": Propiedad,
        "ScraperRunner": ScraperRunner,
        "ScraperConfig": ScraperConfig,
    }


# Get all resources once (cached by Streamlit)
_resources = get_database_resources()
engine = _resources["engine"]
FuenteCRUD = _resources["FuenteCRUD"]
Fuente = _resources["Fuente"]
Propiedad = _resources["Propiedad"]
ScraperRunner = _resources["ScraperRunner"]
ScraperConfig = _resources["ScraperConfig"]

# Page config
st.set_page_config(
    page_title="Gestión de Fuentes",
    page_icon="📍",
    layout="wide"
)

st.title("📍 Gestión de Fuentes")
st.markdown("Aquí puedes añadir, editar y eliminar URLs de inmobiliarias para el scraping automático.")

# Validation function
def validate_url(url: str) -> bool:
    """Validate URL format."""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False

# Create two columns for form and list
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("➕ Añadir Nueva Fuente")

    with st.form("add_fuente_form", clear_on_submit=True):
        nombre = st.text_input(
            "Nombre de la fuente",
            placeholder="ej: Idealista Madrid",
            help="Un nombre descriptivo para identificar la fuente"
        )

        url = st.text_input(
            "URL de la inmobiliaria",
            placeholder="https://www.idealista.com/venta/viviendas/madrid/",
            help="URL completa con protocolo (http/https)"
        )

        tipo_scraper = st.selectbox(
            "Tipo de scraper",
            options=["generic", "playwright"],
            help="generic: httpx + BeautifulSoup (rápido). playwright: navegador real (más lento pero confiable)"
        )

        intervalo_horas = st.number_input(
            "Intervalo de scraping (horas)",
            min_value=1,
            max_value=168,
            value=24,
            help="Cada cuántas horas hacer scraping de esta fuente"
        )

        notas = st.text_area(
            "Notas (opcional)",
            placeholder="ej: Esta fuente requiere... / Filtros específicos...",
            height=100
        )

        submitted = st.form_submit_button("✅ Añadir Fuente", use_container_width=True)

        if submitted:
            # Validation
            if not nombre.strip():
                st.error("❌ El nombre es obligatorio")
            elif not url.strip():
                st.error("❌ La URL es obligatoria")
            elif not validate_url(url):
                st.error("❌ URL inválida. Debe comenzar con http:// o https://")
            else:
                try:
                    with Session(engine) as session:
                        # Check if URL already exists
                        existing = FuenteCRUD.get_by_url(session, url)
                        if existing:
                            st.error("⚠️ Esta URL ya existe en la base de datos")
                        else:
                            new_fuente = Fuente(
                                nombre=nombre.strip(),
                                url=url.strip(),
                                tipo_scraper=tipo_scraper,
                                intervalo_horas=int(intervalo_horas),
                                notas=notas.strip() if notas.strip() else None,
                                activa=True
                            )
                            FuenteCRUD.create(session, new_fuente)
                            st.success(f"✅ Fuente '{nombre}' añadida correctamente")
                            st.rerun()
                except Exception as e:
                    logger.error(f"Error al añadir fuente: {e}")
                    st.error(f"❌ Error al añadir la fuente: {e}")

with col2:
    st.subheader("📋 Fuentes Existentes")

    try:
        with Session(engine) as session:
            fuentes = FuenteCRUD.get_all(session)

            if not fuentes:
                st.info("📌 No hay fuentes registradas. Añade una en el formulario de la izquierda.")
            else:
                st.write(f"**Total: {len(fuentes)} fuente(s)**")
                st.divider()

                for fuente in fuentes:
                    with st.container(border=True):
                        # Header row with name and status
                        col_name, col_status, col_actions = st.columns([2, 1, 1.5])

                        with col_name:
                            status_icon = "🟢" if fuente.activa else "🔴"
                            st.markdown(f"### {status_icon} {fuente.nombre}")

                        with col_status:
                            tipo_badge = f"🤖 {fuente.tipo_scraper}"
                            st.caption(tipo_badge)

                        with col_actions:
                            col_edit, col_toggle, col_delete = st.columns(3)

                            with col_edit:
                                if st.button(
                                    "✏️ Editar",
                                    key=f"edit_{fuente.id}",
                                    use_container_width=True,
                                    type="secondary"
                                ):
                                    st.session_state[f"editing_{fuente.id}"] = True
                                    st.rerun()

                            with col_toggle:
                                if st.button(
                                    "✓ Activar" if not fuente.activa else "✗ Desactivar",
                                    key=f"toggle_{fuente.id}",
                                    use_container_width=True,
                                    type="secondary"
                                ):
                                    with Session(engine) as s:
                                        FuenteCRUD.update(s, fuente.id, activa=not fuente.activa)
                                    st.rerun()

                            with col_delete:
                                if st.button(
                                    "🗑️ Eliminar",
                                    key=f"delete_{fuente.id}",
                                    use_container_width=True
                                ):
                                    with Session(engine) as s:
                                        FuenteCRUD.delete(s, fuente.id)
                                    st.success("Fuente eliminada")
                                    st.rerun()

                        # URL
                        st.caption(f"🔗 {fuente.url}")

                        # Details
                        col_interval, col_exec = st.columns(2)
                        with col_interval:
                            st.caption(f"⏰ Cada {fuente.intervalo_horas}h")
                        with col_exec:
                            if fuente.ultima_ejecucion:
                                last_exec = fuente.ultima_ejecucion.strftime("%d/%m/%Y %H:%M")
                                st.caption(f"⏱️ Última: {last_exec}")
                            else:
                                st.caption("⏱️ Nunca ejecutada")

                        # Notes
                        if fuente.notas:
                            st.caption(f"📝 {fuente.notas}")

                        # Edit form (shown when edit button is clicked)
                        if st.session_state.get(f"editing_{fuente.id}", False):
                            st.divider()
                            st.subheader("✏️ Editar Fuente")

                            with st.form(f"edit_form_{fuente.id}"):
                                edit_nombre = st.text_input(
                                    "Nombre",
                                    value=fuente.nombre,
                                    key=f"edit_nombre_{fuente.id}"
                                )

                                edit_url = st.text_input(
                                    "URL",
                                    value=fuente.url,
                                    key=f"edit_url_{fuente.id}"
                                )

                                edit_tipo = st.selectbox(
                                    "Tipo de scraper",
                                    options=["generic", "playwright"],
                                    index=0 if fuente.tipo_scraper == "generic" else 1,
                                    key=f"edit_tipo_{fuente.id}"
                                )

                                edit_intervalo = st.number_input(
                                    "Intervalo de scraping (horas)",
                                    min_value=1,
                                    max_value=168,
                                    value=fuente.intervalo_horas,
                                    key=f"edit_intervalo_{fuente.id}"
                                )

                                edit_notas = st.text_area(
                                    "Notas (opcional)",
                                    value=fuente.notas or "",
                                    height=80,
                                    key=f"edit_notas_{fuente.id}"
                                )

                                col_save, col_cancel = st.columns(2)

                                with col_save:
                                    if st.form_submit_button("💾 Guardar Cambios", use_container_width=True):
                                        if not edit_nombre.strip():
                                            st.error("❌ El nombre es obligatorio")
                                        elif not edit_url.strip():
                                            st.error("❌ La URL es obligatoria")
                                        elif not validate_url(edit_url):
                                            st.error("❌ URL inválida")
                                        else:
                                            try:
                                                with Session(engine) as s:
                                                    # Check if new URL already exists (excluding current fuente)
                                                    existing = FuenteCRUD.get_by_url(s, edit_url.strip())
                                                    if existing and existing.id != fuente.id:
                                                        st.error("⚠️ Esta URL ya existe en la base de datos")
                                                    else:
                                                        FuenteCRUD.update(
                                                            s,
                                                            fuente.id,
                                                            nombre=edit_nombre.strip(),
                                                            url=edit_url.strip(),
                                                            tipo_scraper=edit_tipo,
                                                            intervalo_horas=int(edit_intervalo),
                                                            notas=edit_notas.strip() if edit_notas.strip() else None
                                                        )
                                                        st.success("✅ Cambios guardados")
                                                        st.session_state[f"editing_{fuente.id}"] = False
                                                        st.rerun()
                                            except Exception as e:
                                                logger.error(f"Error al actualizar fuente: {e}")
                                                st.error(f"❌ Error al guardar: {e}")

                                with col_cancel:
                                    if st.form_submit_button("❌ Cancelar", use_container_width=True, type="secondary"):
                                        st.session_state[f"editing_{fuente.id}"] = False
                                        st.rerun()

                        # Test scraping buttons
                        col_test, col_complete = st.columns([1, 1])
                        with col_test:
                            if st.button(
                                "🧪 Probar scraping",
                                key=f"test_{fuente.id}",
                                disabled=not fuente.activa,
                                help="Ejecuta un scraping de prueba para esta fuente (página actual)" if fuente.activa else "Activa la fuente primero",
                                use_container_width=True
                            ):
                                st.session_state[f"scraping_{fuente.id}"] = "simple"

                        with col_complete:
                            if st.button(
                                "🌐 Scraping Completo",
                                key=f"complete_{fuente.id}",
                                disabled=not fuente.activa,
                                help="Ejecuta scraping en TODAS las páginas (paginado)" if fuente.activa else "Activa la fuente primero",
                                use_container_width=True,
                                type="primary"
                            ):
                                st.session_state[f"scraping_{fuente.id}"] = "paginated"

                        # Execute scraping if button was clicked
                        scraping_mode = st.session_state.get(f"scraping_{fuente.id}", False)
                        if scraping_mode:
                            scraping_type = "completo (paginado)" if scraping_mode == "paginated" else "simple"
                            with st.spinner(f"🔄 Scrapeando {fuente.nombre} ({scraping_type})..."):
                                try:
                                    with Session(engine) as session:
                                        runner = ScraperRunner(session)
                                        # Run appropriate scraper in sync context
                                        if scraping_mode == "paginated":
                                            stats = asyncio.run(runner.run_paginated_scraper(fuente, results_per_page=48))
                                        else:
                                            stats = asyncio.run(runner.run_scraper(fuente))

                                    # Display results in columns
                                    if scraping_mode == "paginated":
                                        result_cols = st.columns(5)
                                        with result_cols[0]:
                                            st.metric("✅ Nuevas", stats.get("nuevas", 0))
                                        with result_cols[1]:
                                            st.metric("⚠️ Duplicadas", stats.get("duplicadas", 0))
                                        with result_cols[2]:
                                            st.metric("❌ Errores", stats.get("errores", 0))
                                        with result_cols[3]:
                                            st.metric("📄 Páginas", stats.get("paginas_procesadas", 0))
                                        with result_cols[4]:
                                            st.metric("⏱️ Tiempo (s)", stats.get("tiempo_segundos", 0))
                                    else:
                                        result_cols = st.columns(4)
                                        with result_cols[0]:
                                            st.metric("✅ Nuevas", stats.get("nuevas", 0))
                                        with result_cols[1]:
                                            st.metric("⚠️ Duplicadas", stats.get("duplicadas", 0))
                                        with result_cols[2]:
                                            st.metric("❌ Errores", stats.get("errores", 0))
                                        with result_cols[3]:
                                            st.metric("⏱️ Tiempo (s)", stats.get("tiempo_segundos", 0))

                                    # Show error details if any
                                    if stats.get("error"):
                                        st.error(f"❌ Error durante scraping: {stats['error']}")

                                    # Display newly scraped properties
                                    nuevas_count = stats.get("nuevas", 0)
                                    if nuevas_count > 0:
                                        st.divider()
                                        st.subheader(f"📊 {nuevas_count} Propiedades Nuevas")

                                        # Get recently added properties (from this scraping)
                                        try:
                                            with Session(engine) as session:
                                                stmt = (
                                                    select(Propiedad)
                                                    .where(Propiedad.fuente_id == fuente.id)
                                                    .order_by(Propiedad.created_at.desc())
                                                    .limit(nuevas_count)
                                                )
                                                nuevas_propiedades = session.exec(stmt).all()

                                                if nuevas_propiedades:
                                                    # Create dataframe for display
                                                    propiedades_data = []
                                                    for prop in nuevas_propiedades:
                                                        propiedades_data.append({
                                                            "Título": prop.titulo or "Sin título",
                                                            "Precio": f"€{prop.precio:,.0f}" if prop.precio else "N/A",
                                                            "m²": f"{prop.superficie_m2:.0f}" if prop.superficie_m2 else "N/A",
                                                            "Hab.": str(prop.habitaciones) if prop.habitaciones else "N/A",
                                                            "Baños": str(prop.banos) if prop.banos else "N/A",
                                                            "Dirección": prop.direccion or "N/A",
                                                            "URL": prop.url_original[:50] + "..." if len(prop.url_original) > 50 else prop.url_original,
                                                        })

                                                    st.dataframe(
                                                        propiedades_data,
                                                        use_container_width=True,
                                                        hide_index=True,
                                                        column_config={
                                                            "URL": st.column_config.LinkColumn("URL"),
                                                        }
                                                    )

                                        except Exception as e:
                                            logger.warning(f"Error mostrando propiedades: {e}")
                                            st.warning("No se pudieron cargar las propiedades nuevas")

                                    st.success("✅ Scraping completado")
                                    st.session_state[f"scraping_{fuente.id}"] = None

                                except asyncio.TimeoutError:
                                    st.error("⏱️ Timeout: El scraping tardó demasiado tiempo")
                                    st.session_state[f"scraping_{fuente.id}"] = None

                                except Exception as e:
                                    logger.error(f"Error en scraping de {fuente.nombre}: {e}")
                                    st.error(f"❌ Error durante scraping: {str(e)}")
                                    st.session_state[f"scraping_{fuente.id}"] = None

    except Exception as e:
        logger.error(f"Error al cargar fuentes: {e}")
        st.error(f"❌ Error al cargar las fuentes: {e}")

st.divider()
st.markdown("""
### 💡 Consejos de Uso
- **Probar scraping** (🧪): Ejecuta scraping en la página actual solamente (rápido)
- **Scraping Completo** (🌐): Ejecuta scraping en TODAS las páginas con paginación (más lento pero más completo)
- Comienza con "Probar scraping" para validar que funciona antes de usar "Scraping Completo"
- El scraping automático se ejecuta a las 08:00 y 20:00 UTC según el intervalo configurado
- El scraping completo es ideal para obtener todas las propiedades disponibles de una fuente
""")

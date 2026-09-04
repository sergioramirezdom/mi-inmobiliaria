"""Main Streamlit app for Mi Inmobiliaria Personal."""

import streamlit as st
import logging
import sys
from pathlib import Path
from sqlmodel import Session
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Consola de scrapers — Mi Inmobiliaria",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def get_db_resources():
    """Cache database imports to avoid SQLAlchemy reload issues."""
    from db.database import init_db, engine
    return {"init_db": init_db, "engine": engine}


# Initialize database on first run
@st.cache_resource
def init_database():
    """Initialize database tables if not already done."""
    db_resources = get_db_resources()
    engine = db_resources["engine"]
    init_db = db_resources["init_db"]
    try:
        with Session(engine) as session:
            logger.info("Checking database connection...")
            # Try a simple query to verify connection
            session.exec(text("SELECT 1")).all()
        init_db()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        st.error(f"Database initialization error: {e}")
        return False

# Initialize database
db_ready = init_database()

if not db_ready:
    st.stop()

# Sidebar
with st.sidebar:
    st.markdown("# 🛠️ Consola de scrapers")
    st.markdown("---")
    st.markdown("""
    Portal de administración de los scrapers que alimentan la base de datos:
    - **Fuentes** — alta y configuración de portales y sus scrapers
    - **Ejecuciones** — historial de runs y salud por fuente
    - **Alertas** — filtros que disparan avisos de Telegram

    La búsqueda de vivienda para usuarios finales vive ahora en la app web
    separada; este panel solo opera la recolección de datos.
    """)

# Main page
st.title("🛠️ Consola de administración de scrapers")

st.markdown("""
## Panel de operación

Desde aquí se administran las fuentes de datos, se lanzan scrapers y se vigila
la salud de las ejecuciones. Secciones disponibles en el menú lateral:

1. **Fuentes** — Añade y configura portales inmobiliarios y el scraper de cada uno
2. **Ejecuciones** — Revisa el historial de runs, los contadores y el estado de salud por fuente
3. **Alertas** — Define los filtros que envían notificaciones a Telegram

### Cómo empezar:

1. Ve a "Fuentes" en el menú lateral y da de alta una fuente con su URL
2. Elige el tipo de scraper y ejecuta una prueba para validar que extrae datos
3. Deja que el scheduler recoja la fuente según su `intervalo_horas`
4. Vigila "Ejecuciones" para confirmar que los runs terminan sin errores
5. Ajusta las alertas para recibir avisos de las propiedades relevantes

---

**Nota:** El scheduler (`scripts/scheduler.py`) y GitHub Actions ejecutan los
scrapers de forma periódica; las primeras ejecuciones de una fuente nueva pueden
tardar más mientras se recorre todo el listado.
""")

if not db_ready:
    st.error("❌ No se pudo conectar a la base de datos. Verifica las variables de entorno.")
else:
    st.success("✅ Conectado a la base de datos")

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
    page_title="Mi Inmobiliaria Personal",
    page_icon="🏠",
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
    st.markdown("# 🏠 Mi Inmobiliaria Personal")
    st.markdown("---")
    st.markdown("""
    Una herramienta para buscar vivienda de forma inteligente:
    - Gestiona múltiples fuentes (inmobiliarias)
    - Scralea automáticamente
    - Filtra propiedades según tus preferencias
    - Recibe alertas en Telegram
    """)

# Main page
st.title("🏠 Mi Inmobiliaria Personal")

st.markdown("""
## Bienvenido

Esta aplicación te ayuda a buscar vivienda de manera eficiente. Puedes:

1. **Gestionar Fuentes** — Añade URLs de inmobiliarias (Idealista, Fotocasa, etc.)
2. **Ver Propiedades** — Explora todas las propiedades con filtros avanzados
3. **Configurar Alertas** — Recibe notificaciones en Telegram cuando aparezcan propiedades que te interesen

### Cómo empezar:

1. Ve a la página "Fuentes" en el menú lateral
2. Añade la URL de una inmobiliaria
3. Haz clic en "Probar scraping" para validar que funciona
4. Una vez configuradas tus fuentes, establece filtros de alerta
5. ¡Listo! Recibirás notificaciones automáticas

---

**Nota:** Las primeras ejecuciones pueden tardar un poco mientras se scrapean los sitios.
""")

if not db_ready:
    st.error("❌ No se pudo conectar a la base de datos. Verifica las variables de entorno.")
else:
    st.success("✅ Conectado a la base de datos")

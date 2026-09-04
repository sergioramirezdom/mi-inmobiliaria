"""Página de ejecuciones: historial de runs y salud derivada por fuente.

Solo lectura. Toda la lógica vive en `app/admin/health.py`; esta página
únicamente consulta (`RegistroEjecucionCRUD`) y renderiza.
"""

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from admin.health import derive_health, summarize_fuente_runs  # noqa: E402

# Nº de ejecuciones recientes que se muestran en la tabla global.
RECENT_RUNS_LIMIT = 30
# Filas por fuente que se piden para derivar salud / resumen.
PER_FUENTE_LIMIT = 50

HEALTH_BADGE = {
    "OK": "🟢 OK",
    "STALE": "🟡 STALE",
    "FAILING": "🔴 FAILING",
    "UNKNOWN": "⚪ UNKNOWN",
}


@st.cache_resource
def get_database_resources():
    """Cache database imports to avoid SQLAlchemy reload issues."""
    from db.database import FuenteCRUD, RegistroEjecucionCRUD, engine

    return {
        "engine": engine,
        "FuenteCRUD": FuenteCRUD,
        "RegistroEjecucionCRUD": RegistroEjecucionCRUD,
    }


_resources = get_database_resources()
engine = _resources["engine"]
FuenteCRUD = _resources["FuenteCRUD"]
RegistroEjecucionCRUD = _resources["RegistroEjecucionCRUD"]

st.set_page_config(page_title="Ejecuciones", page_icon="📊", layout="wide")

st.title("📊 Ejecuciones y salud de las fuentes")
st.markdown(
    "Historial de scraping y sold-check por fuente, con un estado de salud "
    "derivado en el momento (no hay columna de estado en la base de datos)."
)


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def _fmt_counter(value) -> str:
    return "—" if value is None else str(value)


def _render_fuente_health(fuentes, now: datetime) -> None:
    st.subheader("Salud por fuente")
    if not fuentes:
        st.info("No hay fuentes registradas todavía. Añade una en la página de Fuentes.")
        return

    with Session(engine) as session:
        for fuente in fuentes:
            registros = RegistroEjecucionCRUD.get_by_fuente(
                session, fuente.id, limit=PER_FUENTE_LIMIT
            )
            status, reason = derive_health(fuente, registros, now=now)
            summary = summarize_fuente_runs(registros)

            with st.container(border=True):
                header = f"{HEALTH_BADGE.get(status, status)} · **{fuente.nombre}**"
                if not fuente.activa:
                    header += " · _(inactiva)_"
                st.markdown(header)

                if not registros:
                    st.caption("Esta fuente todavía no se ha ejecutado nunca.")
                    continue

                cols = st.columns(4)
                cols[0].metric("Nuevas", _fmt_counter(summary.last_nuevas))
                cols[1].metric("Duplicadas", _fmt_counter(summary.last_duplicadas))
                cols[2].metric("Errores", _fmt_counter(summary.last_errores))
                cols[3].metric("Último tipo", summary.last_tipo or "—")

                st.caption(
                    f"Última ejecución: {_fmt(summary.last_run_at)} · "
                    f"Último scrape correcto: {_fmt(summary.last_successful_scrape_at)} · "
                    f"{reason}"
                )


def _render_recent_runs() -> None:
    st.subheader(f"Últimas {RECENT_RUNS_LIMIT} ejecuciones (todas las fuentes)")
    with Session(engine) as session:
        recientes = RegistroEjecucionCRUD.get_recent(session, limit=RECENT_RUNS_LIMIT)
        nombres = {f.id: f.nombre for f in FuenteCRUD.get_all(session)}

    if not recientes:
        st.info("No hay ninguna ejecución registrada todavía.")
        return

    filas = [
        {
            "fecha": _fmt(r.fecha),
            "fuente": nombres.get(r.fuente_id, f"#{r.fuente_id}"),
            "tipo": r.tipo,
            "nuevas": _fmt_counter(r.nuevas),
            "duplicadas": _fmt_counter(r.duplicadas),
            "errores": r.errores,
            "total": r.total,
            "run_id": r.run_id or "—",
        }
        for r in recientes
    ]
    st.dataframe(filas, use_container_width=True, hide_index=True)


def main() -> None:
    now = datetime.utcnow()
    with Session(engine) as session:
        fuentes = FuenteCRUD.get_all(session)
    _render_fuente_health(fuentes, now)
    st.divider()
    _render_recent_runs()


main()

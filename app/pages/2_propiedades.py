"""Página de visualización y filtrado de propiedades con tarjetas."""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, UTC
from sqlmodel import Session, select
from sqlalchemy import func, distinct, or_, update as sa_update
import math

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine, PropiedadCRUD
from db.models import Propiedad, PrecioHistorico
from utils.calculadora import (
    calcular_compraventa,
    calcular_gastos_hipoteca,
    calcular_aportacion_necesaria,
    calcular_hipoteca,
)

st.set_page_config(page_title="Propiedades", page_icon="🏘️", layout="wide")


def _get_or_create_fuente_manual(session) -> int:
    from sqlmodel import select
    from db.models import Fuente
    fuente = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
    if not fuente:
        fuente = Fuente(
            nombre="Manual",
            url="manual://manual",
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas='{"detail_scraper_type": "manual_auto"}',
        )
        session.add(fuente)
        session.commit()
        session.refresh(fuente)
    return fuente.id


@st.dialog("➕ Añadir propiedad por URL", width="large")
def add_url_dialog(session):
    """Dialog to add a property by URL with auto-extraction."""
    import asyncio
    import hashlib
    from urllib.parse import urlparse
    from datetime import datetime
    from scraper.url_extractor import extract_from_url
    from db.models import Propiedad, PrecioHistorico

    # Initialize state
    if "add_url_extracted" not in st.session_state:
        st.session_state["add_url_extracted"] = {}
    if "add_url_value" not in st.session_state:
        st.session_state["add_url_value"] = ""

    extracted = st.session_state["add_url_extracted"]

    # Step 1: URL input
    url = st.text_input("URL de la propiedad", value=st.session_state["add_url_value"], placeholder="https://mbfinca.com/inmueble/...")
    st.session_state["add_url_value"] = url

    if st.button("🔍 Extraer datos", disabled=not url.strip()):
        with st.spinner("Extrayendo datos..."):
            data = asyncio.run(extract_from_url(url.strip()))
        if "error" in data:
            st.error(f"No se pudo extraer: {data['error']}")
            st.session_state["add_url_extracted"] = {}
        else:
            st.session_state["add_url_extracted"] = data
            extracted = data

    st.divider()

    # Step 2: Form (always shown, pre-filled if extracted)
    titulo = st.text_input("Título", value=extracted.get("titulo", ""))
    precio = st.number_input("Precio (€) *", min_value=0, value=int(extracted.get("precio") or 0), step=1000)
    col1, col2, col3 = st.columns(3)
    with col1:
        superficie = st.number_input("Superficie m²", min_value=0, value=int(extracted.get("superficie_m2") or 0), step=1)
    with col2:
        habitaciones = st.number_input("Habitaciones", min_value=0, value=int(extracted.get("habitaciones") or 0), step=1)
    with col3:
        banos = st.number_input("Baños", min_value=0, value=int(extracted.get("banos") or 0), step=1)
    municipio = st.text_input("Municipio", value=extracted.get("municipio") or "El Puerto de Santa María")
    tipo_propiedad = st.selectbox("Tipo de propiedad", ["piso", "casa", "chalet", "otro"])
    notas_campo = st.text_area("Notas", value="")

    if not precio:
        st.warning("El precio es obligatorio para guardar.")

    if st.button("💾 Guardar", disabled=not precio or not url.strip()):
        try:
            hash_unico = hashlib.sha256(url.strip().encode()).hexdigest()
            fuente_manual_id = _get_or_create_fuente_manual(session)
            propiedad = Propiedad(
                hash_unico=hash_unico,
                url_original=url.strip(),
                fuente_id=fuente_manual_id,
                origen_web=urlparse(url.strip()).netloc,
                titulo=titulo or url.strip(),
                precio=float(precio),
                superficie_m2=superficie or None,
                habitaciones=habitaciones or None,
                banos=banos or None,
                municipio=municipio or None,
                tipo_propiedad=tipo_propiedad,
                descripcion=notas_campo or None,
                activa=True,
                fecha_scraping=datetime.utcnow(),
            )
            session.add(propiedad)
            session.commit()
            session.refresh(propiedad)
            if propiedad.precio:
                session.add(PrecioHistorico(propiedad_id=propiedad.id, precio=propiedad.precio))
                session.commit()
            # Clear state
            st.session_state["add_url_extracted"] = {}
            st.session_state["add_url_value"] = ""
            st.success(f"✅ Propiedad guardada: {propiedad.titulo[:50]}")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")


# Initialize session state
if "current_page" not in st.session_state:
    st.session_state.current_page = 1
if "sort_by" not in st.session_state:
    st.session_state.sort_by = "Más reciente"
if "bulk_discard_confirm" not in st.session_state:
    st.session_state.bulk_discard_confirm = False

ITEMS_PER_PAGE = 12

SORT_OPTIONS = {
    "Más reciente": ("fecha_scraping", "desc"),
    "Más antiguo": ("fecha_scraping", "asc"),
    "Precio (menor)": ("precio", "asc"),
    "Precio (mayor)": ("precio", "desc"),
    "m² (mayor)": ("superficie_m2", "desc"),
}


@st.dialog("✏️ Editar propiedad", width="large")
def edit_property_dialog(prop):
    """Modal de edición de propiedad."""
    st.caption(f"🔗 {prop.url_original[:80]}...")

    tab_basic, tab_location, tab_features, tab_extra, tab_history = st.tabs(
        ["📋 Básico", "📍 Ubicación", "✨ Características", "💰 Económico", "📈 Historial"]
    )

    with tab_basic:
        titulo = st.text_input("Título", value=prop.titulo or "")
        col1, col2 = st.columns(2)
        with col1:
            precio = st.number_input("Precio (€)", value=float(prop.precio or 0), step=1000.0, min_value=0.0)
            superficie_m2 = st.number_input("Superficie total (m²)", value=float(prop.superficie_m2 or 0), step=1.0, min_value=0.0)
            habitaciones = st.number_input("Habitaciones", value=int(prop.habitaciones or 0), step=1, min_value=0)
        with col2:
            precio_anterior = st.number_input("Precio anterior (€)", value=float(prop.precio_anterior or 0), step=1000.0, min_value=0.0)
            superficie_util_m2 = st.number_input("Superficie útil (m²)", value=float(prop.superficie_util_m2 or 0), step=1.0, min_value=0.0)
            banos = st.number_input("Baños", value=int(prop.banos or 0), step=1, min_value=0)

        col3, col4 = st.columns(2)
        with col3:
            tipo_propiedad = st.text_input("Tipo de propiedad", value=prop.tipo_propiedad or "")
        with col4:
            estado = st.text_input("Estado", value=prop.estado or "")

        descripcion = st.text_area("Descripción", value=prop.descripcion or "", height=120)

    with tab_location:
        col1, col2 = st.columns(2)
        with col1:
            direccion = st.text_input("Dirección", value=prop.direccion or "")
            barrio = st.text_input("Barrio / Zona", value=prop.barrio or "")
            municipio = st.text_input("Municipio", value=prop.municipio or "")
        with col2:
            codigo_postal = st.text_input("Código postal", value=prop.codigo_postal or "")
            distrito = st.text_input("Distrito", value=prop.distrito or "")
            provincia = st.text_input("Provincia", value=prop.provincia or "")

    with tab_features:
        col1, col2, col3 = st.columns(3)
        with col1:
            ascensor = st.checkbox("Ascensor", value=bool(prop.ascensor))
            garaje = st.checkbox("Garaje", value=bool(prop.garaje))
            trastero = st.checkbox("Trastero", value=bool(prop.trastero))
        with col2:
            terraza = st.checkbox("Terraza", value=bool(prop.terraza))
            balcon = st.checkbox("Balcón", value=bool(prop.balcon))
            patio = st.checkbox("Patio", value=bool(prop.patio))
        with col3:
            piscina = st.checkbox("Piscina", value=bool(prop.piscina))
            aire_acondicionado = st.checkbox("Aire acondicionado", value=bool(prop.aire_acondicionado))
            amueblado = st.checkbox("Amueblado", value=bool(prop.amueblado))
            mascotas = st.checkbox("Mascotas", value=bool(prop.mascotas))

        col4, col5 = st.columns(2)
        with col4:
            planta = st.number_input("Planta", value=int(prop.planta or 0), step=1, min_value=0)
        with col5:
            certificado_energetico = st.selectbox(
                "Certificado energético",
                ["", "A", "B", "C", "D", "E", "F", "G", "En trámite"],
                index=["", "A", "B", "C", "D", "E", "F", "G", "En trámite"].index(prop.certificado_energetico or "")
                if prop.certificado_energetico in ["A", "B", "C", "D", "E", "F", "G", "En trámite"] else 0
            )

    with tab_extra:
        col1, col2 = st.columns(2)
        with col1:
            precio_comunidad = st.number_input("Gastos comunidad (€/mes)", value=float(prop.precio_comunidad or 0), step=10.0, min_value=0.0)
        with col2:
            precio_ibi = st.number_input("IBI (€/año)", value=float(prop.precio_ibi or 0), step=10.0, min_value=0.0)

    with tab_history:
        with Session(engine) as hsession:
            registros = hsession.exec(
                select(PrecioHistorico)
                .where(PrecioHistorico.propiedad_id == prop.id)
                .order_by(PrecioHistorico.fecha.asc())
            ).all()

        if not registros:
            st.info("Sin historial de precios todavía. Se registrará automáticamente en el próximo scraping.")
        else:
            import pandas as pd
            df = pd.DataFrame([{"Fecha": r.fecha, "Precio (€)": r.precio} for r in registros])
            df["Fecha"] = pd.to_datetime(df["Fecha"])
            df = df.set_index("Fecha")

            precio_min = df["Precio (€)"].min()
            precio_max = df["Precio (€)"].max()
            bajada = precio_max - precio_min

            col1, col2, col3 = st.columns(3)
            col1.metric("Precio actual", f"€{registros[-1].precio:,.0f}")
            col2.metric("Precio inicial", f"€{registros[0].precio:,.0f}")
            col3.metric("Bajada máxima", f"-€{bajada:,.0f}" if bajada > 0 else "Sin bajadas")

            st.line_chart(df, y="Precio (€)")

            with st.expander("📋 Tabla completa"):
                for r in reversed(registros):
                    st.caption(f"{r.fecha.strftime('%Y-%m-%d %H:%M')} — €{r.precio:,.0f}")

    st.divider()
    col_save, col_cancel = st.columns([1, 1])
    with col_save:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
            with Session(engine) as session:
                PropiedadCRUD.update(session, prop.id,
                    titulo=titulo or prop.titulo,
                    precio=precio if precio > 0 else None,
                    precio_anterior=precio_anterior if precio_anterior > 0 else None,
                    superficie_m2=superficie_m2 if superficie_m2 > 0 else None,
                    superficie_util_m2=superficie_util_m2 if superficie_util_m2 > 0 else None,
                    habitaciones=habitaciones if habitaciones > 0 else None,
                    banos=banos if banos > 0 else None,
                    tipo_propiedad=tipo_propiedad or None,
                    estado=estado or None,
                    descripcion=descripcion or None,
                    direccion=direccion or None,
                    barrio=barrio or None,
                    distrito=distrito or None,
                    municipio=municipio or None,
                    provincia=provincia or None,
                    codigo_postal=codigo_postal or None,
                    ascensor=ascensor,
                    garaje=garaje,
                    trastero=trastero,
                    terraza=terraza,
                    balcon=balcon,
                    patio=patio,
                    piscina=piscina,
                    aire_acondicionado=aire_acondicionado,
                    amueblado=amueblado,
                    mascotas=mascotas,
                    planta=planta if planta > 0 else None,
                    certificado_energetico=certificado_energetico or None,
                    precio_comunidad=precio_comunidad if precio_comunidad > 0 else None,
                    precio_ibi=precio_ibi if precio_ibi > 0 else None,
                )
            st.success("✅ Guardado")
            st.rerun()
    with col_cancel:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()


@st.dialog("🧮 Calculadora", width="large")
def calculadora_modal(prop):
    """Modal de calculadora financiera pre-rellenada con el precio de la propiedad."""
    precio_default = float(prop.precio or 200_000)
    st.caption(f"📍 {prop.titulo[:70]}")

    precio = st.number_input("Precio (€)", min_value=0.0, value=precio_default, step=5_000.0, format="%.0f")
    itp_pct = st.selectbox("ITP", options=[3.5, 6.0, 7.0], index=2, format_func=lambda v: f"{v}%")

    col1, col2, col3 = st.columns(3)
    with col1:
        notaria = st.number_input("Notaría (€)", min_value=0.0, value=700.0, step=50.0, format="%.0f")
    with col2:
        registro = st.number_input("Registro (€)", min_value=0.0, value=350.0, step=50.0, format="%.0f")
    with col3:
        agencia_pct = st.number_input("Agencia (%)", min_value=0.0, value=0.0, step=0.5, format="%.1f")

    st.subheader("B) Gastos hipotecarios")
    col1, col2, col3 = st.columns(3)
    with col1:
        gestoria = st.number_input("Gestoría (€)", min_value=0.0, value=350.0, step=50.0, format="%.0f")
        comision_apertura = st.number_input("Comisión apertura (€)", min_value=0.0, value=0.0, step=100.0, format="%.0f")
    with col2:
        tasacion = st.number_input("Tasación (€)", min_value=0.0, value=450.0, step=50.0, format="%.0f")
        registro_hip = st.number_input("Registro hipoteca (€)", min_value=0.0, value=0.0, step=50.0, format="%.0f")
    with col3:
        ajd_pct = st.number_input("AJD (%)", min_value=0.0, value=1.0, step=0.1, format="%.1f")

    st.subheader("💰 Financiación")
    modo = st.radio("Modo aportación", ["Manual", "80%", "90%", "100%"], horizontal=True, key=f"modo_modal_{prop.id}")

    st.subheader("🏦 Hipoteca")
    col1, col2 = st.columns(2)
    with col1:
        tipo_base = st.number_input("Tipo base (%)", min_value=0.0, value=3.0, step=0.1, format="%.2f", key=f"tipo_modal_{prop.id}")
    with col2:
        plazo_anos = st.slider("Plazo (años)", 5, 40, 30, key=f"plazo_modal_{prop.id}")

    bonificaciones_modal = st.data_editor(
        [{"Concepto": "", "Reducción (%)": 0.25}],
        num_rows="dynamic",
        use_container_width=True,
        key=f"bon_modal_{prop.id}",
    )
    total_bonificacion = sum(r.get("Reducción (%)", 0) for r in bonificaciones_modal if r.get("Reducción (%)"))
    tipo_final = max(tipo_base - total_bonificacion, 0.0)

    # Cálculos
    gastos_a = calcular_compraventa(precio, itp_pct, notaria, registro, agencia_pct)
    total_a = gastos_a["total_a"]

    financiacion_map = {"Manual": None, "80%": 80.0, "90%": 90.0, "100%": 100.0}
    financiacion_pct = financiacion_map[modo]

    if financiacion_pct is not None:
        prestamo_calculado = round(precio * financiacion_pct / 100, 2)
    else:
        prestamo_calculado = precio  # placeholder

    gastos_b = calcular_gastos_hipoteca(prestamo_calculado, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct)
    total_b = gastos_b["total_b"]

    if financiacion_pct is not None:
        aportacion = calcular_aportacion_necesaria(precio, financiacion_pct, total_a, total_b)
        prestamo_calculado = round(precio * financiacion_pct / 100, 2)
    else:
        aportacion = st.number_input("Aportación inicial (€)", min_value=0.0, value=precio * 0.2, step=1_000.0, format="%.0f", key=f"aport_modal_{prop.id}")
        prestamo_calculado = max(precio + total_a + total_b - aportacion, 0.0)
        gastos_b = calcular_gastos_hipoteca(prestamo_calculado, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct)
        total_b = gastos_b["total_b"]

    coste_total = precio + total_a + total_b
    hip = calcular_hipoteca(prestamo_calculado, tipo_final, plazo_anos) if prestamo_calculado > 0 else None

    st.divider()
    st.subheader("📊 Resumen")

    if financiacion_pct is not None:
        st.info(f"💰 Con financiación del **{financiacion_pct:.0f}%**, necesitas al menos **€{aportacion:,.0f}** de ahorros")

    col1, col2, col3 = st.columns(3)
    col1.metric("Gastos A+B", f"€{total_a + total_b:,.0f}")
    col2.metric("Coste total", f"€{coste_total:,.0f}")
    col3.metric("Préstamo", f"€{prestamo_calculado:,.0f}")

    if hip:
        st.metric("📅 Cuota mensual", f"€{hip['cuota_mensual']:,.2f}",
                  help=f"Tipo {tipo_final:.2f}% · {plazo_anos} años")
        c1, c2 = st.columns(2)
        c1.metric("Total pagado", f"€{hip['total_pagado']:,.0f}")
        c2.metric("Total intereses", f"€{hip['total_intereses']:,.0f} ({hip['pct_intereses']:.1f}%)")


@st.dialog("📸 Fotos", width="large")
def fotos_dialog(prop):
    fotos = prop.fotos or []
    if not fotos:
        st.info("Esta propiedad no tiene fotos.")
        return

    key = f"foto_idx_{prop.id}"
    if key not in st.session_state:
        st.session_state[key] = 0

    idx = st.session_state[key]
    total = len(fotos)

    st.caption(f"Foto {idx + 1} de {total}")
    st.image(fotos[idx], use_container_width=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← Anterior", key=f"foto_prev_{prop.id}", use_container_width=True):
            st.session_state[key] = (idx - 1) % total
    with col_next:
        if st.button("Siguiente →", key=f"foto_next_{prop.id}", use_container_width=True):
            st.session_state[key] = (idx + 1) % total


def render_property_card(prop):
    """Renderizar tarjeta de propiedad con HTML/Markdown."""
    with st.container(border=True):
        # Header
        col_title, col_actions = st.columns([4, 1])

        with col_title:
            titulo_display = prop.titulo[:70] if prop.titulo else 'Sin título'
            if not prop.activa:
                titulo_display = f"~~{titulo_display}~~ 🚫 {prop.estado or 'Vendida'}"
            st.markdown(f"### {titulo_display}")

        with col_actions:
            # Favorite button
            fav_btn = st.button(
                "❤️" if prop.favorita else "🤍",
                key=f"fav_{prop.id}",
                help="Favorita"
            )
            if fav_btn:
                with Session(engine) as session:
                    PropiedadCRUD.toggle_favorite(session, prop.id)
                st.rerun()

        # Info row 1: Price, Size, Rooms
        col_p, col_m, col_h = st.columns(3)
        with col_p:
            if prop.precio:
                st.caption(f"💰 **€{prop.precio:,.0f}**")
            else:
                st.caption("💰 Precio N/A")

        with col_m:
            if prop.superficie_m2:
                st.caption(f"📐 **{prop.superficie_m2:.0f}m²**")
            else:
                st.caption("📐 Tamaño N/A")

        with col_h:
            if prop.habitaciones:
                st.caption(f"🛏️ **{prop.habitaciones} hab**")
            else:
                st.caption("🛏️ Hab N/A")

        # Info row 2: Location
        location = []
        if prop.barrio:
            location.append(prop.barrio)
        if prop.distrito:
            location.append(prop.distrito)
        if location:
            st.caption(f"📍 {', '.join(location)}")

        # Info row 3: Meta
        meta = []
        if prop.origen_web:
            meta.append(f"🌐 {prop.origen_web}")
        if prop.fecha_scraping:
            days = (datetime.now(UTC).replace(tzinfo=None) - prop.fecha_scraping).days
            if days == 0:
                meta.append("Hoy")
            else:
                meta.append(f"{days}d atrás")
        if meta:
            st.caption(" • ".join(meta))

        # Manual badge
        fuente_manual_id = st.session_state.get("fuente_manual_id")
        if fuente_manual_id and prop.fuente_id == fuente_manual_id:
            st.caption("📌 Manual")

        # Expandable details
        with st.expander("📖 Detalles"):
            col_d1, col_d2 = st.columns(2)

            with col_d1:
                st.markdown("**📍 UBICACIÓN**")
                if prop.direccion:
                    st.caption(f"Dirección: {prop.direccion}")
                if prop.codigo_postal:
                    st.caption(f"CP: {prop.codigo_postal}")
                if prop.municipio:
                    st.caption(f"Municipio: {prop.municipio}")

                st.markdown("**🏠 CARACTERÍSTICAS**")
                if prop.tipo_propiedad:
                    st.caption(f"Tipo: {prop.tipo_propiedad}")
                if prop.estado:
                    st.caption(f"Estado: {prop.estado}")
                if prop.superficie_util_m2:
                    st.caption(f"Sup. útil: {prop.superficie_util_m2}m²")

            with col_d2:
                st.markdown("**✨ SERVICIOS**")
                services = []
                if prop.ascensor:
                    services.append("✓ Ascensor")
                if prop.garaje:
                    services.append("✓ Garaje")
                if prop.terraza:
                    services.append("✓ Terraza")
                if prop.balcon:
                    services.append("✓ Balcón")
                if prop.piscina:
                    services.append("✓ Piscina")
                if prop.aire_acondicionado:
                    services.append("✓ A/C")
                if prop.mascotas:
                    services.append("✓ Mascotas")

                for svc in services:
                    st.caption(svc)

                if not services:
                    st.caption("(Sin información)")

                st.markdown("**💵 PRECIOS**")
                if prop.precio_comunidad:
                    st.caption(f"Comunidad: €{prop.precio_comunidad}/mes")
                if prop.precio_ibi:
                    st.caption(f"IBI: €{prop.precio_ibi}/año")

        # Action buttons
        col_btn1, col_btn2, col_btn3, col_btn4, col_btn5, col_btn6 = st.columns(6)

        with col_btn1:
            view_btn = st.button(
                "👁 Visto" if prop.vista else "👁",
                key=f"view_{prop.id}",
                use_container_width=True,
                type="secondary"
            )
            if view_btn:
                with Session(engine) as session:
                    PropiedadCRUD.mark_as_viewed(session, prop.id)
                st.rerun()

        with col_btn2:
            if st.button("✏️", key=f"edit_{prop.id}", use_container_width=True):
                edit_property_dialog(prop)

        with col_btn3:
            if st.button("🧮", key=f"calc_{prop.id}", use_container_width=True, help="Calcular gastos e hipoteca"):
                calculadora_modal(prop)

        with col_btn4:
            if prop.fotos:
                if st.button("📸", key=f"fotos_{prop.id}", use_container_width=True, help="Ver fotos"):
                    st.session_state[f"foto_idx_{prop.id}"] = 0
                    fotos_dialog(prop)

        with col_btn5:
            st.link_button(
                "🔗",
                prop.url_original,
                use_container_width=True
            )

        with col_btn6:
            discard_btn = st.button(
                "❌ Descartado" if prop.descartada else "❌",
                key=f"discard_{prop.id}",
                use_container_width=True,
                type="secondary"
            )
            if discard_btn:
                with Session(engine) as session:
                    PropiedadCRUD.mark_as_discarded(session, prop.id)
                st.rerun()


try:
    with Session(engine) as session:
        # Get stats
        total = session.exec(select(func.count(Propiedad.id))).first() or 0

        st.title("🏘️ Propiedades")
        st.write(f"📊 Total: **{total}** propiedades")

        if total == 0:
            st.warning("No hay propiedades")
            st.stop()

        # Initialize fuente_manual_id in session state for card badges
        if "fuente_manual_id" not in st.session_state:
            st.session_state["fuente_manual_id"] = _get_or_create_fuente_manual(session)

        # SIDEBAR FILTERS
        with st.sidebar:
            if st.sidebar.button("➕ Añadir URL", use_container_width=True):
                add_url_dialog(session)
            st.sidebar.divider()

            st.title("🔍 Filtros")

            # Stats
            with st.expander("📊 Estadísticas"):
                viewed = session.exec(select(func.count(Propiedad.id)).where(Propiedad.vista == True)).first() or 0
                discarded = session.exec(select(func.count(Propiedad.id)).where(Propiedad.descartada == True)).first() or 0
                favorites = session.exec(select(func.count(Propiedad.id)).where(Propiedad.favorita == True)).first() or 0

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("👁 Vistas", viewed)
                    st.metric("❤️ Favoritas", favorites)
                with col2:
                    st.metric("❌ Descartadas", discarded)

            st.divider()

            # BASIC FILTERS
            st.subheader("💰 Precio")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                precio_min = st.number_input("Mín (€)", value=0, step=50000)
            with col_p2:
                precio_max = st.number_input("Máx (€)", value=1000000, step=50000)

            st.subheader("📐 Superficie")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                m2_min = st.number_input("Mín (m²)", value=0, step=10)
            with col_m2:
                m2_max = st.number_input("Máx (m²)", value=10000, step=50)

            st.subheader("🏠 Habitaciones")
            hab_min = st.slider("Mínimo", 0, 10, 0)

            st.subheader("🚿 Baños")
            banos_min = st.slider("Mínimo", 0, 5, 0)

            st.divider()

            # ADVANCED FILTERS
            st.subheader("🔧 Avanzados")

            tipos = session.exec(
                select(distinct(Propiedad.tipo_propiedad))
                .where(Propiedad.tipo_propiedad != None)
                .limit(50)
            ).all()
            tipo_filter = st.multiselect("Tipo", sorted([t for t in tipos if t]))

            distritos = session.exec(
                select(distinct(Propiedad.distrito))
                .where(Propiedad.distrito != None)
                .limit(50)
            ).all()
            distrito_filter = st.multiselect("Distrito", sorted([d for d in distritos if d]))

            estados = session.exec(
                select(distinct(Propiedad.estado))
                .where(Propiedad.estado != None)
                .limit(50)
            ).all()
            estado_filter = st.multiselect("Estado", sorted([e for e in estados if e]))

            st.subheader("✨ Características")
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                filter_ascensor = st.checkbox("Ascensor")
                filter_garaje = st.checkbox("Garaje")
            with col_c2:
                filter_terraza = st.checkbox("Terraza")
                filter_balcon = st.checkbox("Balcón")
            with col_c3:
                filter_piscina = st.checkbox("Piscina")
                filter_aire = st.checkbox("Aire acondi.")

            st.divider()

            # TEXT SEARCH
            st.subheader("🔎 Búsqueda")
            search_text = st.text_input("Buscar en título/descripción")

            st.divider()

            # VISIBILITY TOGGLES
            st.subheader("👁️ Ver")
            show_viewed = st.checkbox("Vistas", value=True)
            show_discarded = st.checkbox("Descartadas", value=False)
            show_vendidas = st.checkbox("Vendidas", value=False)

            st.divider()

            # SORTING
            st.subheader("📊 Ordenar")
            sort_by = st.selectbox("Ordenar por", list(SORT_OPTIONS.keys()), index=list(SORT_OPTIONS.keys()).index(st.session_state.sort_by))
            st.session_state.sort_by = sort_by

            st.divider()

            # BULK DISCARD
            st.subheader("🗑️ Descarte masivo")

            bulk_id_stmt = select(Propiedad.id).where(
                Propiedad.activa == True,
                Propiedad.descartada == False,
            )
            if precio_min > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.precio >= precio_min, Propiedad.precio == None))
            if precio_max > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.precio <= precio_max, Propiedad.precio == None))
            if m2_min > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.superficie_m2 >= m2_min, Propiedad.superficie_m2 == None))
            if m2_max > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.superficie_m2 <= m2_max, Propiedad.superficie_m2 == None))
            if hab_min > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.habitaciones >= hab_min, Propiedad.habitaciones == None))
            if banos_min > 0:
                bulk_id_stmt = bulk_id_stmt.where(or_(Propiedad.banos >= banos_min, Propiedad.banos == None))
            if tipo_filter:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.tipo_propiedad.in_(tipo_filter))
            if distrito_filter:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.distrito.in_(distrito_filter))
            if estado_filter:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.estado.in_(estado_filter))
            if filter_ascensor:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.ascensor == True)
            if filter_garaje:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.garaje == True)
            if filter_terraza:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.terraza == True)
            if filter_balcon:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.balcon == True)
            if filter_piscina:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.piscina == True)
            if filter_aire:
                bulk_id_stmt = bulk_id_stmt.where(Propiedad.aire_acondicionado == True)
            if search_text:
                search_bulk = f"%{search_text}%"
                bulk_id_stmt = bulk_id_stmt.where(
                    (Propiedad.titulo.ilike(search_bulk)) | (Propiedad.descripcion.ilike(search_bulk))
                )

            bulk_ids = session.exec(bulk_id_stmt).all()
            bulk_count = len(bulk_ids)

            if bulk_count > 0:
                st.caption(f"{bulk_count} propiedades activas sin descartar coinciden con los filtros")
                if not st.session_state.bulk_discard_confirm:
                    if st.button(f"🗑️ Descartar todas ({bulk_count})", use_container_width=True):
                        st.session_state.bulk_discard_confirm = True
                        st.rerun()
                else:
                    st.warning(f"⚠️ ¿Marcar {bulk_count} propiedades como descartadas?")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("✅ Sí, descartar", type="primary", use_container_width=True, key="bulk_confirm_yes"):
                            with Session(engine) as bulk_session:
                                bulk_session.execute(
                                    sa_update(Propiedad)
                                    .where(Propiedad.id.in_(bulk_ids))
                                    .values(descartada=True)
                                )
                                bulk_session.commit()
                            st.session_state.bulk_discard_confirm = False
                            st.success(f"✅ {bulk_count} descartadas")
                            st.rerun()
                    with col_no:
                        if st.button("❌ Cancelar", use_container_width=True, key="bulk_confirm_no"):
                            st.session_state.bulk_discard_confirm = False
                            st.rerun()
            else:
                st.caption("Ninguna propiedad activa sin descartar con el filtro actual")

            st.divider()

            # SOLD VERIFICATION
            st.subheader("🔍 Verificar vendidas")
            active_count = session.exec(
                select(func.count(Propiedad.id)).where(Propiedad.activa == True)
            ).first() or 0
            st.caption(f"{active_count} propiedades activas a verificar")
            st.caption("Descarga cada ficha y marca como vendidas las que estén reservadas o vendidas.")
            if st.button("🔍 Verificar ahora", use_container_width=True, key="verify_sold_btn"):
                import asyncio
                from scraper.sold_checker import check_sold_properties as _check_sold
                with st.spinner(f"Verificando {active_count} propiedades... (puede tardar varios minutos)"):
                    with Session(engine) as verify_session:
                        sold_stats = asyncio.run(_check_sold(verify_session))
                vendidas_n = sold_stats.get("vendidas", 0)
                errores_n = sold_stats.get("errores", 0)
                st.success(f"✅ Completado — {vendidas_n} vendidas, {errores_n} errores")
                st.rerun()

        # BUILD QUERY
        stmt = select(Propiedad)
        if not show_vendidas:
            stmt = stmt.where(Propiedad.activa == True)

        if precio_min > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.precio >= precio_min,
                    Propiedad.precio == None
                )
            )
        if precio_max > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.precio <= precio_max,
                    Propiedad.precio == None
                )
            )
        if m2_min > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.superficie_m2 >= m2_min,
                    Propiedad.superficie_m2 == None
                )
            )
        if m2_max > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.superficie_m2 <= m2_max,
                    Propiedad.superficie_m2 == None
                )
            )
        # For numeric filters, include both matching values AND NULLs (unknown)
        if hab_min > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.habitaciones >= hab_min,
                    Propiedad.habitaciones == None
                )
            )
        if banos_min > 0:
            stmt = stmt.where(
                or_(
                    Propiedad.banos >= banos_min,
                    Propiedad.banos == None
                )
            )

        if tipo_filter:
            stmt = stmt.where(Propiedad.tipo_propiedad.in_(tipo_filter))
        if distrito_filter:
            stmt = stmt.where(Propiedad.distrito.in_(distrito_filter))
        if estado_filter:
            stmt = stmt.where(Propiedad.estado.in_(estado_filter))

        if filter_ascensor:
            stmt = stmt.where(Propiedad.ascensor == True)
        if filter_garaje:
            stmt = stmt.where(Propiedad.garaje == True)
        if filter_terraza:
            stmt = stmt.where(Propiedad.terraza == True)
        if filter_balcon:
            stmt = stmt.where(Propiedad.balcon == True)
        if filter_piscina:
            stmt = stmt.where(Propiedad.piscina == True)
        if filter_aire:
            stmt = stmt.where(Propiedad.aire_acondicionado == True)

        if search_text:
            search = f"%{search_text}%"
            stmt = stmt.where(
                (Propiedad.titulo.ilike(search)) |
                (Propiedad.descripcion.ilike(search))
            )

        if not show_viewed:
            stmt = stmt.where(Propiedad.vista == False)
        if not show_discarded:
            stmt = stmt.where(Propiedad.descartada == False)

        # APPLY SORTING
        sort_field, sort_order = SORT_OPTIONS[st.session_state.sort_by]
        if sort_order == "desc":
            stmt = stmt.order_by(getattr(Propiedad, sort_field).desc())
        else:
            stmt = stmt.order_by(getattr(Propiedad, sort_field).asc())

        # LIMIT & EXECUTE
        stmt = stmt.limit(300)
        propiedades = session.exec(stmt).all()

        if not propiedades:
            st.warning("❌ No hay propiedades con esos filtros")
            st.stop()

        # PAGINATION
        total_filtered = len(propiedades)
        total_pages = math.ceil(total_filtered / ITEMS_PER_PAGE)

        col_info, col_page = st.columns([2, 1])
        with col_info:
            st.write(f"📊 **{total_filtered}** propiedades encontradas | Página **{st.session_state.current_page}** de **{total_pages}**")
        with col_page:
            page = st.number_input("Ir a página", 1, total_pages, st.session_state.current_page)
            st.session_state.current_page = page

        # GET PAGE ITEMS
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_items = propiedades[start:end]

        st.divider()

        # RENDER CARDS (3 columns)
        cols = st.columns(3)
        for idx, prop in enumerate(page_items):
            with cols[idx % 3]:
                render_property_card(prop)

        st.divider()

        # PAGINATION INFO
        st.caption(f"Página {page} de {total_pages} • {total_filtered} propiedades totales")

except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

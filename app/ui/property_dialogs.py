"""Modales de la página Propiedades: editar, calculadora, fotos y añadir por URL.

Código movido desde app/pages/2_propiedades.py sin cambios funcionales,
salvo add_url_dialog, que ahora abre su propia sesión de BD.
"""

import html as html_lib

import streamlit as st
from sqlmodel import Session, select

from db.database import engine, PropiedadCRUD, PrecioHistoricoCRUD
from db.models import Propiedad, PrecioHistorico
from listing_date import es_candidato_backfill
from utils.calculadora import (
    calcular_compraventa,
    calcular_gastos_hipoteca,
    calcular_aportacion_necesaria,
    calcular_hipoteca,
)


def get_or_create_fuente_manual(session) -> int:
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
def add_url_dialog(on_write=None):
    """Dialog to add a property by URL with auto-extraction."""
    import asyncio
    import hashlib
    from urllib.parse import urlparse
    from datetime import datetime
    from scraper.url_extractor import extract_from_url

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
            with Session(engine) as session:
                fuente_manual_id = get_or_create_fuente_manual(session)
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
                titulo_guardado = propiedad.titulo[:50]
            st.session_state["add_url_extracted"] = {}
            st.session_state["add_url_value"] = ""
            st.success(f"✅ Propiedad guardada: {titulo_guardado}")
            if on_write:
                on_write()
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")


@st.dialog("✏️ Editar propiedad", width="large")
def edit_property_dialog(prop, on_write=None):
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

        st.divider()
        from datetime import date as _date
        from db.models import Fuente as _Fuente

        with Session(engine) as _fsession:
            _fuente = _fsession.get(_Fuente, prop.fuente_id)
        if _fuente and es_candidato_backfill(prop.fecha_scraping, _fuente.created_at):
            st.info(
                "📥 Esta propiedad parece proceder de una carga inicial (backfill) de la "
                "fuente — la fecha de scraping puede no reflejar la fecha real de publicación."
            )

        corregir_fecha = st.checkbox(
            "📅 Corregir fecha de publicación manualmente",
            value=prop.fecha_publicacion is not None,
        )
        if corregir_fecha:
            fecha_inicial = (prop.fecha_publicacion or prop.fecha_scraping).date()
            fecha_publicacion_date = st.date_input(
                "Fecha de publicación real", value=fecha_inicial, max_value=_date.today()
            )
        else:
            fecha_publicacion_date = None
            st.caption(
                f"Sin corregir — se usa la fecha de scraping "
                f"({prop.fecha_scraping.strftime('%Y-%m-%d')}) como fecha de publicación efectiva."
            )

    with tab_location:
        from scraper.zona_normalizer import cargar_catalogo
        catalogo = cargar_catalogo()
        zonas_canonicas = sorted(catalogo.keys())
        opciones_zona = ["(Sin zona)"] + zonas_canonicas

        col1, col2 = st.columns(2)
        with col1:
            direccion = st.text_input("Dirección", value=prop.direccion or "")
            barrio = st.text_input("Barrio / Zona", value=prop.barrio or "")
            municipio = st.text_input("Municipio", value=prop.municipio or "")
        with col2:
            codigo_postal = st.text_input("Código postal", value=prop.codigo_postal or "")
            distrito = st.text_input("Distrito", value=prop.distrito or "")
            provincia = st.text_input("Provincia", value=prop.provincia or "")

        # Zona canónica como desplegable
        zona_actual = prop.zona_normalizada or "(Sin zona)"
        zona_idx = opciones_zona.index(zona_actual) if zona_actual in opciones_zona else 0
        zona_normalizada = st.selectbox(
            "🏷️ Zona canónica",
            options=opciones_zona,
            index=zona_idx,
            help="Zona normalizada del catálogo. Se usa en estadísticas y filtros de alertas.",
        )
        if zona_normalizada == "(Sin zona)":
            zona_normalizada = None

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
        from datetime import date, datetime

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
        st.subheader("➕ Añadir registro de precio")
        with st.form(key=f"add_historico_{prop.id}"):
            col_a, col_b = st.columns(2)
            with col_a:
                nuevo_precio = st.number_input(
                    "Precio (€)", min_value=0.0, step=1000.0, key=f"nuevo_precio_{prop.id}"
                )
            with col_b:
                nueva_fecha = st.date_input(
                    "Fecha", value=date.today(), max_value=date.today(), key=f"nueva_fecha_{prop.id}"
                )
            if st.form_submit_button("Añadir"):
                fecha_dt = datetime(nueva_fecha.year, nueva_fecha.month, nueva_fecha.day)
                es_valido, error = PrecioHistoricoCRUD.validar(nuevo_precio, fecha_dt)
                if not es_valido:
                    st.error(error)
                else:
                    with Session(engine) as hsession2:
                        PrecioHistoricoCRUD.add(
                            hsession2, propiedad_id=prop.id, precio=nuevo_precio, fecha=fecha_dt
                        )
                    st.success("✅ Registro añadido")
                    if on_write:
                        on_write()
                    st.rerun()

        if registros:
            st.subheader("✏️ Editar registro existente")
            opciones = {
                f"{r.fecha.strftime('%Y-%m-%d')} — €{r.precio:,.0f} (#{r.id})": r
                for r in reversed(registros)
            }
            seleccion_label = st.selectbox(
                "Selecciona un registro", list(opciones.keys()), key=f"editar_sel_{prop.id}"
            )
            registro_sel = opciones[seleccion_label]
            with st.form(key=f"edit_historico_{prop.id}"):
                col_a, col_b = st.columns(2)
                with col_a:
                    precio_editado = st.number_input(
                        "Precio (€)",
                        min_value=0.0,
                        value=float(registro_sel.precio),
                        step=1000.0,
                        key=f"precio_edit_{prop.id}",
                    )
                with col_b:
                    fecha_editada = st.date_input(
                        "Fecha",
                        value=registro_sel.fecha.date(),
                        max_value=date.today(),
                        key=f"fecha_edit_{prop.id}",
                    )
                if st.form_submit_button("Guardar edición"):
                    fecha_dt = datetime(fecha_editada.year, fecha_editada.month, fecha_editada.day)
                    es_valido, error = PrecioHistoricoCRUD.validar(precio_editado, fecha_dt)
                    if not es_valido:
                        st.error(error)
                    else:
                        with Session(engine) as hsession3:
                            PrecioHistoricoCRUD.update(
                                hsession3,
                                historico_id=registro_sel.id,
                                precio=precio_editado,
                                fecha=fecha_dt,
                            )
                        st.success("✅ Registro actualizado")
                        if on_write:
                            on_write()
                        st.rerun()

    st.divider()
    col_save, col_cancel = st.columns([1, 1])
    with col_save:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
            fecha_publicacion_dt = (
                datetime(fecha_publicacion_date.year, fecha_publicacion_date.month, fecha_publicacion_date.day)
                if corregir_fecha and fecha_publicacion_date
                else None
            )
            with Session(engine) as session:
                PropiedadCRUD.update(session, prop.id,
                    titulo=titulo or prop.titulo,
                    fecha_publicacion=fecha_publicacion_dt,
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
                    zona_normalizada=zona_normalizada,
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
            if on_write:
                on_write()
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
    st.markdown(
        f'<img src="{html_lib.escape(fotos[idx], quote=True)}" style="width:100%;max-height:420px;object-fit:contain;">',
        unsafe_allow_html=True,
    )

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← Anterior", key=f"foto_prev_{prop.id}", use_container_width=True):
            st.session_state[key] = (idx - 1) % total
    with col_next:
        if st.button("Siguiente →", key=f"foto_next_{prop.id}", use_container_width=True):
            st.session_state[key] = (idx + 1) % total


@st.dialog("🔍 Buscar fotos", width="large")
def buscar_fotos_dialog(prop, on_write=None):
    """Descarga la ficha, extrae imágenes y deja elegir cuáles guardar.

    Se previsualiza antes de guardar porque el extractor es genérico: en
    portales que sirven las fotos del anuncio y las del widget de
    'propiedades similares' desde la misma carpeta, no puede distinguirlas.
    """
    import asyncio

    from scraper.foto_extractor import obtener_fotos

    with st.spinner("Descargando la ficha…"):
        resultado = asyncio.run(obtener_fotos(prop.url_original))

    if "error" in resultado:
        st.error(f"No se pudo acceder a la ficha: {resultado['error']}")
        return

    fotos = resultado.get("fotos") or []
    if not fotos:
        st.warning("No se encontraron imágenes en esta ficha.")
        return

    if len(fotos) < 5:
        st.warning(
            f"Solo se han encontrado {len(fotos)} imágenes. "
            "Puede que este portal las cargue por JavaScript."
        )

    st.caption(f"{len(fotos)} imágenes encontradas. Desmarca las que no correspondan.")

    seleccion = []
    columnas = st.columns(4)
    for idx, foto in enumerate(fotos):
        with columnas[idx % 4]:
            st.markdown(
                f'<img src="{html_lib.escape(foto, quote=True)}" '
                f'style="width:100%;height:110px;object-fit:cover;border-radius:4px;">',
                unsafe_allow_html=True,
            )
            if st.checkbox("Usar", value=True, key=f"foto_sel_{prop.id}_{idx}"):
                seleccion.append(foto)

    st.divider()
    if st.button(
        f"💾 Guardar {len(seleccion)} fotos",
        type="primary",
        use_container_width=True,
        disabled=not seleccion,
        key=f"foto_save_{prop.id}",
    ):
        with Session(engine) as session:
            PropiedadCRUD.update(session, prop.id, fotos=seleccion)
        st.success(f"✅ Guardadas {len(seleccion)} fotos")
        if on_write:
            on_write()
        st.rerun()


@st.dialog("🏠 Visita a propiedad", width="medium")
def visita_dialog(prop, on_write=None):
    """Diálogo para registrar detalles de una visita a una propiedad."""
    # --- Estado inicial de los widgets (pueden ser None/False) ---
    estado_inicial = st.session_state.get(f"visita_inicial_{prop.id}")
    if estado_inicial is None:
        estado_inicial = {
            "visitada": bool(prop.visitada),
            "notas_visita": prop.notas_visita or "",
            "oferta_realizada": bool(prop.oferta_realizada),
            "precio_oferta": float(prop.precio_oferta or 0),
            "respuesta_oferta": prop.respuesta_oferta or "Pendiente",
        }
        st.session_state[f"visita_inicial_{prop.id}"] = estado_inicial

    # --- 1. Visitada ---
    visitada = st.checkbox(
        "He visitado esta propiedad",
        value=estado_inicial["visitada"],
        key=f"visita_{prop.id}_visitada",
        help="Marca si ya has visitado esta propiedad.",
    )

    if not visitada:
        st.caption("Marca la casilla para poder añadir los detalles de la visita y la oferta.")
        st.divider()
        if st.button("Cerrar", use_container_width=True):
            st.rerun()
        return

    st.divider()

    # --- 2. Notas de la visita ---
    notas_visita = st.text_area(
        "Notas de la visita",
        value=estado_inicial["notas_visita"],
        key=f"visita_{prop.id}_notas",
        placeholder="Ej: Buen estado, necesita reforma de cocina...",
        help="Apunta aquí todo lo que hayas observado durante la visita.",
    )

    st.divider()

    # --- 3. Oferta realizada ---
    oferta_realizada = st.checkbox(
        "Oferta realizada",
        value=estado_inicial["oferta_realizada"],
        key=f"visita_{prop.id}_oferta",
        help="Marca si has presentado una oferta por esta propiedad.",
    )

    if oferta_realizada:
        # --- 4. Precio de la oferta ---
        precio_oferta = st.number_input(
            "Precio de la oferta (€)",
            min_value=0.0,
            value=estado_inicial["precio_oferta"],
            step=1000.0,
            key=f"visita_{prop.id}_precio",
            help="Cantidad económica de tu oferta.",
        )

        # --- 5. Respuesta del vendedor ---
        respuesta_oferta = st.selectbox(
            "Respuesta del vendedor",
            options=["Pendiente", "Aceptada", "Rechazada", "Contrapropuesta"],
            index=["Pendiente", "Aceptada", "Rechazada", "Contrapropuesta"].index(estado_inicial["respuesta_oferta"])
            if estado_inicial["respuesta_oferta"] in ["Pendiente", "Aceptada", "Rechazada", "Contrapropuesta"] else 0,
            key=f"visita_{prop.id}_respuesta",
            help="¿Cómo ha respondido el vendedor a tu oferta?",
        )
    else:
        precio_oferta = None
        respuesta_oferta = None

    st.divider()

    # --- 6. Guardar ---
    if st.button("Guardar", type="primary", use_container_width=True):
        with Session(engine) as session:
            PropiedadCRUD.update(session, prop.id,
                visitada=visitada,
                notas_visita=notas_visita,
                oferta_realizada=oferta_realizada,
                precio_oferta=precio_oferta,
                respuesta_oferta=respuesta_oferta,
            )
        st.session_state.pop(f"visita_inicial_{prop.id}", None)
        if on_write:
            on_write()
        st.toast("✅ Visita guardada")
        st.rerun()

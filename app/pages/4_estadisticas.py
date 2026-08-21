"""Estadísticas 2.0: pulso del mercado, zonas y asistente de ofertas."""

import sys
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine, EstadisticaNotarialCRUD, PropiedadCRUD
from db.models import Propiedad, PrecioHistorico
from ui import market_stats as ms
from ui import notarial_stats as ns
from ui import offer_advisor as oa
from ui.chart_theme import PLOTLY_CONFIG, bar_chart, line_chart, offer_range_chart

st.set_page_config(page_title="Mercado", page_icon="📊", layout="wide")

TABS = {
    "pulso": "📈 Pulso", "zonas": "🗺️ Zonas", "ofertas": "🎯 Ofertas",
    "notarial": "🏛️ Notarial",
}
MAX_BARRIOS_GRAFICO = 8  # límite de la paleta categórica — nunca ciclar colores
_MESES_ABREV = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
               7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


# ── Fetches cacheados (dicts planos, nunca ORM) ───────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_props() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Propiedad)).all()
        return [{
            "id": p.id, "titulo": p.titulo, "precio": p.precio,
            "precio_anterior": p.precio_anterior, "superficie_m2": p.superficie_m2,
            "habitaciones": p.habitaciones, "tipo_propiedad": p.tipo_propiedad,
            "barrio": p.zona_normalizada or p.barrio,
            "municipio": p.municipio, "origen_web": p.origen_web,
            "url_original": p.url_original, "activa": p.activa, "favorita": p.favorita,
            "descartada": p.descartada, "fecha_scraping": p.fecha_scraping,
            "fecha_baja": p.fecha_baja,
        } for p in rows]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_hist() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(PrecioHistorico)).all()
        return [{"propiedad_id": h.propiedad_id, "precio": h.precio, "fecha": h.fecha}
                for h in rows]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_notarial() -> list[dict]:
    with Session(engine) as session:
        rows = EstadisticaNotarialCRUD.get_all(session)
        return [{
            "location_code": r.location_code, "property_type": r.property_type,
            "construction_type": r.construction_type,
            "current_price_per_sqm": r.current_price_per_sqm,
            "current_number_of_sales": r.current_number_of_sales,
            "current_average_price": r.current_average_price,
            "current_average_area_sqm": r.current_average_area_sqm,
            "rate_price_change": r.rate_price_change,
            "last_data_update": r.last_data_update, "report_date": r.report_date,
        } for r in rows]


def clear_caches():
    fetch_props.clear()
    fetch_hist.clear()
    fetch_notarial.clear()


def eur(v) -> str:
    return f"{v:,.0f} €".replace(",", ".")


# ── Pestaña Pulso ─────────────────────────────────────────────────────

def render_pulso(df, hist_df, now):
    k = ms.kpis_pulso(df, hist_df, now)
    c1, c2, c3, c4, c5 = st.columns(5)
    # delta_color: para un comprador, más oferta/bajadas/días = bueno (verde al subir);
    # €/m² y ventas subiendo = malo (rojo al subir) -> inverse.
    c1.metric("🆕 Nuevas (30d)", k["nuevas"]["valor"], delta=k["nuevas"]["delta"])
    c2.metric("🚫 Ventas (30d)", k["ventas"]["valor"], delta=k["ventas"]["delta"],
              delta_color="inverse")
    c3.metric("💶 €/m² mediano",
              eur(k["precio_m2"]["valor"]) if k["precio_m2"]["valor"] is not None else "N/D",
              delta=k["precio_m2"]["delta"], delta_color="inverse")
    c4.metric("📉 Bajadas (30d)", k["bajadas"]["valor"], delta=k["bajadas"]["delta"])
    c5.metric("⏱️ Días en mercado",
              f"{k['dias_mercado']['valor']:.0f}" if k["dias_mercado"]["valor"] is not None else "N/D",
              delta=k["dias_mercado"]["delta"])
    st.info(f"💡 {ms.lectura_mercado(k)}")
    st.caption("Deltas: últimos 30 días frente a los 30 anteriores. Verde = a favor del comprador.")
    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Entradas por semana")
        s = ms.serie_semanal_entradas(df, now)
        etiquetas = s["semana"].apply(lambda d: f"{d.day} {_MESES_ABREV[d.month]}")
        st.plotly_chart(
            bar_chart(etiquetas, s["nuevas"], "Nuevas",
                      hovertemplate="Semana del %{x}: %{y} nuevas<extra></extra>"),
            config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
        )
    with col_b:
        st.subheader("Ventas por mes")
        sv = ms.serie_mensual_ventas(df)
        if sv.empty:
            st.info("Sin ventas registradas todavía.")
        else:
            st.plotly_chart(
                bar_chart(sv["mes"], sv["ventas"], "Ventas"),
                config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
            )

    st.subheader("Evolución del €/m² mediano (activas)")
    sm = ms.serie_mensual_precio_m2(df, hist_df)
    if sm.empty:
        st.info("Sin historial de precios todavía.")
    else:
        st.plotly_chart(
            line_chart(sm, x="mes", y="precio_m2", y_title="€/m²", area=True),
            config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
        )


# ── Pestaña Zonas ─────────────────────────────────────────────────────

def render_zonas(df, hist_df, now):
    t = ms.tabla_zonas(df, hist_df, now)
    if t.empty:
        st.info("No hay propiedades para agrupar por zona.")
        return

    display = t.copy()
    display["precio_m2_mediano"] = display["precio_m2_mediano"].map(
        lambda v: eur(v) if v is not None and pd.notna(v) else "—")
    display["precio_mediano"] = display["precio_mediano"].map(
        lambda v: eur(v) if v is not None and pd.notna(v) else "—")
    display["dias_mercado"] = display["dias_mercado"].map(
        lambda v: f"{v:.0f}" if v is not None and pd.notna(v) else "—")
    display["pct_bajada"] = display["pct_bajada"].map(
        lambda v: f"{v:.1f}%" if v is not None and pd.notna(v) else "—")
    display["tendencia_pct"] = display["tendencia_pct"].map(
        lambda v: "=" if v is None or pd.isna(v)
        else (f"▲ +{v:.1f}%" if v > 0 else (f"▼ {v:.1f}%" if v < 0 else "= 0%")))
    display.columns = ["Barrio", "Activas", "€/m² mediano", "Precio mediano",
                       "Vendidas (6m)", "Días en mercado", "% con bajada", "Tendencia €/m²"]
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(
        f"Barrios con menos de {ms.MIN_ACTIVAS_BARRIO} activas se agrupan en «{ms.OTROS}». "
        "Tendencia: €/m² mediano de los últimos 90 días frente a los 90 anteriores."
    )
    st.divider()

    st.subheader("Evolución del €/m² por barrio")
    serie = ms.serie_mensual_precio_m2_por_barrio(df, hist_df)
    if serie.empty:
        st.info("Sin historial de precios todavía.")
        return
    barrios = sorted(serie["barrio"].unique())
    defecto = [b for b in barrios if b not in (ms.OTROS, ms.SIN_ZONA)][:3] or barrios[:3]
    seleccion = st.multiselect(
        "Barrios", barrios, default=defecto, max_selections=MAX_BARRIOS_GRAFICO,
        help=f"Máximo {MAX_BARRIOS_GRAFICO} barrios a la vez.",
    )
    if not seleccion:
        st.caption("Selecciona al menos un barrio.")
        return
    filtrada = serie[serie["barrio"].isin(seleccion)]
    st.plotly_chart(
        line_chart(filtrada, x="mes", y="precio_m2", color="barrio", y_title="€/m²"),
        config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
    )
    con_pocos = sorted(filtrada[filtrada["n"] < 3]["barrio"].unique())
    if con_pocos:
        st.warning(
            "⚠️ Líneas con meses de menos de 3 propiedades — interpretar con cautela: "
            + ", ".join(con_pocos)
        )


# ── Pestaña Ofertas ───────────────────────────────────────────────────

CAMPOS_LABEL = {
    "precio": "Precio (€)",
    "superficie_m2": "Superficie (m²)",
    "barrio": "Barrio",
    "tipo_propiedad": "Tipo de propiedad",
}


def form_completar_datos(fav: dict, campos: list, props: list, key: str):
    """Formulario inline para completar campos que faltan; persiste y recarga."""
    with st.form(f"completar_{key}_{fav['id']}"):
        valores = {}
        if "precio" in campos:
            valores["precio"] = st.number_input(CAMPOS_LABEL["precio"], min_value=0, step=1000)
        if "superficie_m2" in campos:
            valores["superficie_m2"] = st.number_input(CAMPOS_LABEL["superficie_m2"], min_value=0, step=1)
        if "barrio" in campos:
            with Session(engine) as session:
                barrios = PropiedadCRUD.get_distinct_barrios(session)
            elegido = st.selectbox(CAMPOS_LABEL["barrio"], [""] + barrios)
            libre = st.text_input("…o escribe un barrio nuevo")
            valores["barrio"] = libre.strip() or elegido
        if "tipo_propiedad" in campos:
            tipos = sorted({p["tipo_propiedad"] for p in props if p["tipo_propiedad"]})
            valores["tipo_propiedad"] = st.selectbox(CAMPOS_LABEL["tipo_propiedad"], [""] + tipos)

        if st.form_submit_button("💾 Guardar y recalcular", type="primary"):
            a_guardar = {k: v for k, v in valores.items() if v}
            if a_guardar:
                with Session(engine) as session:
                    PropiedadCRUD.update(session, fav["id"], **a_guardar)
                clear_caches()
                st.rerun()
            else:
                st.warning("No has rellenado ningún campo.")


def render_ofertas(props: list, now):
    favoritas = [p for p in props if p["favorita"]]
    if not favoritas:
        st.info("No tienes favoritas todavía. Marca alguna con ❤️ en la página de Propiedades.")
        return

    fav_id = st.selectbox(
        "Favorita a valorar", [p["id"] for p in favoritas],
        format_func=lambda pid: next(
            f"{(p['titulo'] or 'Sin título')[:60]} — " + (eur(p["precio"]) if p["precio"] else "sin precio")
            for p in favoritas if p["id"] == pid
        ),
        key="oferta_favorita_id",
    )
    fav = next(p for p in favoritas if p["id"] == fav_id)

    vista = oa.decidir_vista(fav, props, now)

    if vista == "form_imprescindibles":
        faltan = oa.campos_faltantes(fav)
        nombres = ", ".join(CAMPOS_LABEL[c] for c in faltan["imprescindibles"])
        st.warning(f"⚠️ No se puede valorar sin: {nombres}. Complétalos aquí:")
        st.markdown("#### 📝 Completa datos para afinar la valoración")
        form_completar_datos(fav, faltan["imprescindibles"] + faltan["mejora"], props, "impr")
        return

    if vista == "sin_comparables":
        faltan = oa.campos_faltantes(fav)
        st.error(
            "No hay ningún comparable con precio y superficie en tu base de datos "
            "(ni siquiera ampliando a todo el municipio). Añade más fuentes o espera a nuevos datos."
        )
        if faltan["mejora"]:
            with st.expander("📝 Completa datos para afinar la valoración"):
                form_completar_datos(fav, faltan["mejora"], props, "mejora")
        return

    faltan = oa.campos_faltantes(fav)
    comparables, nivel = oa.seleccionar_comparables(fav, props, now)
    val = oa.valorar(fav, comparables)
    ajustes = oa.calcular_ajustes(fav, comparables, now)
    rango = oa.rango_oferta(fav, val["valor_estimado"], ajustes)

    if val["n"] < oa.MIN_COMPARABLES:
        st.warning(
            f"⚠️ Solo {val['n']} comparable(s) (nivel: {oa.NIVELES[nivel]}). Fiabilidad baja."
        )
    else:
        st.caption(f"Comparables: {val['n']} · criterio: {oa.NIVELES[nivel]}")

    c1, c2, c3 = st.columns(3)
    c1.metric("🎯 Oferta inicial sugerida", eur(rango["oferta_inicial"]),
              delta=f"-{rango['descuento_total_pct']:.1f}% de presión" if rango["descuento_total_pct"] else None,
              delta_color="off")
    c2.metric("✅ Máximo razonable", eur(rango["maximo_razonable"]))
    c3.metric("📌 Precio anunciado", eur(fav["precio"]))

    comparables_eur = [c["precio"] / c["superficie_m2"] * fav["superficie_m2"] for c in comparables]
    st.plotly_chart(
        offer_range_chart(rango["oferta_inicial"], rango["maximo_razonable"],
                          val["valor_estimado"], fav["precio"], comparables_eur),
        config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
    )
    st.caption("Los puntos grises son los comparables llevados al tamaño de tu favorita (su €/m² × tu superficie).")

    st.markdown("#### 🧾 Desglose")
    st.markdown(f"- **Valor estimado**: {eur(val['valor_estimado'])} "
                f"(€/m² mediano de comparables: {eur(val['precio_m2_mediano'])} × {fav['superficie_m2']:.0f} m²)")
    for a in ajustes:
        pct_txt = f"{a['pct']:+.1f}%" if a["pct"] else "0%"
        st.markdown(f"- **{a['concepto']}** ({pct_txt}): {a['detalle']}")

    st.markdown("#### 📋 Comparables")
    tabla = pd.DataFrame([{
        "Título": (c["titulo"] or "")[:50],
        "Barrio": c["barrio"] or "—",
        "Tipo": c["tipo_propiedad"] or "—",
        "m²": c["superficie_m2"],
        "Precio": c["precio"],
        "€/m²": round(c["precio"] / c["superficie_m2"]),
        "Estado": "Activa" if c["activa"] else "Vendida",
        "Días en mercado": (c["fecha_baja"] - c["fecha_scraping"]).days
        if not c["activa"] and c["fecha_baja"] and c["fecha_scraping"] else None,
        "Anuncio": c["url_original"],
    } for c in comparables])
    st.dataframe(
        tabla, use_container_width=True, hide_index=True,
        column_config={"Anuncio": st.column_config.LinkColumn("Anuncio", display_text="Abrir")},
    )

    if faltan["mejora"]:
        nombres = ", ".join(CAMPOS_LABEL[c] for c in faltan["mejora"])
        with st.expander(f"📝 Completa datos para afinar la valoración ({nombres})"):
            st.caption(f"Añadir {nombres} afinaría los comparables (criterio actual: {oa.NIVELES[nivel]}).")
            form_completar_datos(fav, faltan["mejora"], props, "mejora")

    st.caption(
        "ℹ️ Heurística orientativa basada en la oferta anunciada observada en tus fuentes; "
        "no es una tasación oficial."
    )


# ── Pestaña Notarial ──────────────────────────────────────────────────

# Estado de "mercado vs oficial" desde la perspectiva del comprador — icono +
# etiqueta siempre (nunca solo color), reservado para esta comparación de estado.
ESTADO_LABEL = {
    "favorable": "🟢 Favorable",
    "neutral": "🟡 Neutral",
    "desfavorable": "🔴 Desfavorable",
    "sin_datos": "⚪ Sin datos",
}
ESTADO_ALERTA = {
    "favorable": (st.success, "Tus fuentes activas están por debajo del precio oficial notarial — margen para negociar a la baja."),
    "neutral": (st.info, "Tus fuentes activas están alineadas con el último precio oficial notarial."),
    "desfavorable": (st.warning, "Tus fuentes activas están por encima del precio oficial notarial — presión al alza en el mercado."),
    "sin_datos": (st.info, "Sin datos suficientes todavía para comparar mercado vs oficial (piso · segunda mano)."),
}
_CONSTRUCCION_LABEL = {"obra_nueva": "Obra nueva", "segunda_mano": "Segunda mano"}


def n_(v) -> str:
    return f"{v:,.0f}".replace(",", ".") if v is not None and pd.notna(v) else "N/D"


def _combo_label(row) -> str:
    return ns.COMBO_LABELS.get(
        (row["property_type"], row["construction_type"]),
        f"{row['property_type']} · {row['construction_type']}",
    )


def _serie_piso_por_construccion(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Serie mensual de `columna` para property_type=piso, una traza por construction_type."""
    partes = []
    for construction_type in ("obra_nueva", "segunda_mano"):
        s = ns.serie_mensual(df, "piso", construction_type, columna)
        if not s.empty:
            s = s.copy()
            s["construction_type"] = _CONSTRUCCION_LABEL[construction_type]
            partes.append(s)
    if not partes:
        return pd.DataFrame(columns=["last_data_update", columna, "construction_type"])
    return pd.concat(partes, ignore_index=True)


def render_notarial(notarial_rows: list, props: list):
    if not ns.has_notarial_data(notarial_rows):
        st.info(
            "📭 Todavía no hay estadísticas notariales oficiales almacenadas. "
            "Se cargan semanalmente vía `scripts/fetch_notariado_stats.py`."
        )
        return

    df = ns.notarial_to_df(notarial_rows)
    latest = ns.latest_por_combo(df)
    listing_por_tipo = ns.listing_precio_m2_medio_por_tipo(props)
    tabla = ns.tabla_comparativa(latest, listing_por_tipo)
    piso_df = df[df["property_type"] == "piso"]

    # ── KPIs (mes más reciente con dato vs el anterior) ────────────────
    d_ventas = ns.delta_ultimo_periodo(
        ns.serie_mensual_total(df, "current_number_of_sales", agg="sum"), "current_number_of_sales"
    )
    d_precio_m2 = ns.delta_ultimo_periodo(
        ns.serie_mensual_total(piso_df, "current_price_per_sqm", agg="mean"), "current_price_per_sqm"
    )
    d_precio_medio = ns.delta_ultimo_periodo(
        ns.serie_mensual_total(piso_df, "current_average_price", agg="mean"), "current_average_price"
    )

    fila_referencia = tabla[
        (tabla["property_type"] == "piso") & (tabla["construction_type"] == "segunda_mano")
    ]
    diferencia_ref = fila_referencia["diferencia"].iloc[0] if not fila_referencia.empty else None
    oficial_ref = fila_referencia["precio_m2_oficial"].iloc[0] if not fila_referencia.empty else None
    estado = ns.estado_comparacion_mercado(diferencia_ref, oficial_ref)

    st.subheader("📌 Resumen del mercado")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "🤝 Compraventas / mes (todos los tipos)", n_(d_ventas["actual"]),
        delta=f"{d_ventas['delta_abs']:+.0f}" if d_ventas["delta_abs"] is not None else None,
        delta_color="off",
    )
    c2.metric(
        "💶 €/m² oficial (piso)",
        eur(d_precio_m2["actual"]) if d_precio_m2["actual"] is not None else "N/D",
        delta=f"{d_precio_m2['delta_pct']:+.1f}%" if d_precio_m2["delta_pct"] is not None else None,
        delta_color="inverse",
    )
    c3.metric(
        "🏠 Precio medio oficial (piso)",
        eur(d_precio_medio["actual"]) if d_precio_medio["actual"] is not None else "N/D",
        delta=f"{d_precio_medio['delta_pct']:+.1f}%" if d_precio_medio["delta_pct"] is not None else None,
        delta_color="inverse",
    )
    alerta_fn, mensaje = ESTADO_ALERTA[estado]
    sufijo = f" (diferencia: {eur(diferencia_ref)}/m²)" if diferencia_ref is not None else ""
    alerta_fn(f"{ESTADO_LABEL[estado]} — {mensaje}{sufijo}")
    st.caption(
        "Deltas de compraventas y precios: último informe notarial disponible frente al "
        "anterior con dato. Verde/rojo en €/m² y precio medio: bajar es bueno para el comprador."
    )
    st.divider()

    # ── Evolución mensual — piso, obra nueva vs segunda mano, 3 en fila ─
    st.subheader("📈 Evolución mensual — piso")
    metricas_evolucion = [
        ("current_price_per_sqm", "€/m²", "€/m²"),
        ("current_number_of_sales", "Compraventas", "nº"),
        ("current_average_price", "Precio medio", "€"),
    ]
    cols_evolucion = st.columns(3)
    for col, (columna, titulo, y_title) in zip(cols_evolucion, metricas_evolucion):
        with col:
            st.caption(titulo)
            serie = _serie_piso_por_construccion(df, columna)
            if serie.empty or serie["last_data_update"].nunique() < 2:
                st.info("Histórico insuficiente (≥2 informes con dato).")
            else:
                st.plotly_chart(
                    line_chart(serie, x="last_data_update", y=columna,
                               color="construction_type", y_title=y_title),
                    config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
                )
    st.divider()

    # ── Último informe oficial por tipo de vivienda, 3 en fila ─────────
    st.subheader("🏷️ Último informe oficial — por tipo de vivienda")
    metricas_barras = [
        ("current_price_per_sqm", "€/m² oficial"),
        ("current_number_of_sales", "Compraventas"),
        ("current_average_price", "Precio medio"),
    ]
    cols_barras = st.columns(3)
    for col, (columna, titulo) in zip(cols_barras, metricas_barras):
        with col:
            st.caption(titulo)
            barras = latest.dropna(subset=[columna])
            if barras.empty:
                st.info("Sin dato oficial todavía.")
            else:
                etiquetas = barras.apply(_combo_label, axis=1)
                st.plotly_chart(
                    bar_chart(etiquetas, barras[columna], titulo),
                    config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
                )
    st.divider()

    # ── Tabla comparativa oficial vs mercado, con estado ───────────────
    st.subheader("⚖️ Oficial (Notariado) vs mercado actual — €/m²")
    display = tabla.copy()
    display["combo"] = display.apply(_combo_label, axis=1)
    display["Estado"] = display.apply(
        lambda r: ESTADO_LABEL[ns.estado_comparacion_mercado(r["diferencia"], r["precio_m2_oficial"])],
        axis=1,
    )
    for col in ("precio_m2_oficial", "precio_m2_mercado", "diferencia"):
        display[col] = display[col].map(lambda v: eur(v) if v is not None and pd.notna(v) else "—")
    display = display[["combo", "precio_m2_oficial", "precio_m2_mercado", "diferencia", "Estado"]]
    display.columns = ["Tipo", "€/m² oficial (Notariado)", "€/m² mercado (activas)", "Diferencia", "Estado"]
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(
        "Diferencia = €/m² medio de tus fuentes activas − €/m² oficial del último informe "
        "notarial disponible (a nivel municipio). Positivo = tus fuentes están por encima "
        "del precio notarial. Estado: favorable/desfavorable a partir de ±3% de diferencia."
    )


# ── Página ────────────────────────────────────────────────────────────

try:
    st.title("📊 Mercado")

    tab = st.segmented_control(
        "Vista", options=list(TABS.keys()),
        format_func=lambda k: TABS[k],
        default="pulso", key="tab_mercado",
        label_visibility="collapsed", required=True,
    ) or "pulso"

    props = fetch_props()

    if tab == "notarial":
        render_notarial(fetch_notarial(), props)
    elif not props:
        st.warning("No hay propiedades en la base de datos.")
    else:
        hist = fetch_hist()
        df = ms.props_to_df(props)
        hist_df = ms.hist_to_df(hist)
        now = datetime.now(UTC).replace(tzinfo=None)

        if tab == "pulso":
            render_pulso(df, hist_df, now)
        elif tab == "zonas":
            render_zonas(df, hist_df, now)
        else:
            render_ofertas(props, now)

except Exception as e:
    st.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

"""Página de estadísticas y análisis del mercado inmobiliario."""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta, UTC

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from sqlalchemy import func, distinct
import pandas as pd

from db.database import engine
from db.models import Propiedad, PrecioHistorico, Fuente

st.set_page_config(page_title="Estadísticas", page_icon="📊", layout="wide")
st.title("📊 Estadísticas del mercado")


def fmt_price(v):
    if v is None:
        return "N/A"
    return f"€{v:,.0f}"


# ── Filtros globales ─────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Filtros")
    excluir_descartadas = st.checkbox("Excluir descartadas", value=True)
    solo_favoritas = st.checkbox("Solo favoritas", value=False)
    st.divider()
    st.caption("Los filtros afectan a todos los gráficos y tablas.")


try:
    with Session(engine) as session:
        # ── KPIs globales ────────────────────────────────────────────────────
        total = session.exec(select(func.count(Propiedad.id))).first() or 0
        activas = session.exec(select(func.count(Propiedad.id)).where(Propiedad.activa == True)).first() or 0
        vendidas = session.exec(select(func.count(Propiedad.id)).where(Propiedad.activa == False)).first() or 0
        favoritas = session.exec(select(func.count(Propiedad.id)).where(Propiedad.favorita == True)).first() or 0
        descartadas = session.exec(select(func.count(Propiedad.id)).where(Propiedad.descartada == True)).first() or 0
        bajadas = session.exec(
            select(func.count(Propiedad.id)).where(
                Propiedad.precio_anterior != None,
                Propiedad.activa == True,
            )
        ).first() or 0

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("🏘️ Total", total)
        col2.metric("✅ Activas", activas)
        col3.metric("🚫 Vendidas", vendidas)
        col4.metric("❤️ Favoritas", favoritas)
        col5.metric("❌ Descartadas", descartadas)
        col6.metric("📉 Con bajada", bajadas)

        st.divider()

        # ── Cargar DataFrame completo ────────────────────────────────────────
        rows = session.exec(select(Propiedad)).all()
        if not rows:
            st.warning("No hay propiedades en la base de datos.")
            st.stop()

        df = pd.DataFrame([{
            "id": p.id,
            "titulo": p.titulo,
            "precio": p.precio,
            "precio_anterior": p.precio_anterior,
            "superficie_m2": p.superficie_m2,
            "habitaciones": p.habitaciones,
            "tipo_propiedad": p.tipo_propiedad,
            "origen_web": p.origen_web,
            "barrio": p.barrio,
            "distrito": p.distrito,
            "municipio": p.municipio,
            "activa": p.activa,
            "favorita": p.favorita,
            "descartada": p.descartada,
            "fecha_scraping": p.fecha_scraping,
            "fecha_baja": p.fecha_baja,
            "ascensor": p.ascensor,
            "garaje": p.garaje,
            "terraza": p.terraza,
            "piscina": p.piscina,
        } for p in rows])

        df["precio_m2"] = df.apply(
            lambda r: r["precio"] / r["superficie_m2"]
            if r["precio"] and r["superficie_m2"] and r["superficie_m2"] > 0 else None,
            axis=1
        )
        df["bajada_pct"] = df.apply(
            lambda r: round(100 * (r["precio_anterior"] - r["precio"]) / r["precio_anterior"], 1)
            if r["precio"] and r["precio_anterior"] and r["precio_anterior"] > 0 else None,
            axis=1
        )
        # Apply global sidebar filters
        df_activas = df[df["activa"] == True].copy()
        if excluir_descartadas:
            df_activas = df_activas[df_activas["descartada"] == False]
        if solo_favoritas:
            df_activas = df_activas[df_activas["favorita"] == True]
        df_vendidas = df[df["activa"] == False].copy()

        # ── Tabs ─────────────────────────────────────────────────────────────
        tab_precios, tab_oferta, tab_vendidas, tab_bajadas, tab_historial = st.tabs([
            "💰 Precios", "🏠 Oferta", "🚫 Vendidas", "📉 Bajadas", "📈 Historial"
        ])

        # ── TAB 1: PRECIOS ───────────────────────────────────────────────────
        with tab_precios:
            st.subheader("Precio medio por tipo de propiedad")

            col_a, col_b = st.columns(2)
            with col_a:
                df_tipo = (
                    df_activas.dropna(subset=["tipo_propiedad", "precio"])
                    .groupby("tipo_propiedad")["precio"]
                    .agg(["mean", "median", "count"])
                    .rename(columns={"mean": "Precio medio", "median": "Precio mediano", "count": "Nº"})
                    .sort_values("Precio medio", ascending=False)
                )
                df_tipo["Precio medio"] = df_tipo["Precio medio"].map(lambda v: f"€{v:,.0f}")
                df_tipo["Precio mediano"] = df_tipo["Precio mediano"].map(lambda v: f"€{v:,.0f}")
                if not df_tipo.empty:
                    st.dataframe(df_tipo, use_container_width=True)
                else:
                    st.info("Sin datos suficientes")

            with col_b:
                st.subheader("Precio €/m² por tipo")
                df_m2 = (
                    df_activas.dropna(subset=["tipo_propiedad", "precio_m2"])
                    .groupby("tipo_propiedad")["precio_m2"]
                    .agg(["mean", "count"])
                    .rename(columns={"mean": "€/m² medio", "count": "Nº"})
                    .sort_values("€/m² medio", ascending=False)
                )
                df_m2["€/m² medio"] = df_m2["€/m² medio"].map(lambda v: f"€{v:,.0f}")
                if not df_m2.empty:
                    st.dataframe(df_m2, use_container_width=True)
                else:
                    st.info("Sin datos suficientes")

            st.divider()
            st.subheader("Distribución de precios")
            precio_data = df_activas.dropna(subset=["precio"])
            if not precio_data.empty:
                # Filter outliers: up to 99th percentile
                p99 = precio_data["precio"].quantile(0.99)
                precio_hist = precio_data[precio_data["precio"] <= p99]["precio"]
                st.bar_chart(precio_hist.value_counts(bins=20).sort_index())
            else:
                st.info("Sin datos de precio")

            st.divider()
            st.subheader("Precio medio por fuente")
            df_fuente = (
                df_activas.dropna(subset=["origen_web", "precio"])
                .groupby("origen_web")["precio"]
                .agg(["mean", "count"])
                .rename(columns={"mean": "Precio medio", "count": "Propiedades"})
                .sort_values("Precio medio", ascending=False)
            )
            df_fuente["Precio medio"] = df_fuente["Precio medio"].map(lambda v: f"€{v:,.0f}")
            if not df_fuente.empty:
                st.dataframe(df_fuente, use_container_width=True)

        # ── TAB 2: OFERTA ────────────────────────────────────────────────────
        with tab_oferta:
            col_a, col_b = st.columns(2)

            with col_a:
                st.subheader("Propiedades por tipo")
                tipo_counts = df_activas["tipo_propiedad"].value_counts().dropna()
                if not tipo_counts.empty:
                    st.bar_chart(tipo_counts)
                else:
                    st.info("Sin datos")

                st.subheader("Por número de habitaciones")
                hab_counts = df_activas["habitaciones"].value_counts().dropna().sort_index()
                if not hab_counts.empty:
                    st.bar_chart(hab_counts)

            with col_b:
                st.subheader("Propiedades por fuente")
                fuente_counts = df_activas["origen_web"].value_counts()
                if not fuente_counts.empty:
                    st.bar_chart(fuente_counts)

                st.subheader("Por barrio / zona")
                barrio_counts = df_activas["barrio"].value_counts().dropna().head(15)
                if not barrio_counts.empty:
                    st.bar_chart(barrio_counts)
                else:
                    distrito_counts = df_activas["distrito"].value_counts().dropna().head(15)
                    if not distrito_counts.empty:
                        st.bar_chart(distrito_counts)
                    else:
                        st.info("Sin datos de zona")

            st.divider()
            st.subheader("Características más comunes")
            features = {
                "Ascensor": df_activas["ascensor"].sum(),
                "Garaje": df_activas["garaje"].sum(),
                "Terraza": df_activas["terraza"].sum(),
                "Piscina": df_activas["piscina"].sum(),
            }
            feat_df = pd.DataFrame(list(features.items()), columns=["Característica", "Propiedades"])
            feat_df = feat_df[feat_df["Propiedades"] > 0].sort_values("Propiedades", ascending=False)
            if not feat_df.empty:
                st.bar_chart(feat_df.set_index("Característica"))

            st.divider()
            st.subheader("Nuevas propiedades por día (últimos 30 días)")
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
            df_recientes = df[df["fecha_scraping"] >= cutoff].copy()
            if not df_recientes.empty:
                df_recientes["dia"] = df_recientes["fecha_scraping"].dt.date
                daily = df_recientes.groupby("dia").size().rename("Nuevas propiedades")
                st.line_chart(daily)
            else:
                st.info("Sin propiedades en los últimos 30 días")

        # ── TAB 3: VENDIDAS ──────────────────────────────────────────────────
        with tab_vendidas:
            if df_vendidas.empty:
                st.info("No hay propiedades marcadas como vendidas todavía.")
            else:
                st.subheader(f"🚫 {len(df_vendidas)} propiedades vendidas / reservadas")

                # ── Calcular días en mercado ──────────────────────────────
                df_v = df_vendidas.copy()
                df_v["fecha_scraping"] = pd.to_datetime(df_v["fecha_scraping"])
                df_v["fecha_baja"] = pd.to_datetime(df_v["fecha_baja"])
                df_v_tim = df_v.dropna(subset=["fecha_baja"])
                df_v_tim["dias_mercado"] = (
                    df_v_tim["fecha_baja"] - df_v_tim["fecha_scraping"]
                ).dt.days.clip(lower=0)

                # ── KPIs ─────────────────────────────────────────────────
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.metric("Total vendidas", len(df_v))
                col_b.metric("Precio medio", fmt_price(df_v["precio"].mean()))
                if not df_v_tim.empty:
                    col_c.metric("Días en mercado (media)", f"{df_v_tim['dias_mercado'].mean():.0f} días")
                    col_d.metric("Días en mercado (mediana)", f"{df_v_tim['dias_mercado'].median():.0f} días")
                else:
                    col_c.metric("Días en mercado", "Sin datos aún")
                    col_d.metric("", "")

                st.divider()

                # ── Tiempo en mercado ─────────────────────────────────────
                if not df_v_tim.empty:
                    st.subheader("⏱️ Tiempo en mercado")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.caption("Distribución de días en mercado")
                        hist_data = df_v_tim["dias_mercado"]
                        st.bar_chart(hist_data.value_counts(bins=10).sort_index())

                    with col_b:
                        st.caption("Días en mercado por tipo de propiedad")
                        tim_tipo = (
                            df_v_tim.dropna(subset=["tipo_propiedad"])
                            .groupby("tipo_propiedad")["dias_mercado"]
                            .agg(["mean", "median", "count"])
                            .rename(columns={"mean": "Media (días)", "median": "Mediana (días)", "count": "Nº"})
                            .sort_values("Media (días)")
                        )
                        tim_tipo["Media (días)"] = tim_tipo["Media (días)"].map(lambda v: f"{v:.0f}")
                        tim_tipo["Mediana (días)"] = tim_tipo["Mediana (días)"].map(lambda v: f"{v:.0f}")
                        if not tim_tipo.empty:
                            st.dataframe(tim_tipo, use_container_width=True)

                    st.caption("Días en mercado por barrio (mín. 2 propiedades)")
                    tim_barrio = (
                        df_v_tim.dropna(subset=["barrio"])
                        .groupby("barrio")["dias_mercado"]
                        .agg(["mean", "count"])
                        .rename(columns={"mean": "Media días", "count": "Nº"})
                    )
                    tim_barrio = tim_barrio[tim_barrio["Nº"] >= 2].sort_values("Media días")
                    if not tim_barrio.empty:
                        tim_barrio["Media días"] = tim_barrio["Media días"].map(lambda v: f"{v:.0f}")
                        st.dataframe(tim_barrio, use_container_width=True)
                    else:
                        st.info("Aún no hay suficientes vendidas por barrio para comparar.")

                    st.divider()

                st.subheader("Por tipo de propiedad")
                tipo_v = df_v["tipo_propiedad"].value_counts().dropna()
                if not tipo_v.empty:
                    st.bar_chart(tipo_v)

                st.subheader("Listado de propiedades vendidas")
                cols_show = ["titulo", "precio", "superficie_m2", "habitaciones", "tipo_propiedad", "origen_web", "fecha_scraping", "fecha_baja"]
                df_v_display = df_v[cols_show].copy()
                df_v_display["precio"] = df_v_display["precio"].map(lambda v: fmt_price(v) if v else "N/A")
                df_v_display["fecha_scraping"] = df_v_display["fecha_scraping"].dt.strftime("%Y-%m-%d")
                df_v_display["fecha_baja"] = df_v_display["fecha_baja"].dt.strftime("%Y-%m-%d").fillna("—")
                if not df_v_tim.empty:
                    df_v_display = df_v_display.join(df_v_tim["dias_mercado"].rename("Días"))
                df_v_display.columns = (
                    ["Título", "Precio", "m²", "Hab.", "Tipo", "Fuente", "Entrada", "Baja", "Días en mercado"]
                    if not df_v_tim.empty else
                    ["Título", "Precio", "m²", "Hab.", "Tipo", "Fuente", "Entrada", "Baja"]
                )
                st.dataframe(df_v_display, use_container_width=True)

        # ── TAB 4: BAJADAS DE PRECIO ─────────────────────────────────────────
        with tab_bajadas:
            df_bajadas_df = df_activas.dropna(subset=["precio", "precio_anterior", "bajada_pct"])
            df_bajadas_df = df_bajadas_df[df_bajadas_df["bajada_pct"] > 0].sort_values("bajada_pct", ascending=False)

            if df_bajadas_df.empty:
                st.info("No hay bajadas de precio registradas.")
            else:
                st.subheader(f"📉 {len(df_bajadas_df)} propiedades con bajada de precio")

                col_a, col_b = st.columns(2)
                col_a.metric("Bajada media", f"{df_bajadas_df['bajada_pct'].mean():.1f}%")
                col_b.metric("Bajada máxima", f"{df_bajadas_df['bajada_pct'].max():.1f}%")

                st.divider()
                display = df_bajadas_df[["titulo", "precio_anterior", "precio", "bajada_pct", "tipo_propiedad", "origen_web"]].copy()
                display["precio_anterior"] = display["precio_anterior"].map(fmt_price)
                display["precio"] = display["precio"].map(fmt_price)
                display["bajada_pct"] = display["bajada_pct"].map(lambda v: f"{v:.1f}%")
                display.columns = ["Título", "Precio anterior", "Precio actual", "Bajada %", "Tipo", "Fuente"]
                st.dataframe(display, use_container_width=True)

                st.subheader("Distribución de bajadas (%)")
                st.bar_chart(df_bajadas_df["bajada_pct"].value_counts(bins=10).sort_index())

        # ── TAB 5: HISTORIAL DE PRECIOS ──────────────────────────────────────
        with tab_historial:
            st.subheader("Evolución del precio medio mensual")

            hist_rows = session.exec(
                select(PrecioHistorico).order_by(PrecioHistorico.fecha.asc())
            ).all()

            if not hist_rows:
                st.info("Sin historial de precios todavía.")
            else:
                df_hist = pd.DataFrame([{
                    "fecha": h.fecha,
                    "precio": h.precio,
                    "propiedad_id": h.propiedad_id,
                } for h in hist_rows])
                df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])
                df_hist["mes"] = df_hist["fecha"].dt.to_period("M").astype(str)

                mensual = df_hist.groupby("mes")["precio"].mean().rename("Precio medio (€)")
                st.line_chart(mensual)

                st.divider()
                st.subheader("Número de registros de precio por mes")
                registros_mes = df_hist.groupby("mes").size().rename("Registros")
                st.bar_chart(registros_mes)

                total_registros = len(df_hist)
                propiedades_con_hist = df_hist["propiedad_id"].nunique()
                col_a, col_b = st.columns(2)
                col_a.metric("Registros totales de precio", total_registros)
                col_b.metric("Propiedades con historial", propiedades_con_hist)

except Exception as e:
    st.error(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

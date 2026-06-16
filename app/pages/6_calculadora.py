"""Calculadora de gastos de compraventa e hipoteca."""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.calculadora import (
    calcular_compraventa,
    calcular_gastos_hipoteca,
    calcular_aportacion_necesaria,
    calcular_hipoteca,
)

st.set_page_config(page_title="Calculadora", page_icon="🧮", layout="wide")
st.title("🧮 Calculadora de compraventa e hipoteca")

col_form, col_result = st.columns([1, 1], gap="large")

# ── FORMULARIOS ───────────────────────────────────────────────────────────────
with col_form:

    # Bloque A
    st.subheader("A) Gastos de compraventa")
    precio = st.number_input("Precio de la vivienda (€)", min_value=0.0, value=200_000.0, step=5_000.0, format="%.0f")
    itp_pct = st.selectbox("ITP", options=[3.5, 6.0, 7.0], index=2, format_func=lambda v: f"{v}%")
    notaria = st.number_input("Notaría (€)", min_value=0.0, value=700.0, step=50.0, format="%.0f")
    registro = st.number_input("Registro (€)", min_value=0.0, value=350.0, step=50.0, format="%.0f")
    agencia_pct = st.number_input("Agencia (% sobre precio)", min_value=0.0, value=0.0, step=0.5, format="%.1f")

    st.divider()

    # Modo de financiación
    st.subheader("💰 Aportación inicial")
    modo = st.radio("Modo", ["Manual", "80% financiación", "90% financiación", "100% financiación"], horizontal=True)

    # Bloque B
    st.subheader("B) Gastos hipotecarios")
    comision_apertura = st.number_input("Comisión de apertura (€)", min_value=0.0, value=0.0, step=100.0, format="%.0f")
    gestoria = st.number_input("Gestoría (€)", min_value=0.0, value=350.0, step=50.0, format="%.0f")
    tasacion = st.number_input("Tasación (€)", min_value=0.0, value=450.0, step=50.0, format="%.0f")
    registro_hip = st.number_input("Registro hipoteca (€)", min_value=0.0, value=0.0, step=50.0, format="%.0f")
    ajd_pct = st.number_input("AJD (% sobre préstamo)", min_value=0.0, value=1.0, step=0.1, format="%.1f")

    st.divider()

    # Hipoteca
    st.subheader("🏦 Préstamo hipotecario")
    tipo_base = st.number_input("Tipo de interés base (%)", min_value=0.0, value=3.0, step=0.1, format="%.2f")

    st.caption("Bonificaciones (cada una reduce el tipo final)")
    if "bonificaciones" not in st.session_state:
        st.session_state.bonificaciones = []

    for i, bon in enumerate(st.session_state.bonificaciones):
        bc1, bc2, bc3 = st.columns([3, 2, 1])
        with bc1:
            st.session_state.bonificaciones[i]["nombre"] = st.text_input(
                "Concepto", value=bon["nombre"], key=f"bon_nombre_{i}", label_visibility="collapsed"
            )
        with bc2:
            st.session_state.bonificaciones[i]["reduccion"] = st.number_input(
                "Reducción %", value=bon["reduccion"], min_value=0.0, max_value=5.0, step=0.05,
                format="%.2f", key=f"bon_red_{i}", label_visibility="collapsed"
            )
        with bc3:
            if st.button("🗑️", key=f"del_bon_{i}"):
                st.session_state.bonificaciones.pop(i)
                st.rerun()

    if st.button("➕ Añadir bonificación"):
        st.session_state.bonificaciones.append({"nombre": "", "reduccion": 0.25})
        st.rerun()

    total_bonificacion = sum(b["reduccion"] for b in st.session_state.bonificaciones)
    tipo_final = max(tipo_base - total_bonificacion, 0.0)
    st.info(f"Tipo final: **{tipo_final:.2f}%** (base {tipo_base:.2f}% − bonificaciones {total_bonificacion:.2f}%)")

    plazo_anos = st.slider("Plazo de amortización (años)", min_value=5, max_value=40, value=30)

# ── CÁLCULOS ──────────────────────────────────────────────────────────────────
gastos_a = calcular_compraventa(precio, itp_pct, notaria, registro, agencia_pct)
total_a = gastos_a["total_a"]

financiacion_pct_map = {"Manual": None, "80% financiación": 80.0, "90% financiación": 90.0, "100% financiación": 100.0}
financiacion_pct = financiacion_pct_map[modo]

if financiacion_pct is not None:
    prestamo_estimado = precio * financiacion_pct / 100
else:
    prestamo_estimado = precio

gastos_b = calcular_gastos_hipoteca(prestamo_estimado, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct)
total_b = gastos_b["total_b"]

if financiacion_pct is not None:
    aportacion = calcular_aportacion_necesaria(precio, financiacion_pct, total_a, total_b)
    prestamo_calculado = round(precio * financiacion_pct / 100, 2)
else:
    aportacion = st.session_state.get("aportacion_manual", 0.0)
    prestamo_calculado = max(precio + total_a + total_b - aportacion, 0.0)

gastos_b = calcular_gastos_hipoteca(prestamo_calculado, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct)
total_b = gastos_b["total_b"]

coste_total = precio + total_a + total_b

hip = calcular_hipoteca(prestamo_calculado, tipo_final, plazo_anos) if prestamo_calculado > 0 else None

# ── RESULTADOS ────────────────────────────────────────────────────────────────
with col_result:
    st.subheader("📊 Resumen")

    if financiacion_pct is None:
        aportacion_manual = st.number_input(
            "Aportación inicial (€)", min_value=0.0,
            value=st.session_state.get("aportacion_manual", precio * 0.2),
            step=1_000.0, format="%.0f", key="aportacion_manual"
        )
        prestamo_calculado = max(precio + total_a + total_b - aportacion_manual, 0.0)
        gastos_b = calcular_gastos_hipoteca(prestamo_calculado, comision_apertura, gestoria, tasacion, registro_hip, ajd_pct)
        total_b = gastos_b["total_b"]
        coste_total = precio + total_a + total_b
        hip = calcular_hipoteca(prestamo_calculado, tipo_final, plazo_anos) if prestamo_calculado > 0 else None
    else:
        st.info(f"💰 Con financiación del **{financiacion_pct:.0f}%**, necesitas al menos **€{aportacion:,.0f}** de ahorros (entrada + todos los gastos)")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total gastos A", f"€{total_a:,.0f}")
    col2.metric("Total gastos B", f"€{total_b:,.0f}")
    col3.metric("Total gastos A+B", f"€{total_a + total_b:,.0f}")

    st.metric("Coste total (vivienda + gastos)", f"€{coste_total:,.0f}")
    st.metric("Préstamo solicitado", f"€{prestamo_calculado:,.0f}")

    st.divider()

    with st.expander("📋 Desglose gastos A"):
        st.caption(f"ITP ({itp_pct}%): €{gastos_a['itp_importe']:,.0f}")
        st.caption(f"Notaría: €{gastos_a['notaria']:,.0f}")
        st.caption(f"Registro: €{gastos_a['registro']:,.0f}")
        if gastos_a["agencia_importe"] > 0:
            st.caption(f"Agencia ({agencia_pct}%): €{gastos_a['agencia_importe']:,.0f}")

    with st.expander("📋 Desglose gastos B"):
        if gastos_b["comision_apertura"] > 0:
            st.caption(f"Comisión apertura: €{gastos_b['comision_apertura']:,.0f}")
        st.caption(f"Gestoría: €{gastos_b['gestoria']:,.0f}")
        st.caption(f"Tasación: €{gastos_b['tasacion']:,.0f}")
        if gastos_b["registro_hip"] > 0:
            st.caption(f"Registro hipoteca: €{gastos_b['registro_hip']:,.0f}")
        st.caption(f"AJD ({ajd_pct}%): €{gastos_b['ajd_importe']:,.0f}")

    if hip:
        st.divider()
        st.subheader("🏦 Hipoteca")
        st.metric("Cuota mensual", f"€{hip['cuota_mensual']:,.2f}", help=f"Tipo final: {tipo_final:.2f}% a {plazo_anos} años")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total pagado", f"€{hip['total_pagado']:,.0f}")
        c2.metric("Total intereses", f"€{hip['total_intereses']:,.0f}")
        c3.metric("% intereses", f"{hip['pct_intereses']:.1f}%")

        with st.expander("📊 Tabla de amortización"):
            df_tabla = pd.DataFrame(hip["tabla"])
            st.caption("Primeros 12 meses:")
            st.dataframe(
                df_tabla.head(12).style.format({
                    "Cuota": "€{:.2f}", "Capital": "€{:.2f}",
                    "Intereses": "€{:.2f}", "Saldo pendiente": "€{:,.0f}"
                }),
                use_container_width=True,
                hide_index=True,
            )
            if len(df_tabla) > 12:
                if st.checkbox("Ver tabla completa"):
                    st.dataframe(
                        df_tabla.style.format({
                            "Cuota": "€{:.2f}", "Capital": "€{:.2f}",
                            "Intereses": "€{:.2f}", "Saldo pendiente": "€{:,.0f}"
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )

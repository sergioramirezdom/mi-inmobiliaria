"""Tests de la capa pura de estadísticas notariales (pestaña Notarial)."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pandas as pd

from ui.notarial_stats import (
    COMBOS,
    delta_meses_atras,
    delta_ultimo_periodo,
    es_fila_actual,
    estado_comparacion_mercado,
    fila_actual_por_combo,
    has_notarial_data,
    latest_por_combo,
    listing_precio_m2_medio_por_tipo,
    notarial_to_df,
    serie_mensual,
    serie_mensual_total,
    serie_temporal,
    solo_mensual,
    tabla_comparativa,
)


def _row(**kw):
    base = dict(
        location_code="11027",
        property_type="piso",
        construction_type="obra_nueva",
        current_price_per_sqm=2500.0,
        current_number_of_sales=10,
        current_average_price=200000.0,
        current_average_area_sqm=80.0,
        rate_price_change=1.5,
        last_data_update=datetime(2026, 6, 1),
        report_date=datetime(2026, 6, 1),
        raw_json="{}",
    )
    base.update(kw)
    return base


# ── has_notarial_data (empty-state) ────────────────────────────────────

def test_has_notarial_data_false_when_no_rows():
    assert has_notarial_data([]) is False


def test_has_notarial_data_true_when_rows_present():
    assert has_notarial_data([_row()]) is True


# ── notarial_to_df ──────────────────────────────────────────────────────

def test_notarial_to_df_empty_list_returns_empty_df():
    df = notarial_to_df([])
    assert df.empty


def test_notarial_to_df_parses_dates():
    df = notarial_to_df([_row()])
    assert pd.api.types.is_datetime64_any_dtype(df["last_data_update"])
    assert pd.api.types.is_datetime64_any_dtype(df["report_date"])


# ── latest_por_combo ────────────────────────────────────────────────────

def test_latest_por_combo_picks_most_recent_row_per_combo():
    rows = [
        _row(current_price_per_sqm=2000.0, last_data_update=datetime(2026, 1, 1)),
        _row(current_price_per_sqm=2500.0, last_data_update=datetime(2026, 6, 1)),
        _row(
            property_type="casa", construction_type="segunda_mano",
            current_price_per_sqm=1800.0, last_data_update=datetime(2026, 3, 1),
        ),
    ]
    df = notarial_to_df(rows)
    latest = latest_por_combo(df)
    assert len(latest) == 2
    piso_row = latest[latest["property_type"] == "piso"].iloc[0]
    assert piso_row["current_price_per_sqm"] == 2500.0


def test_latest_por_combo_empty_df_returns_empty():
    assert latest_por_combo(pd.DataFrame()).empty


# ── serie_temporal ───────────────────────────────────────────────────────

def test_serie_temporal_filters_by_combo_and_sorts():
    rows = [
        _row(current_price_per_sqm=2200.0, last_data_update=datetime(2026, 3, 1)),
        _row(current_price_per_sqm=2000.0, last_data_update=datetime(2026, 1, 1)),
        _row(property_type="casa", current_price_per_sqm=1500.0),
    ]
    df = notarial_to_df(rows)
    serie = serie_temporal(df, "piso", "obra_nueva")
    assert list(serie["current_price_per_sqm"]) == [2000.0, 2200.0]


# ── listing_precio_m2_medio_por_tipo ──────────────────────────────────────

def test_listing_precio_m2_medio_por_tipo_averages_active_listings():
    props = [
        {"activa": True, "tipo_propiedad": "piso", "precio": 200000, "superficie_m2": 100},
        {"activa": True, "tipo_propiedad": "piso", "precio": 300000, "superficie_m2": 100},
        {"activa": False, "tipo_propiedad": "piso", "precio": 999999, "superficie_m2": 100},
        {"activa": True, "tipo_propiedad": "casa", "precio": 400000, "superficie_m2": 200},
    ]
    resultado = listing_precio_m2_medio_por_tipo(props)
    assert resultado["piso"] == 2500.0
    assert resultado["casa"] == 2000.0


def test_listing_precio_m2_medio_por_tipo_none_when_no_comparables():
    resultado = listing_precio_m2_medio_por_tipo([])
    assert resultado["piso"] is None
    assert resultado["casa"] is None


# ── tabla_comparativa ─────────────────────────────────────────────────────

def test_tabla_comparativa_delta_is_listing_minus_official():
    rows = [_row(property_type="piso", construction_type="obra_nueva", current_price_per_sqm=2500.0)]
    latest = latest_por_combo(notarial_to_df(rows))
    tabla = tabla_comparativa(latest, {"piso": 2800.0, "casa": None})
    fila = tabla.iloc[0]
    assert fila["precio_m2_oficial"] == 2500.0
    assert fila["precio_m2_mercado"] == 2800.0
    assert fila["diferencia"] == 300.0


def test_tabla_comparativa_none_when_no_market_comparable():
    rows = [_row(property_type="casa", construction_type="segunda_mano", current_price_per_sqm=1800.0)]
    latest = latest_por_combo(notarial_to_df(rows))
    tabla = tabla_comparativa(latest, {"piso": 2800.0, "casa": None})
    assert tabla.iloc[0]["diferencia"] is None


def test_tabla_comparativa_empty_latest_df_returns_empty_with_columns():
    tabla = tabla_comparativa(pd.DataFrame(), {"piso": None, "casa": None})
    assert tabla.empty
    assert "diferencia" in tabla.columns


def test_combos_has_four_fixed_combinations():
    assert COMBOS == [
        ("piso", "obra_nueva"),
        ("piso", "segunda_mano"),
        ("casa", "obra_nueva"),
        ("casa", "segunda_mano"),
    ]


# ── serie_mensual (genérica, con dropna por métrica) ─────────────────────

def test_serie_mensual_filters_by_combo_sorts_and_drops_nulls():
    rows = [
        _row(current_number_of_sales=12, last_data_update=datetime(2026, 3, 1)),
        _row(current_number_of_sales=None, last_data_update=datetime(2026, 2, 1)),
        _row(current_number_of_sales=8, last_data_update=datetime(2026, 1, 1)),
        _row(property_type="casa", current_number_of_sales=99, last_data_update=datetime(2026, 1, 15)),
    ]
    df = notarial_to_df(rows)
    serie = serie_mensual(df, "piso", "obra_nueva", "current_number_of_sales")
    assert list(serie["current_number_of_sales"]) == [8, 12]


def test_serie_mensual_empty_df_returns_empty():
    assert serie_mensual(pd.DataFrame(), "piso", "obra_nueva", "current_average_price").empty


def test_serie_temporal_is_alias_of_serie_mensual_precio_m2():
    rows = [_row(current_price_per_sqm=2000.0)]
    df = notarial_to_df(rows)
    pd.testing.assert_frame_equal(
        serie_temporal(df, "piso", "obra_nueva").reset_index(drop=True),
        serie_mensual(df, "piso", "obra_nueva", "current_price_per_sqm").reset_index(drop=True),
    )


# ── serie_mensual_total (agregada entre combos) ───────────────────────────

def test_serie_mensual_total_sums_across_combos_by_month():
    rows = [
        _row(property_type="piso", construction_type="obra_nueva",
             current_number_of_sales=10, last_data_update=datetime(2026, 1, 1)),
        _row(property_type="piso", construction_type="segunda_mano",
             current_number_of_sales=5, last_data_update=datetime(2026, 1, 1)),
        _row(property_type="casa", construction_type="segunda_mano",
             current_number_of_sales=3, last_data_update=datetime(2026, 2, 1)),
    ]
    df = notarial_to_df(rows)
    total = serie_mensual_total(df, "current_number_of_sales", agg="sum")
    assert total["current_number_of_sales"].tolist() == [15, 3]


def test_serie_mensual_total_mean_aggregation():
    rows = [
        _row(property_type="piso", construction_type="obra_nueva",
             current_price_per_sqm=2000.0, last_data_update=datetime(2026, 1, 1)),
        _row(property_type="piso", construction_type="segunda_mano",
             current_price_per_sqm=3000.0, last_data_update=datetime(2026, 1, 1)),
    ]
    df = notarial_to_df(rows)
    total = serie_mensual_total(df, "current_price_per_sqm", agg="mean")
    assert total["current_price_per_sqm"].tolist() == [2500.0]


def test_serie_mensual_total_empty_df_returns_empty():
    assert serie_mensual_total(pd.DataFrame(), "current_number_of_sales").empty


def test_serie_mensual_total_all_null_returns_empty():
    rows = [_row(current_number_of_sales=None)]
    df = notarial_to_df(rows)
    assert serie_mensual_total(df, "current_number_of_sales").empty


# ── delta_ultimo_periodo ──────────────────────────────────────────────────

def test_delta_ultimo_periodo_compares_last_two_values():
    serie = pd.DataFrame({
        "last_data_update": [datetime(2026, 1, 1), datetime(2026, 2, 1)],
        "current_number_of_sales": [10, 15],
    })
    d = delta_ultimo_periodo(serie, "current_number_of_sales")
    assert d == {
        "actual": 15, "anterior": 10, "delta_abs": 5, "delta_pct": 50.0, "direccion": "sube",
    }


def test_delta_ultimo_periodo_baja():
    serie = pd.DataFrame({
        "last_data_update": [datetime(2026, 1, 1), datetime(2026, 2, 1)],
        "current_price_per_sqm": [2000.0, 1800.0],
    })
    d = delta_ultimo_periodo(serie, "current_price_per_sqm")
    assert d["direccion"] == "baja"
    assert d["delta_abs"] == -200.0


def test_delta_ultimo_periodo_single_value_sin_comparacion():
    serie = pd.DataFrame({
        "last_data_update": [datetime(2026, 1, 1)],
        "current_number_of_sales": [10],
    })
    d = delta_ultimo_periodo(serie, "current_number_of_sales")
    assert d["actual"] == 10
    assert d["anterior"] is None
    assert d["direccion"] == "sin_comparacion"


def test_delta_ultimo_periodo_empty_serie_sin_datos():
    serie = pd.DataFrame(columns=["last_data_update", "current_number_of_sales"])
    d = delta_ultimo_periodo(serie, "current_number_of_sales")
    assert d["direccion"] == "sin_datos"
    assert d["actual"] is None


# ── estado_comparacion_mercado ────────────────────────────────────────────

def test_estado_comparacion_mercado_favorable_cuando_mercado_mas_barato():
    assert estado_comparacion_mercado(-200.0, 2500.0) == "favorable"


def test_estado_comparacion_mercado_desfavorable_cuando_mercado_mas_caro():
    assert estado_comparacion_mercado(200.0, 2500.0) == "desfavorable"


def test_estado_comparacion_mercado_neutral_dentro_del_umbral():
    assert estado_comparacion_mercado(20.0, 2500.0) == "neutral"


def test_estado_comparacion_mercado_sin_datos_cuando_falta_info():
    assert estado_comparacion_mercado(None, 2500.0) == "sin_datos"
    assert estado_comparacion_mercado(100.0, None) == "sin_datos"


# ── es_fila_actual / solo_mensual / fila_actual_por_combo ─────────────────
#
# La API devuelve una fila "actual" (currentPricePerSqm/currentNumberOf
# Sales/...) que es un acumulado móvil de 12 meses, no el dato de un mes
# suelto — y puede compartir last_data_update con una fila mensual real del
# backfill. Solo la fila actual trae current_average_area_sqm/rate_price_
# change (el mapeo del backfill mensual nunca los rellena); es la única
# forma fiable de distinguirlas sin cambiar el esquema.

def test_es_fila_actual_true_solo_para_snapshot_con_area_o_tasa():
    rows = [
        _row(current_average_area_sqm=77.44, rate_price_change=-0.15),
        _row(current_average_area_sqm=None, rate_price_change=None, current_number_of_sales=0),
        _row(current_average_area_sqm=None, rate_price_change=-0.1, current_number_of_sales=1),
    ]
    df = notarial_to_df(rows)
    assert es_fila_actual(df).tolist() == [True, False, True]


def test_es_fila_actual_df_vacio():
    df = notarial_to_df([])
    assert es_fila_actual(df).tolist() == []


def test_solo_mensual_excluye_fila_actual_incluso_con_mismo_mes():
    rows = [
        _row(
            last_data_update=datetime(2026, 5, 1),
            current_average_area_sqm=77.44, rate_price_change=-0.15,
            current_number_of_sales=69,
        ),
        _row(
            last_data_update=datetime(2026, 5, 1),
            current_average_area_sqm=None, rate_price_change=None,
            current_number_of_sales=0,
        ),
        _row(
            last_data_update=datetime(2026, 4, 1),
            current_average_area_sqm=None, rate_price_change=None,
            current_number_of_sales=2,
        ),
    ]
    df = notarial_to_df(rows)
    mensual = solo_mensual(df)
    assert len(mensual) == 2
    assert mensual["current_average_area_sqm"].isna().all()
    assert sorted(mensual["current_number_of_sales"].tolist()) == [0, 2]


def test_fila_actual_por_combo_ignora_filas_mensuales_del_backfill():
    rows = [
        _row(
            last_data_update=datetime(2026, 5, 1),
            current_price_per_sqm=2145.61, current_average_area_sqm=77.44,
            rate_price_change=-0.15,
        ),
        _row(
            last_data_update=datetime(2026, 4, 1),
            current_price_per_sqm=2100.0, current_average_area_sqm=76.0,
            rate_price_change=-0.10,
        ),
        _row(
            last_data_update=datetime(2026, 5, 1),
            current_price_per_sqm=None, current_average_area_sqm=None,
            rate_price_change=None, current_number_of_sales=0,
        ),
    ]
    df = notarial_to_df(rows)
    actual = fila_actual_por_combo(df)
    assert len(actual) == 1
    assert actual.iloc[0]["current_price_per_sqm"] == 2145.61


# ── delta_meses_atras ──────────────────────────────────────────────────

def test_delta_meses_atras_compara_con_el_mes_calendario_correcto():
    serie = pd.DataFrame({
        "last_data_update": pd.to_datetime(["2025-12-01", "2026-01-01", "2026-02-01"]),
        "current_price_per_sqm": [2101.41, 2421.36, 2205.84],
    })
    d = delta_meses_atras(serie, "current_price_per_sqm", 1)
    assert d["actual"] == 2205.84
    assert d["comparado"] == 2421.36
    assert d["delta_pct"] == round(100 * (2205.84 - 2421.36) / 2421.36, 1)


def test_delta_meses_atras_none_cuando_el_mes_no_esta_en_la_serie():
    serie = pd.DataFrame({
        "last_data_update": pd.to_datetime(["2026-02-01"]),
        "current_price_per_sqm": [2205.84],
    })
    d = delta_meses_atras(serie, "current_price_per_sqm", 3)
    assert d["actual"] == 2205.84
    assert d["comparado"] is None
    assert d["delta_pct"] is None


def test_delta_meses_atras_serie_vacia():
    serie = pd.DataFrame(columns=["last_data_update", "current_price_per_sqm"])
    d = delta_meses_atras(serie, "current_price_per_sqm", 6)
    assert d["actual"] is None
    assert d["comparado"] is None

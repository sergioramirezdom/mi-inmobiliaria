"""Tests de la capa pura de estadísticas notariales (pestaña Notarial)."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pandas as pd

from ui.notarial_stats import (
    COMBOS,
    has_notarial_data,
    latest_por_combo,
    listing_precio_m2_medio_por_tipo,
    notarial_to_df,
    serie_temporal,
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

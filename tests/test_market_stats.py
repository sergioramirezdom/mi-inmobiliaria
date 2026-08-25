"""Tests de la capa pura de estadísticas de mercado (Estadísticas 2.0)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pandas as pd

from ui.market_stats import (
    MIN_ACTIVAS_BARRIO,
    OTROS,
    SIN_ZONA,
    hist_to_df,
    kpis_pulso,
    lectura_mercado,
    precio_m2_mediano_en,
    props_to_df,
    serie_mensual_precio_m2,
    serie_mensual_precio_m2_por_barrio,
    serie_mensual_ventas,
    serie_semanal_entradas,
    tabla_zonas,
)

NOW = datetime(2026, 7, 16, 12, 0, 0)


def _prop(**kw):
    base = dict(
        id=1, titulo="Piso", precio=150_000.0, precio_anterior=None,
        superficie_m2=100.0, habitaciones=3, tipo_propiedad="piso",
        barrio="Centro", municipio="El Puerto", origen_web="x.com",
        url_original="https://x.com/1", activa=True, favorita=False,
        descartada=False, fecha_scraping=NOW - timedelta(days=10), fecha_baja=None,
        fecha_publicacion=None,
    )
    base.update(kw)
    return base


def _hist(pid, precio, fecha):
    return {"propiedad_id": pid, "precio": precio, "fecha": fecha}


# ── props_to_df / hist_to_df ─────────────────────────────────────────

def test_props_to_df_precio_m2():
    df = props_to_df([_prop(precio=200_000, superficie_m2=100),
                      _prop(id=2, precio=None),
                      _prop(id=3, superficie_m2=0)])
    assert df.loc[df["id"] == 1, "precio_m2"].iloc[0] == 2000
    assert pd.isna(df.loc[df["id"] == 2, "precio_m2"].iloc[0])
    assert pd.isna(df.loc[df["id"] == 3, "precio_m2"].iloc[0])


def test_dfs_empty_safe():
    assert props_to_df([]).empty
    assert hist_to_df([]).empty
    assert list(hist_to_df([]).columns) == ["propiedad_id", "precio", "fecha"]


def test_props_to_df_deriva_fecha_listado():
    """props_to_df debe exponer `fecha_listado` (resolver: fecha_publicacion
    si está, si no fecha_scraping) para que las KPIs no lean fecha_scraping
    directamente."""
    props = [
        _prop(id=1, fecha_scraping=NOW - timedelta(days=5), fecha_publicacion=None),
        _prop(id=2, fecha_scraping=NOW - timedelta(days=5), fecha_publicacion=NOW - timedelta(days=50)),
    ]
    df = props_to_df(props)
    assert "fecha_listado" in df.columns
    assert df.loc[df["id"] == 1, "fecha_listado"].iloc[0] == df.loc[df["id"] == 1, "fecha_scraping"].iloc[0]
    assert df.loc[df["id"] == 2, "fecha_listado"].iloc[0] == pd.Timestamp(NOW - timedelta(days=50))


# ── kpis_pulso ───────────────────────────────────────────────────────

def test_kpi_nuevas_delta_30_vs_30():
    props = (
        [_prop(id=i, fecha_scraping=NOW - timedelta(days=5)) for i in range(1, 4)]      # 3 en ventana actual
        + [_prop(id=i, fecha_scraping=NOW - timedelta(days=45)) for i in range(4, 6)]   # 2 en anterior
        + [_prop(id=9, fecha_scraping=NOW - timedelta(days=100))]                        # fuera
    )
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["nuevas"] == {"valor": 3, "delta": 1}


def test_kpi_nuevas_usa_fecha_publicacion_corregida():
    """Una fecha_publicacion corregida fuera de la ventana actual excluye de
    'nuevas', aunque fecha_scraping esté dentro de los 30 días."""
    props = [
        _prop(id=1, fecha_scraping=NOW - timedelta(days=5), fecha_publicacion=NOW - timedelta(days=100)),
        _prop(id=2, fecha_scraping=NOW - timedelta(days=5)),  # sin corrección: cuenta
    ]
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["nuevas"]["valor"] == 1


def test_kpi_dias_mercado_usa_fecha_publicacion_corregida():
    props = [
        _prop(id=1, activa=False, fecha_scraping=NOW - timedelta(days=30),
              fecha_publicacion=NOW - timedelta(days=50), fecha_baja=NOW - timedelta(days=10)),  # 40 días reales
    ]
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["dias_mercado"]["valor"] == 40.0


def test_kpi_ventas_por_fecha_baja():
    props = [
        _prop(id=1, activa=False, fecha_baja=NOW - timedelta(days=3)),
        _prop(id=2, activa=False, fecha_baja=NOW - timedelta(days=40)),
        _prop(id=3, activa=False, fecha_baja=NOW - timedelta(days=41)),
        _prop(id=4),  # activa, no cuenta
    ]
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["ventas"] == {"valor": 1, "delta": -1}


def test_kpi_bajadas_cuenta_descensos_en_ventana():
    hist = [
        _hist(1, 100_000, NOW - timedelta(days=50)),
        _hist(1, 95_000, NOW - timedelta(days=10)),   # descenso dentro de 30d
        _hist(2, 80_000, NOW - timedelta(days=20)),
        _hist(2, 85_000, NOW - timedelta(days=5)),    # subida: no cuenta
        _hist(3, 70_000, NOW - timedelta(days=70)),
        _hist(3, 60_000, NOW - timedelta(days=40)),   # descenso en ventana anterior
    ]
    k = kpis_pulso(props_to_df([_prop(id=1), _prop(id=2), _prop(id=3)]), hist_to_df(hist), NOW)
    assert k["bajadas"] == {"valor": 1, "delta": 0}


def test_kpi_dias_mercado_mediano():
    props = [
        _prop(id=1, activa=False, fecha_scraping=NOW - timedelta(days=30), fecha_baja=NOW - timedelta(days=10)),  # 20 días
        _prop(id=2, activa=False, fecha_scraping=NOW - timedelta(days=50), fecha_baja=NOW - timedelta(days=10)),  # 40 días
    ]
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["dias_mercado"]["valor"] == 30.0
    assert k["dias_mercado"]["delta"] is None  # sin ventas en ventana anterior


def test_kpis_df_vacio():
    k = kpis_pulso(props_to_df([]), hist_to_df([]), NOW)
    assert k["nuevas"]["valor"] == 0
    assert k["precio_m2"]["valor"] is None
    assert k["dias_mercado"]["valor"] is None


# ── precio_m2_mediano_en ─────────────────────────────────────────────

def test_precio_m2_reconstruido_usa_ultimo_precio_previo():
    props = [_prop(id=1, superficie_m2=100, fecha_scraping=NOW - timedelta(days=90))]
    hist = [
        _hist(1, 200_000, NOW - timedelta(days=90)),
        _hist(1, 180_000, NOW - timedelta(days=40)),
        _hist(1, 150_000, NOW - timedelta(days=5)),  # posterior a la fecha pedida
    ]
    v = precio_m2_mediano_en(props_to_df(props), hist_to_df(hist), NOW - timedelta(days=30))
    assert v == 1800.0


def test_precio_m2_reconstruido_excluye_vendidas_a_fecha():
    props = [_prop(id=1, superficie_m2=100, fecha_scraping=NOW - timedelta(days=90),
                   activa=False, fecha_baja=NOW - timedelta(days=60))]
    hist = [_hist(1, 200_000, NOW - timedelta(days=80))]
    assert precio_m2_mediano_en(props_to_df(props), hist_to_df(hist), NOW - timedelta(days=30)) is None


# ── series ───────────────────────────────────────────────────────────

def test_serie_semanal_doce_filas_con_ceros():
    df = props_to_df([_prop(id=1, fecha_scraping=NOW - timedelta(days=2))])
    s = serie_semanal_entradas(df, NOW, semanas=12)
    assert len(s) == 12
    assert s["nuevas"].sum() == 1
    assert (s["nuevas"] >= 0).all()


def test_serie_semanal_usa_fecha_publicacion_corregida():
    """Una entrada con fecha_publicacion corregida fuera de las 12 semanas
    mostradas no debe contarse, aunque fecha_scraping caiga dentro."""
    props = [_prop(id=1, fecha_scraping=NOW - timedelta(days=2), fecha_publicacion=NOW - timedelta(days=200))]
    s = serie_semanal_entradas(props_to_df(props), NOW, semanas=12)
    assert s["nuevas"].sum() == 0


def test_serie_mensual_ventas():
    props = [
        _prop(id=1, activa=False, fecha_baja=datetime(2026, 5, 10)),
        _prop(id=2, activa=False, fecha_baja=datetime(2026, 5, 20)),
        _prop(id=3, activa=False, fecha_baja=datetime(2026, 6, 1)),
    ]
    s = serie_mensual_ventas(props_to_df(props))
    assert s.to_dict("records") == [
        {"mes": "2026-05", "ventas": 2},
        {"mes": "2026-06", "ventas": 1},
    ]


def test_serie_mensual_precio_m2_ultimo_precio_del_mes():
    props = [_prop(id=1, superficie_m2=100)]
    hist = [
        _hist(1, 200_000, datetime(2026, 6, 5)),
        _hist(1, 180_000, datetime(2026, 6, 25)),  # último de junio
    ]
    s = serie_mensual_precio_m2(props_to_df(props), hist_to_df(hist))
    fila = s[s["mes"] == "2026-06"].iloc[0]
    assert fila["precio_m2"] == 1800.0
    assert fila["n"] == 1


def test_serie_por_barrio_asigna_sin_zona():
    props = [_prop(id=1, barrio=None, superficie_m2=100)]
    hist = [_hist(1, 100_000, datetime(2026, 6, 5))]
    s = serie_mensual_precio_m2_por_barrio(props_to_df(props), hist_to_df(hist))
    assert s.iloc[0]["barrio"] == SIN_ZONA


# ── tabla_zonas ──────────────────────────────────────────────────────

def test_tabla_zonas_agrupa_pequenos_en_otros():
    props = (
        [_prop(id=i, barrio="Centro") for i in range(1, 4)]        # 3 activas -> se queda
        + [_prop(id=10, barrio="Chico"), _prop(id=11, barrio="Chico")]  # 2 activas -> Otros
        + [_prop(id=20, barrio=None)]                               # Sin zona
    )
    t = tabla_zonas(props_to_df(props), hist_to_df([]), NOW)
    barrios = set(t["barrio"])
    assert "Centro" in barrios and OTROS in barrios and SIN_ZONA in barrios
    assert "Chico" not in barrios
    assert int(t[t["barrio"] == "Centro"]["activas"].iloc[0]) == 3
    assert int(t[t["barrio"] == OTROS]["activas"].iloc[0]) == 2


def test_tabla_zonas_metricas_basicas():
    props = [
        _prop(id=1, barrio="Centro", precio=100_000, superficie_m2=100),
        _prop(id=2, barrio="Centro", precio=200_000, superficie_m2=100, precio_anterior=220_000.0),
        _prop(id=3, barrio="Centro", precio=300_000, superficie_m2=100),
        _prop(id=4, barrio="Centro", activa=False,
              fecha_scraping=NOW - timedelta(days=30), fecha_baja=NOW - timedelta(days=10)),
    ]
    t = tabla_zonas(props_to_df(props), hist_to_df([]), NOW)
    fila = t[t["barrio"] == "Centro"].iloc[0]
    assert fila["activas"] == 3
    assert fila["precio_mediano"] == 200_000
    assert fila["precio_m2_mediano"] == 2000
    assert fila["vendidas_6m"] == 1
    assert fila["dias_mercado"] == 20
    assert abs(fila["pct_bajada"] - 33.3) < 0.1


def test_tabla_zonas_tendencia_90_vs_90():
    props = [_prop(id=i, barrio="Centro", superficie_m2=100) for i in range(1, 4)]
    hist = (
        [_hist(i, 220_000, NOW - timedelta(days=120)) for i in range(1, 4)]  # ventana anterior: 2200 €/m²
        + [_hist(i, 200_000, NOW - timedelta(days=30)) for i in range(1, 4)]  # actual: 2000 €/m²
    )
    t = tabla_zonas(props_to_df(props), hist_to_df(hist), NOW)
    tendencia = t[t["barrio"] == "Centro"]["tendencia_pct"].iloc[0]
    assert abs(tendencia - (-9.1)) < 0.1


def test_tabla_zonas_tendencia_none_sin_datos():
    props = [_prop(id=i, barrio="Centro") for i in range(1, 4)]
    t = tabla_zonas(props_to_df(props), hist_to_df([]), NOW)
    assert t[t["barrio"] == "Centro"]["tendencia_pct"].iloc[0] is None


# ── lectura_mercado ──────────────────────────────────────────────────

def test_lectura_mercado_comprador():
    kpis = {
        "nuevas": {"valor": 10, "delta": 5},
        "bajadas": {"valor": 4, "delta": 2},
        "dias_mercado": {"valor": 60, "delta": 10},
        "precio_m2": {"valor": 1800, "delta": -50},
        "ventas": {"valor": 1, "delta": -1},
    }
    assert "enfría" in lectura_mercado(kpis)


def test_lectura_mercado_sin_datos():
    kpis = {k: {"valor": None, "delta": None} for k in ["nuevas", "ventas", "precio_m2", "bajadas", "dias_mercado"]}
    assert "Sin cambios" in lectura_mercado(kpis)

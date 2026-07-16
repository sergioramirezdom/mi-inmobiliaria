"""Tests del asistente de ofertas (Estadísticas 2.0)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from ui.offer_advisor import (
    MIN_COMPARABLES,
    NIVELES,
    calcular_ajustes,
    campos_faltantes,
    rango_oferta,
    seleccionar_comparables,
    valorar,
)

NOW = datetime(2026, 7, 16, 12, 0, 0)


def _prop(**kw):
    base = dict(
        id=1, titulo="Piso", precio=150_000.0, precio_anterior=None,
        superficie_m2=100.0, habitaciones=3, tipo_propiedad="piso",
        barrio="Centro", municipio="El Puerto", origen_web="x.com",
        url_original="https://x.com/1", activa=True, favorita=False,
        descartada=False, fecha_scraping=NOW - timedelta(days=10), fecha_baja=None,
    )
    base.update(kw)
    return base


FAV = _prop(id=100, favorita=True, precio=200_000.0, superficie_m2=100.0)


def _universo_nivel1(n=4, **kw):
    """n comparables válidos de nivel 1 (mismo barrio, tipo y superficie)."""
    return [_prop(id=i, precio=150_000.0, superficie_m2=100.0, **kw) for i in range(1, n + 1)]


# ── campos_faltantes ─────────────────────────────────────────────────

def test_campos_faltantes():
    assert campos_faltantes(FAV) == {"imprescindibles": [], "mejora": []}
    sin_datos = _prop(id=5, precio=None, superficie_m2=None, barrio=None, tipo_propiedad=None)
    faltan = campos_faltantes(sin_datos)
    assert faltan["imprescindibles"] == ["precio", "superficie_m2"]
    assert faltan["mejora"] == ["barrio", "tipo_propiedad"]


# ── seleccionar_comparables ──────────────────────────────────────────

def test_nivel_1_con_minimo():
    comps, nivel = seleccionar_comparables(FAV, _universo_nivel1(4), NOW)
    assert nivel == 1
    assert len(comps) == 4


def test_excluye_la_propia_favorita():
    universo = _universo_nivel1(4) + [dict(FAV)]
    comps, _ = seleccionar_comparables(FAV, universo, NOW)
    assert all(c["id"] != FAV["id"] for c in comps)


def test_filtro_superficie_40_pct():
    universo = _universo_nivel1(4) + [
        _prop(id=50, superficie_m2=139.0),  # dentro (±40 de 100)
        _prop(id=51, superficie_m2=141.0),  # fuera
        _prop(id=52, superficie_m2=59.0),   # fuera
    ]
    comps, _ = seleccionar_comparables(FAV, universo, NOW)
    ids = {c["id"] for c in comps}
    assert 50 in ids and 51 not in ids and 52 not in ids


def test_vendidas_solo_ultimos_180_dias():
    universo = _universo_nivel1(4) + [
        _prop(id=60, activa=False, fecha_baja=NOW - timedelta(days=100)),  # entra
        _prop(id=61, activa=False, fecha_baja=NOW - timedelta(days=200)),  # fuera
        _prop(id=62, activa=False, fecha_baja=None),                        # fuera
    ]
    comps, _ = seleccionar_comparables(FAV, universo, NOW)
    ids = {c["id"] for c in comps}
    assert 60 in ids and 61 not in ids and 62 not in ids


def test_cascada_a_nivel_2_sin_tipo():
    universo = (
        [_prop(id=i, tipo_propiedad="piso") for i in range(1, 3)]      # solo 2 de nivel 1
        + [_prop(id=i, tipo_propiedad="casa") for i in range(3, 6)]    # 3 más de nivel 2
    )
    comps, nivel = seleccionar_comparables(FAV, universo, NOW)
    assert nivel == 2
    assert len(comps) == 5


def test_cascada_a_municipio_sin_barrio():
    fav_sin_barrio = _prop(id=100, precio=200_000.0, barrio=None)
    universo = [_prop(id=i, barrio="Cualquiera") for i in range(1, 5)]
    comps, nivel = seleccionar_comparables(fav_sin_barrio, universo, NOW)
    assert nivel == 3
    assert len(comps) == 4


def test_pocos_comparables_devuelve_nivel_mas_especifico():
    universo = [_prop(id=1), _prop(id=2)]  # solo 2 de nivel 1
    comps, nivel = seleccionar_comparables(FAV, universo, NOW)
    assert nivel == 1
    assert len(comps) == 2


def test_sin_comparables():
    comps, nivel = seleccionar_comparables(FAV, [], NOW)
    assert comps == [] and nivel is None


def test_comparables_sin_precio_o_superficie_excluidos():
    universo = _universo_nivel1(4) + [_prop(id=70, precio=None), _prop(id=71, superficie_m2=None)]
    comps, _ = seleccionar_comparables(FAV, universo, NOW)
    ids = {c["id"] for c in comps}
    assert 70 not in ids and 71 not in ids


# ── valorar ──────────────────────────────────────────────────────────

def test_valorar_mediana():
    comps = [
        _prop(id=1, precio=100_000, superficie_m2=100),  # 1000 €/m²
        _prop(id=2, precio=150_000, superficie_m2=100),  # 1500
        _prop(id=3, precio=200_000, superficie_m2=100),  # 2000
    ]
    v = valorar(FAV, comps)
    assert v["precio_m2_mediano"] == 1500
    assert v["valor_estimado"] == 150_000
    assert v["n"] == 3


# ── calcular_ajustes ─────────────────────────────────────────────────

def test_ajuste_dias_mercado_con_tope():
    fav = _prop(id=100, precio=200_000.0, fecha_scraping=NOW - timedelta(days=400))
    comps = [
        _prop(id=1, activa=False,
              fecha_scraping=NOW - timedelta(days=100), fecha_baja=NOW - timedelta(days=70)),  # 30 días
    ] + _universo_nivel1(3)
    ajustes = calcular_ajustes(fav, comps, NOW)
    dias = next(a for a in ajustes if a["concepto"] == "Tiempo en mercado")
    assert dias["pct"] == -5.0  # exceso 370 días -> 12*(-1%) pero tope -5%


def test_ajuste_dias_sin_vendidas_referencia_no_aplica():
    ajustes = calcular_ajustes(FAV, _universo_nivel1(4), NOW)  # todas activas
    dias = next(a for a in ajustes if a["concepto"] == "Tiempo en mercado")
    assert dias["pct"] == 0.0
    assert "no aplica" in dias["detalle"]


def test_ajuste_bajada_previa():
    fav = _prop(id=100, precio=190_000.0, precio_anterior=200_000.0, superficie_m2=100.0)
    ajustes = calcular_ajustes(fav, _universo_nivel1(4), NOW)
    bajada = next(a for a in ajustes if a["concepto"] == "Bajada previa")
    assert bajada["pct"] == -2.0


def test_sobreprecio_es_argumento_sin_descuento():
    fav = _prop(id=100, precio=300_000.0, superficie_m2=100.0)  # 3000 €/m² vs 1500 de comps
    ajustes = calcular_ajustes(fav, _universo_nivel1(4), NOW)
    sobre = next(a for a in ajustes if a["concepto"] == "Sobreprecio vs comparables")
    assert sobre["pct"] == 0.0
    assert "100" in sobre["detalle"]  # 100% por encima


def test_sin_sobreprecio_no_hay_linea():
    fav = _prop(id=100, precio=100_000.0, superficie_m2=100.0)  # 1000 €/m² < mediana
    ajustes = calcular_ajustes(fav, _universo_nivel1(4), NOW)
    assert not any(a["concepto"] == "Sobreprecio vs comparables" for a in ajustes)


# ── rango_oferta ─────────────────────────────────────────────────────

def test_rango_maximo_es_min_estimado_anunciado():
    r = rango_oferta(FAV, valor_estimado=250_000, ajustes=[])
    assert r["maximo_razonable"] == 200_000  # el precio anunciado es menor
    r2 = rango_oferta(FAV, valor_estimado=150_000, ajustes=[])
    assert r2["maximo_razonable"] == 150_000


def test_rango_aplica_descuentos():
    ajustes = [
        {"concepto": "Tiempo en mercado", "pct": -3.0, "detalle": ""},
        {"concepto": "Bajada previa", "pct": -2.0, "detalle": ""},
    ]
    r = rango_oferta(FAV, valor_estimado=150_000, ajustes=ajustes)
    assert r["descuento_total_pct"] == 5.0
    assert r["oferta_inicial"] == 142_500  # 150000 * 0.95
    assert r["maximo_razonable"] == 150_000

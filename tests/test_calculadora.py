import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from utils.calculadora import (
    calcular_compraventa,
    calcular_gastos_hipoteca,
    calcular_aportacion_necesaria,
    calcular_hipoteca,
)


def test_calcular_compraventa_sin_agencia():
    r = calcular_compraventa(
        precio=200_000,
        itp_pct=7.0,
        notaria=700,
        registro=350,
        agencia_pct=0.0,
    )
    assert r["itp_importe"] == 14_000.0
    assert r["agencia_importe"] == 0.0
    assert r["total_a"] == 15_050.0  # 14000 + 700 + 350


def test_calcular_compraventa_con_agencia():
    r = calcular_compraventa(
        precio=200_000,
        itp_pct=6.0,
        notaria=700,
        registro=350,
        agencia_pct=3.0,
    )
    assert r["itp_importe"] == 12_000.0
    assert r["agencia_importe"] == 6_000.0
    assert r["total_a"] == 19_050.0  # 12000 + 700 + 350 + 6000


def test_calcular_gastos_hipoteca():
    r = calcular_gastos_hipoteca(
        prestamo=160_000,
        comision_apertura=0,
        gestoria=350,
        tasacion=450,
        registro_hip=0,
        ajd_pct=1.0,
    )
    assert r["ajd_importe"] == 1_600.0
    assert r["total_b"] == 2_400.0  # 0 + 350 + 450 + 0 + 1600


def test_calcular_aportacion_necesaria_80():
    aportacion = calcular_aportacion_necesaria(
        precio=200_000,
        financiacion_pct=80.0,
        total_gastos_a=15_050,
        total_gastos_b=2_400,
    )
    # banco_financia = 160000, comprador pone 40000 + gastos
    assert aportacion == 57_450.0  # 40000 + 15050 + 2400


def test_calcular_hipoteca_cuota():
    r = calcular_hipoteca(
        prestamo=160_000,
        tipo_interes_final=3.0,
        plazo_anos=30,
    )
    # cuota conocida para 160k al 3% a 30 años ≈ 674.4€
    assert 670 < r["cuota_mensual"] < 680
    assert r["total_pagado"] > r["prestamo"]
    assert r["total_intereses"] == round(r["total_pagado"] - r["prestamo"], 2)
    assert 0 < r["pct_intereses"] < 100


def test_calcular_hipoteca_tipo_cero():
    # Con tipo 0%, cuota = prestamo / n
    r = calcular_hipoteca(prestamo=120_000, tipo_interes_final=0.0, plazo_anos=10)
    assert r["cuota_mensual"] == round(120_000 / 120, 2)
    assert r["total_intereses"] == 0.0

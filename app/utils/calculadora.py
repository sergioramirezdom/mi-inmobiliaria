"""Lógica pura de cálculo financiero para compraventa e hipoteca."""

from typing import Dict, List


def calcular_compraventa(
    precio: float,
    itp_pct: float,
    notaria: float,
    registro: float,
    agencia_pct: float,
) -> Dict[str, float]:
    """Calcula los gastos del bloque A (compraventa)."""
    itp_importe = precio * itp_pct / 100
    agencia_importe = precio * agencia_pct / 100
    total_a = itp_importe + notaria + registro + agencia_importe
    return {
        "itp_importe": round(itp_importe, 2),
        "agencia_importe": round(agencia_importe, 2),
        "notaria": round(notaria, 2),
        "registro": round(registro, 2),
        "total_a": round(total_a, 2),
    }


def calcular_gastos_hipoteca(
    prestamo: float,
    comision_apertura: float,
    gestoria: float,
    tasacion: float,
    registro_hip: float,
    ajd_pct: float,
) -> Dict[str, float]:
    """Calcula los gastos del bloque B (préstamo hipotecario)."""
    ajd_importe = prestamo * ajd_pct / 100
    total_b = comision_apertura + gestoria + tasacion + registro_hip + ajd_importe
    return {
        "comision_apertura": round(comision_apertura, 2),
        "gestoria": round(gestoria, 2),
        "tasacion": round(tasacion, 2),
        "registro_hip": round(registro_hip, 2),
        "ajd_importe": round(ajd_importe, 2),
        "total_b": round(total_b, 2),
    }


def calcular_aportacion_necesaria(
    precio: float,
    financiacion_pct: float,
    total_gastos_a: float,
    total_gastos_b: float,
) -> float:
    """
    Calcula la aportación mínima necesaria dado un % de financiación.
    aportacion = (precio no financiado) + total gastos A + total gastos B
    """
    banco_financia = precio * financiacion_pct / 100
    aportacion = (precio - banco_financia) + total_gastos_a + total_gastos_b
    return round(aportacion, 2)


def calcular_hipoteca(
    prestamo: float,
    tipo_interes_final: float,
    plazo_anos: int,
) -> Dict:
    """
    Amortización francesa.
    Devuelve cuota mensual, total pagado, total intereses y tabla de amortización.
    """
    n = plazo_anos * 12

    if tipo_interes_final <= 0:
        cuota = round(prestamo / n, 2)
        return {
            "cuota_mensual": cuota,
            "total_pagado": round(cuota * n, 2),
            "total_intereses": 0.0,
            "pct_intereses": 0.0,
            "prestamo": prestamo,
            "tabla": _tabla_amortizacion(prestamo, 0.0, n, cuota),
        }

    tipo_mensual = tipo_interes_final / 12 / 100
    cuota = prestamo * (tipo_mensual * (1 + tipo_mensual) ** n) / ((1 + tipo_mensual) ** n - 1)
    cuota = round(cuota, 2)
    total_pagado = round(cuota * n, 2)
    total_intereses = round(total_pagado - prestamo, 2)
    pct_intereses = round(total_intereses / prestamo * 100, 1)

    return {
        "cuota_mensual": cuota,
        "total_pagado": total_pagado,
        "total_intereses": total_intereses,
        "pct_intereses": pct_intereses,
        "prestamo": prestamo,
        "tabla": _tabla_amortizacion(prestamo, tipo_mensual, n, cuota),
    }


def _tabla_amortizacion(
    prestamo: float,
    tipo_mensual: float,
    n: int,
    cuota: float,
) -> List[Dict]:
    """Genera la tabla de amortización mes a mes."""
    filas = []
    saldo = prestamo
    for mes in range(1, n + 1):
        interes = round(saldo * tipo_mensual, 2)
        capital = round(cuota - interes, 2)
        saldo = round(max(saldo - capital, 0), 2)
        filas.append({
            "Mes": mes,
            "Cuota": cuota,
            "Capital": capital,
            "Intereses": interes,
            "Saldo pendiente": saldo,
        })
    return filas

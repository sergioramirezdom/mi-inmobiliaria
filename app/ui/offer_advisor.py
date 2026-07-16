"""Asistente de ofertas: comparables, valoración y rango sugerido.

Funciones puras sobre dicts con datetimes nativos. Sin Streamlit, BD ni Plotly.
Heurística transparente: cada ajuste lleva su justificación en texto.
"""

import statistics
from datetime import datetime, timedelta

VENTANA_VENDIDAS_DIAS = 180
MIN_COMPARABLES = 4
TOLERANCIA_SUPERFICIE = 0.4
TOPE_DIAS_PCT = 5.0
PCT_POR_30_DIAS = 1.0
PCT_BAJADA_PREVIA = 2.0

NIVELES = {
    1: "mismo barrio, mismo tipo y superficie ±40%",
    2: "mismo barrio y superficie ±40%",
    3: "mismo municipio, mismo tipo y superficie ±40%",
    4: "mismo municipio y superficie ±40%",
}


def campos_faltantes(favorita: dict) -> dict:
    """Campos ausentes que impiden (imprescindibles) o degradan (mejora) la valoración."""
    return {
        "imprescindibles": [c for c in ("precio", "superficie_m2") if not favorita.get(c)],
        "mejora": [c for c in ("barrio", "tipo_propiedad") if not favorita.get(c)],
    }


def _es_candidato(p: dict, favorita: dict, now: datetime) -> bool:
    if p["id"] == favorita["id"]:
        return False
    if not p.get("precio") or not p.get("superficie_m2"):
        return False
    if p.get("activa"):
        return True
    fb = p.get("fecha_baja")
    return fb is not None and fb >= now - timedelta(days=VENTANA_VENDIDAS_DIAS)


def _match_superficie(p: dict, favorita: dict) -> bool:
    return abs(p["superficie_m2"] - favorita["superficie_m2"]) <= TOLERANCIA_SUPERFICIE * favorita["superficie_m2"]


def seleccionar_comparables(favorita: dict, universo: list, now: datetime):
    """(comparables, nivel 1-4). Primer nivel con >= MIN_COMPARABLES; si ninguno llega,
    el nivel más específico con al menos 1; ([], None) si no hay nada."""
    candidatos = [p for p in universo if _es_candidato(p, favorita, now) and _match_superficie(p, favorita)]

    def filtro(nivel: int) -> list:
        out = []
        for p in candidatos:
            if nivel in (1, 2) and (not favorita.get("barrio") or p.get("barrio") != favorita["barrio"]):
                continue
            if nivel in (3, 4) and (not favorita.get("municipio") or p.get("municipio") != favorita["municipio"]):
                continue
            if nivel in (1, 3) and (not favorita.get("tipo_propiedad") or p.get("tipo_propiedad") != favorita["tipo_propiedad"]):
                continue
            out.append(p)
        return out

    por_nivel = {n: filtro(n) for n in (1, 2, 3, 4)}
    for n in (1, 2, 3, 4):
        if len(por_nivel[n]) >= MIN_COMPARABLES:
            return por_nivel[n], n
    for n in (1, 2, 3, 4):
        if por_nivel[n]:
            return por_nivel[n], n
    return [], None


def _mediana_m2(comparables: list) -> float:
    return statistics.median(p["precio"] / p["superficie_m2"] for p in comparables)


def valorar(favorita: dict, comparables: list) -> dict:
    """Valor estimado = €/m² mediano de comparables × superficie de la favorita."""
    mediana = _mediana_m2(comparables)
    return {
        "precio_m2_mediano": round(mediana, 2),
        "valor_estimado": round(mediana * favorita["superficie_m2"]),
        "n": len(comparables),
    }


def calcular_ajustes(favorita: dict, comparables: list, now: datetime) -> list:
    """Ajustes de presión, cada uno con concepto, pct (<= 0) y detalle justificado."""
    ajustes = []

    dias_fav = (now - favorita["fecha_scraping"]).days if favorita.get("fecha_scraping") else None
    vendidos = [
        c for c in comparables
        if not c.get("activa") and c.get("fecha_baja") and c.get("fecha_scraping")
    ]
    if dias_fav is not None and vendidos:
        ref = statistics.median((c["fecha_baja"] - c["fecha_scraping"]).days for c in vendidos)
        exceso = dias_fav - ref
        if exceso >= 30:
            pct = -min(PCT_POR_30_DIAS * (exceso // 30), TOPE_DIAS_PCT)
            ajustes.append({
                "concepto": "Tiempo en mercado", "pct": float(pct),
                "detalle": (
                    f"Lleva {dias_fav} días anunciada y las vendidas comparables tardaron "
                    f"{ref:.0f} días (mediana): {exceso:.0f} días de exceso."
                ),
            })
        else:
            ajustes.append({
                "concepto": "Tiempo en mercado", "pct": 0.0,
                "detalle": f"Lleva {dias_fav} días anunciada, dentro de lo normal de su zona ({ref:.0f} días de mediana).",
            })
    elif dias_fav is not None:
        ajustes.append({
            "concepto": "Tiempo en mercado", "pct": 0.0,
            "detalle": f"Lleva {dias_fav} días anunciada; sin vendidas comparables de referencia, este ajuste no aplica.",
        })

    if favorita.get("precio_anterior") and favorita.get("precio") and favorita["precio_anterior"] > favorita["precio"]:
        bajada_pct = 100 * (favorita["precio_anterior"] - favorita["precio"]) / favorita["precio_anterior"]
        ajustes.append({
            "concepto": "Bajada previa", "pct": -PCT_BAJADA_PREVIA,
            "detalle": (
                f"Ya bajó un {bajada_pct:.1f}% (de {favorita['precio_anterior']:,.0f} € a "
                f"{favorita['precio']:,.0f} €): el vendedor está dispuesto a mover el precio."
            ),
        })

    mediana_m2 = _mediana_m2(comparables)
    m2_fav = favorita["precio"] / favorita["superficie_m2"]
    if m2_fav > mediana_m2:
        sobre = 100 * (m2_fav - mediana_m2) / mediana_m2
        ajustes.append({
            "concepto": "Sobreprecio vs comparables", "pct": 0.0,
            "detalle": (
                f"Su €/m² ({m2_fav:,.0f}) está un {sobre:.1f}% por encima de la mediana de "
                f"comparables ({mediana_m2:,.0f}). Úsalo como argumento: ya está descontado en el valor estimado."
            ),
        })
    return ajustes


def rango_oferta(favorita: dict, valor_estimado: float, ajustes: list) -> dict:
    """Máximo razonable = min(estimado, anunciado); oferta = máximo × (1 − descuentos)."""
    descuento_total = -sum(a["pct"] for a in ajustes)
    maximo = min(valor_estimado, favorita["precio"])
    return {
        "oferta_inicial": round(maximo * (1 - descuento_total / 100)),
        "maximo_razonable": round(maximo),
        "descuento_total_pct": round(descuento_total, 1),
    }


def decidir_vista(favorita: dict, universo: list, now) -> str:
    """Qué vista mostrar en la pestaña Ofertas: 'form_imprescindibles',
    'sin_comparables' o 'valoracion'. Pura — sin Streamlit."""
    faltan = campos_faltantes(favorita)
    if faltan["imprescindibles"]:
        return "form_imprescindibles"
    comparables, _ = seleccionar_comparables(favorita, universo, now)
    if not comparables:
        return "sin_comparables"
    return "valoracion"

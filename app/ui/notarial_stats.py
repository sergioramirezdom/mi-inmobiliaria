"""Cálculos puros para la pestaña Notarial de Estadísticas 2.0.

Sin Streamlit, sin BD, sin Plotly: entra una lista de dicts (filas de
`EstadisticaNotarial`), sale pandas. Mirroring de `ui/market_stats.py`.
"""

import pandas as pd

COMBOS = [
    ("piso", "obra_nueva"),
    ("piso", "segunda_mano"),
    ("casa", "obra_nueva"),
    ("casa", "segunda_mano"),
]

COMBO_LABELS = {
    ("piso", "obra_nueva"): "Piso · obra nueva",
    ("piso", "segunda_mano"): "Piso · segunda mano",
    ("casa", "obra_nueva"): "Casa · obra nueva",
    ("casa", "segunda_mano"): "Casa · segunda mano",
}


def has_notarial_data(rows: list) -> bool:
    """True si hay al menos una fila de estadística notarial almacenada.

    Helper puro usado por `render_notarial()` para decidir entre el
    estado vacío (sin datos aún) y el render con gráficos.
    """
    return bool(rows)


def notarial_to_df(rows: list) -> pd.DataFrame:
    """DataFrame de filas `EstadisticaNotarial` con fechas parseadas."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["last_data_update"] = pd.to_datetime(df["last_data_update"])
    df["report_date"] = pd.to_datetime(df["report_date"])
    return df


def latest_por_combo(df: pd.DataFrame) -> pd.DataFrame:
    """Última fila (por `last_data_update`) de cada combo property/construction."""
    if df.empty:
        return df
    return (
        df.sort_values("last_data_update")
        .groupby(["property_type", "construction_type"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def serie_mensual(
    df: pd.DataFrame, property_type: str, construction_type: str, columna: str
) -> pd.DataFrame:
    """Serie mensual ordenada de `columna` para un combo, sin meses con dato nulo.

    No todas las métricas tienen dato real cada mes (p.ej. `current_price_per_sqm`
    suele faltar en meses recientes sin transacciones cerradas todavía) — filtrar
    los nulos evita graficar ceros engañosos.
    """
    if df.empty:
        return df
    serie = df[
        (df["property_type"] == property_type)
        & (df["construction_type"] == construction_type)
    ].sort_values("last_data_update")
    return serie[["last_data_update", columna]].dropna(subset=[columna]).reset_index(drop=True)


def serie_temporal(df: pd.DataFrame, property_type: str, construction_type: str) -> pd.DataFrame:
    """Serie temporal ordenada de `current_price_per_sqm` para un combo."""
    return serie_mensual(df, property_type, construction_type, "current_price_per_sqm")


def serie_mensual_total(df: pd.DataFrame, columna: str, agg: str = "sum") -> pd.DataFrame:
    """Serie mensual de `columna` agregada (suma o media) entre los 4 combos.

    Útil para un total de mercado (p.ej. compraventas totales/mes = suma entre
    combos) o una media (p.ej. €/m² medio/mes entre obra nueva y segunda mano).
    Descarta filas con `columna` nula antes de agregar.
    """
    vacio = pd.DataFrame(columns=["last_data_update", columna])
    if df.empty:
        return vacio
    d = df.dropna(subset=[columna])
    if d.empty:
        return vacio
    return (
        d.groupby("last_data_update")[columna]
        .agg(agg)
        .reset_index()
        .sort_values("last_data_update")
        .reset_index(drop=True)
    )


def delta_ultimo_periodo(serie: pd.DataFrame, columna: str) -> dict:
    """Compara el último valor no nulo de `columna` con el anterior.

    `serie` debe venir ya filtrada/ordenada (p.ej. de `serie_mensual` o
    `serie_mensual_total`). `direccion` es "sube"|"baja"|"igual" cuando hay
    2+ puntos, "sin_comparacion" con 1 solo punto, "sin_datos" si está vacía.
    """
    resultado = {
        "actual": None, "anterior": None, "delta_abs": None,
        "delta_pct": None, "direccion": "sin_datos",
    }
    if serie.empty:
        return resultado
    valores = serie[columna].tolist()
    if len(valores) == 1:
        resultado["actual"] = valores[-1]
        resultado["direccion"] = "sin_comparacion"
        return resultado
    actual, anterior = valores[-1], valores[-2]
    delta_abs = actual - anterior
    delta_pct = round(100 * delta_abs / anterior, 1) if anterior else None
    direccion = "sube" if delta_abs > 0 else ("baja" if delta_abs < 0 else "igual")
    return {
        "actual": actual, "anterior": anterior, "delta_abs": delta_abs,
        "delta_pct": delta_pct, "direccion": direccion,
    }


def estado_comparacion_mercado(diferencia, oficial, umbral_pct: float = 3.0) -> str:
    """Clasifica `diferencia` (mercado − oficial) desde la perspectiva del comprador.

    Mercado más barato que el precio oficial notarial = "favorable" (margen para
    negociar); más caro = "desfavorable"; dentro de ±`umbral_pct`% = "neutral".
    """
    if diferencia is None or oficial is None or not oficial:
        return "sin_datos"
    pct = 100 * diferencia / oficial
    if pct <= -umbral_pct:
        return "favorable"
    if pct >= umbral_pct:
        return "desfavorable"
    return "neutral"


def listing_precio_m2_medio_por_tipo(props: list) -> dict:
    """€/m² medio de listados activos, agrupado por `tipo_propiedad` (piso|casa).

    Solo se comparan piso/casa (los dos `property_type` notariales); no hay
    equivalente de obra_nueva/segunda_mano en `Propiedad`, así que la
    comparación se hace a nivel municipio/tipo, no por combo completo.
    """
    resultado = {}
    for tipo in ("piso", "casa"):
        precios = [
            p["precio"] / p["superficie_m2"]
            for p in props
            if p.get("activa")
            and p.get("tipo_propiedad") == tipo
            and p.get("precio")
            and p.get("superficie_m2")
        ]
        resultado[tipo] = sum(precios) / len(precios) if precios else None
    return resultado


def tabla_comparativa(latest_df: pd.DataFrame, listing_por_tipo: dict) -> pd.DataFrame:
    """Tabla oficial vs mercado por combo. `diferencia = mercado - oficial`."""
    columnas = [
        "property_type", "construction_type",
        "precio_m2_oficial", "precio_m2_mercado", "diferencia",
    ]
    if latest_df.empty:
        return pd.DataFrame(columns=columnas)

    filas = []
    for _, row in latest_df.iterrows():
        oficial = row["current_price_per_sqm"]
        mercado = listing_por_tipo.get(row["property_type"])
        diferencia = (
            mercado - oficial
            if mercado is not None and oficial is not None
            else None
        )
        filas.append({
            "property_type": row["property_type"],
            "construction_type": row["construction_type"],
            "precio_m2_oficial": oficial,
            "precio_m2_mercado": mercado,
            "diferencia": diferencia,
        })
    return pd.DataFrame(filas, columns=columnas)

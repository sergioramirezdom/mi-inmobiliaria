"""Cálculos puros de mercado para Estadísticas 2.0.

Sin Streamlit, sin BD, sin Plotly: entra una lista de dicts, sale pandas.
"""

from datetime import datetime, timedelta

import pandas as pd

MIN_ACTIVAS_BARRIO = 3
OTROS = "Otros"
SIN_ZONA = "Sin zona"
VENTANA_VENDIDAS_DIAS = 180


def props_to_df(props: list) -> pd.DataFrame:
    """DataFrame de propiedades con fechas parseadas y precio_m2 calculado."""
    df = pd.DataFrame(props)
    if df.empty:
        return df
    df["fecha_scraping"] = pd.to_datetime(df["fecha_scraping"])
    df["fecha_baja"] = pd.to_datetime(df["fecha_baja"])
    df["precio_m2"] = df.apply(
        lambda r: r["precio"] / r["superficie_m2"]
        if pd.notna(r["precio"]) and pd.notna(r["superficie_m2"]) and r["superficie_m2"] > 0
        else None,
        axis=1,
    )
    return df


def hist_to_df(hist: list) -> pd.DataFrame:
    df = pd.DataFrame(hist)
    if df.empty:
        return pd.DataFrame(columns=["propiedad_id", "precio", "fecha"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


# ── KPIs de Pulso ─────────────────────────────────────────────────────

def _count_between(fechas: pd.Series, start, end) -> int:
    if fechas.empty:
        return 0
    return int(((fechas >= start) & (fechas < end)).sum())


def _bajadas_en_ventana(hist_df: pd.DataFrame, start, end) -> int:
    """Nº de propiedades con al menos un descenso de precio registrado en la ventana."""
    if hist_df.empty:
        return 0
    n = 0
    for _, grupo in hist_df.sort_values("fecha").groupby("propiedad_id"):
        precios = grupo["precio"].tolist()
        fechas = grupo["fecha"].tolist()
        if any(
            precios[i] < precios[i - 1] and start <= fechas[i] < end
            for i in range(1, len(precios))
        ):
            n += 1
    return n


def _dias_mercado_mediano(vendidas: pd.DataFrame, start, end):
    v = vendidas[(vendidas["fecha_baja"] >= start) & (vendidas["fecha_baja"] < end)]
    if v.empty:
        return None
    dias = (v["fecha_baja"] - v["fecha_scraping"]).dt.days.clip(lower=0)
    return float(dias.median())


def precio_m2_mediano_en(df: pd.DataFrame, hist_df: pd.DataFrame, fecha):
    """€/m² mediano reconstruido a una fecha: último precio registrado <= fecha por
    propiedad que existía y no estaba vendida a esa fecha, dividido por superficie."""
    if hist_df.empty or df.empty:
        return None
    vivas = df[
        (df["fecha_scraping"] <= fecha)
        & (df["fecha_baja"].isna() | (df["fecha_baja"] > fecha))
        & df["superficie_m2"].notna()
        & (df["superficie_m2"] > 0)
    ][["id", "superficie_m2"]]
    if vivas.empty:
        return None
    ultimos = hist_df[hist_df["fecha"] <= fecha].sort_values("fecha").groupby("propiedad_id").tail(1)
    m = ultimos.merge(vivas, left_on="propiedad_id", right_on="id")
    if m.empty:
        return None
    return float((m["precio"] / m["superficie_m2"]).median())


def kpis_pulso(df: pd.DataFrame, hist_df: pd.DataFrame, now: datetime) -> dict:
    """KPIs de los últimos 30 días con delta vs los 30 anteriores."""
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)

    if df.empty:
        return {
            "nuevas": {"valor": 0, "delta": None},
            "ventas": {"valor": 0, "delta": None},
            "precio_m2": {"valor": None, "delta": None},
            "bajadas": {"valor": _bajadas_en_ventana(hist_df, d30, now), "delta": None},
            "dias_mercado": {"valor": None, "delta": None},
        }

    out = {}
    n_act = _count_between(df["fecha_scraping"], d30, now)
    n_prev = _count_between(df["fecha_scraping"], d60, d30)
    out["nuevas"] = {"valor": n_act, "delta": n_act - n_prev}

    vendidas = df[(df["activa"] == False) & df["fecha_baja"].notna()]
    v_act = _count_between(vendidas["fecha_baja"], d30, now)
    v_prev = _count_between(vendidas["fecha_baja"], d60, d30)
    out["ventas"] = {"valor": v_act, "delta": v_act - v_prev}

    activas = df[df["activa"] == True]
    m2_hoy = activas["precio_m2"].dropna().median() if not activas.empty else None
    m2_hoy = None if m2_hoy is None or pd.isna(m2_hoy) else float(m2_hoy)
    m2_antes = precio_m2_mediano_en(df, hist_df, d30)
    delta_m2 = round(m2_hoy - m2_antes) if m2_hoy is not None and m2_antes is not None else None
    out["precio_m2"] = {"valor": round(m2_hoy) if m2_hoy is not None else None, "delta": delta_m2}

    b_act = _bajadas_en_ventana(hist_df, d30, now)
    b_prev = _bajadas_en_ventana(hist_df, d60, d30)
    out["bajadas"] = {"valor": b_act, "delta": b_act - b_prev}

    dm_act = _dias_mercado_mediano(vendidas, d30, now)
    dm_prev = _dias_mercado_mediano(vendidas, d60, d30)
    out["dias_mercado"] = {
        "valor": dm_act,
        "delta": (dm_act - dm_prev) if dm_act is not None and dm_prev is not None else None,
    }
    return out


def lectura_mercado(kpis: dict) -> str:
    """Frase interpretativa: cuenta señales a favor del comprador entre los deltas."""
    a_favor, total = 0, 0
    # (clave, subir favorece al comprador)
    for clave, sube_favorece in [
        ("nuevas", True), ("bajadas", True), ("dias_mercado", True),
        ("precio_m2", False), ("ventas", False),
    ]:
        delta = kpis.get(clave, {}).get("delta")
        if delta is None or delta == 0:
            continue
        total += 1
        if (delta > 0) == sube_favorece:
            a_favor += 1
    if total == 0:
        return "Sin cambios significativos en los últimos 30 días."
    if a_favor * 2 > total:
        return "El mercado se enfría: más margen para negociar y ofertar a la baja."
    if a_favor * 3 <= total:
        return "El mercado se calienta: menos margen de negociación, decide rápido."
    return "Señales mixtas: negocia caso por caso apoyándote en los comparables."


# ── Series temporales ─────────────────────────────────────────────────

def serie_semanal_entradas(df: pd.DataFrame, now: datetime, semanas: int = 12) -> pd.DataFrame:
    """Entradas nuevas por semana (fecha_scraping), exactamente `semanas` filas."""
    semana_actual = pd.Timestamp(now).to_period("W").start_time
    idx = pd.date_range(end=semana_actual, periods=semanas, freq="7D")
    if df.empty:
        return pd.DataFrame({"semana": idx, "nuevas": [0] * semanas})
    inicios = df["fecha_scraping"].dt.to_period("W").dt.start_time
    counts = inicios.value_counts()
    return pd.DataFrame({"semana": idx, "nuevas": [int(counts.get(s, 0)) for s in idx]})


def serie_mensual_ventas(df: pd.DataFrame) -> pd.DataFrame:
    """Ventas por mes (fecha_baja de inactivas), solo meses con ventas, cronológico."""
    if df.empty:
        return pd.DataFrame(columns=["mes", "ventas"])
    vendidas = df[(df["activa"] == False) & df["fecha_baja"].notna()]
    if vendidas.empty:
        return pd.DataFrame(columns=["mes", "ventas"])
    counts = vendidas["fecha_baja"].dt.to_period("M").astype(str).value_counts().sort_index()
    return pd.DataFrame({"mes": counts.index.tolist(), "ventas": counts.values.astype(int)})


def _ultimo_precio_por_mes(hist_df: pd.DataFrame) -> pd.DataFrame:
    """Último registro de precio de cada propiedad dentro de cada mes."""
    h = hist_df.copy()
    h["mes"] = h["fecha"].dt.to_period("M").astype(str)
    return h.sort_values("fecha").groupby(["propiedad_id", "mes"]).tail(1)


def _con_superficie(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["superficie_m2"].notna() & (df["superficie_m2"] > 0)]


def serie_mensual_precio_m2(df: pd.DataFrame, hist_df: pd.DataFrame) -> pd.DataFrame:
    """Mediana mensual de €/m² desde el historial (último precio del mes por propiedad)."""
    vacio = pd.DataFrame(columns=["mes", "precio_m2", "n"])
    if hist_df.empty or df.empty:
        return vacio
    sup = _con_superficie(df)[["id", "superficie_m2"]]
    m = _ultimo_precio_por_mes(hist_df).merge(sup, left_on="propiedad_id", right_on="id")
    if m.empty:
        return vacio
    m["precio_m2"] = m["precio"] / m["superficie_m2"]
    return (
        m.groupby("mes")
        .agg(precio_m2=("precio_m2", "median"), n=("propiedad_id", "nunique"))
        .reset_index()
        .sort_values("mes")
        .reset_index(drop=True)
    )


def serie_mensual_precio_m2_por_barrio(df: pd.DataFrame, hist_df: pd.DataFrame) -> pd.DataFrame:
    """Como serie_mensual_precio_m2 pero segmentada por barrio (NULL -> SIN_ZONA)."""
    vacio = pd.DataFrame(columns=["mes", "barrio", "precio_m2", "n"])
    if hist_df.empty or df.empty:
        return vacio
    sup = _con_superficie(df)[["id", "superficie_m2", "barrio"]].copy()
    sup["barrio"] = sup["barrio"].fillna(SIN_ZONA).replace("", SIN_ZONA)
    m = _ultimo_precio_por_mes(hist_df).merge(sup, left_on="propiedad_id", right_on="id")
    if m.empty:
        return vacio
    m["precio_m2"] = m["precio"] / m["superficie_m2"]
    return (
        m.groupby(["mes", "barrio"])
        .agg(precio_m2=("precio_m2", "median"), n=("propiedad_id", "nunique"))
        .reset_index()
        .sort_values(["mes", "barrio"])
        .reset_index(drop=True)
    )


# ── Zonas ─────────────────────────────────────────────────────────────

def _tendencia_barrio(d: pd.DataFrame, hist_df: pd.DataFrame, barrio: str, now: datetime):
    """Δ% del €/m² mediano del barrio: últimos 90 días vs 90 anteriores."""
    if hist_df.empty:
        return None
    ids = set(d[d["barrio_norm"] == barrio]["id"])
    sup = _con_superficie(d[d["id"].isin(ids)])[["id", "superficie_m2"]]

    def mediana_ventana(start, end):
        h = hist_df[
            hist_df["propiedad_id"].isin(ids)
            & (hist_df["fecha"] >= start)
            & (hist_df["fecha"] < end)
        ]
        if h.empty:
            return None
        ult = h.sort_values("fecha").groupby("propiedad_id").tail(1).merge(
            sup, left_on="propiedad_id", right_on="id"
        )
        if ult.empty:
            return None
        return float((ult["precio"] / ult["superficie_m2"]).median())

    act = mediana_ventana(now - timedelta(days=90), now)
    prev = mediana_ventana(now - timedelta(days=180), now - timedelta(days=90))
    if act is None or prev is None or prev == 0:
        return None
    return round(100 * (act - prev) / prev, 1)


def tabla_zonas(df: pd.DataFrame, hist_df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Agregados por barrio; <MIN_ACTIVAS_BARRIO activas -> OTROS; sin barrio -> SIN_ZONA."""
    columnas = [
        "barrio", "activas", "precio_m2_mediano", "precio_mediano",
        "vendidas_6m", "dias_mercado", "pct_bajada", "tendencia_pct",
    ]
    if df.empty:
        return pd.DataFrame(columns=columnas)

    d = df.copy()
    d["barrio_norm"] = d["barrio"].fillna(SIN_ZONA).replace("", SIN_ZONA)
    conteo_activas = d[d["activa"] == True].groupby("barrio_norm").size()
    pequenos = {b for b, n in conteo_activas.items() if n < MIN_ACTIVAS_BARRIO and b != SIN_ZONA}
    sin_activas = set(d["barrio_norm"].unique()) - set(conteo_activas.index) - {SIN_ZONA}
    d.loc[d["barrio_norm"].isin(pequenos | sin_activas), "barrio_norm"] = OTROS

    filas = []
    for barrio, g in d.groupby("barrio_norm"):
        act = g[g["activa"] == True]
        vend = g[
            (g["activa"] == False)
            & g["fecha_baja"].notna()
            & (g["fecha_baja"] >= now - timedelta(days=VENTANA_VENDIDAS_DIAS))
        ]
        dias = (vend["fecha_baja"] - vend["fecha_scraping"]).dt.days.clip(lower=0)
        con_bajada = act[act["precio_anterior"].notna() & (act["precio_anterior"] > act["precio"])]
        m2 = act["precio_m2"].dropna().median()
        pm = act["precio"].dropna().median()
        filas.append({
            "barrio": barrio,
            "activas": int(len(act)),
            "precio_m2_mediano": None if pd.isna(m2) else float(m2),
            "precio_mediano": None if pd.isna(pm) else float(pm),
            "vendidas_6m": int(len(vend)),
            "dias_mercado": float(dias.median()) if not vend.empty else None,
            "pct_bajada": round(100 * len(con_bajada) / len(act), 1) if len(act) else None,
            "tendencia_pct": _tendencia_barrio(d, hist_df, barrio, now),
        })
    return (
        pd.DataFrame(filas, columns=columnas)
        .sort_values("activas", ascending=False)
        .reset_index(drop=True)
    )

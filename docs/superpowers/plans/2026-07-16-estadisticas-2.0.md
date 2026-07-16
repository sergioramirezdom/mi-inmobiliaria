# Estadísticas 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Estadísticas page as a buyer-oriented market dashboard (Pulso/Zonas/Ofertas tabs, Plotly charts with a shared modern theme) plus a transparent comparables-based offer advisor for favorited properties.

**Architecture:** All business logic lives in two pure modules (`app/ui/market_stats.py` for market/zone aggregates over pandas DataFrames; `app/ui/offer_advisor.py` for comparable selection, valuation and offer-range heuristics over plain dicts) — no Streamlit, DB, or Plotly imports in either. A third module `app/ui/chart_theme.py` builds themed `plotly.graph_objects.Figure`s. The page `app/pages/4_estadisticas.py` is a thin orchestrator: two `st.cache_data` fetches returning plain dicts, then pure computation + rendering.

**Tech Stack:** Streamlit ≥1.41 (segmented_control, already required), Plotly (new dependency), pandas (already present), SQLModel/PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-estadisticas-2.0-design.md` (source of truth for behavior).

## Global Constraints

- Only new dependency: `plotly` (add `plotly>=5.18.0` to `requirements.txt`). Rendered via `st.plotly_chart`. Must keep working on Streamlit Cloud.
- `market_stats.py` and `offer_advisor.py` are PURE: no `streamlit`, no DB, no `plotly` imports. `chart_theme.py` imports plotly only. Cached fetch functions in the page return plain dicts, never live ORM objects.
- Heuristic thresholds, verbatim from the spec — do not change them: comparables surface tolerance ±40%; minimum comparables per cascade level 4; sold-comparables window 180 days; days-on-market discount −1% per full 30 days of excess, capped at −5%; prior-price-drop discount −2% fixed; overprice vs comparables = 0% discount (argument only, no double-count); zone table groups barrios with <3 active properties into «Otros» and NULL/empty barrio into «Sin zona»; zone trend compares median €/m² last 90 days vs previous 90; Pulso KPIs compare last 30 days vs previous 30; cache TTL 300s.
- Máximo razonable = min(valor_estimado, precio anunciado). Oferta inicial = máximo razonable × (1 − suma de descuentos).
- Chart colors: the validated categorical palette in fixed order `["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]` — assigned in order, NEVER cycled past 8 series (the Zonas multiselect is capped at 8 via `max_selections=8`). Spanish number format in charts via Plotly `separators=",."`. Transparent chart backgrounds.
- All UI copy in Spanish, matching the existing pages' tone and emoji style.
- Test files add the app dir to `sys.path` exactly like `tests/test_database_barrios.py` does: `sys.path.insert(0, str(Path(__file__).parent.parent / "app"))`.
- Pre-existing test baseline: `python -m pytest` shows 5 failures in `tests/test_scraper_config.py` (timeout-default/encoding issues, unrelated to this work) and 229 passing. Your changes must add zero NEW failures.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- If a project-local `.venv` exists in the working directory, use `./.venv/Scripts/python.exe` for every python/pytest/pip command; otherwise plain `python`.

---

### Task 1: Plotly dependency

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `plotly` for Tasks 4–5.

- [ ] **Step 1: Add the dependency**

Append this line to `requirements.txt` (keep every existing line unchanged):

```
plotly>=5.18.0
```

- [ ] **Step 2: Install and verify**

Run: `python -m pip install "plotly>=5.18.0"` then `python -c "import plotly.graph_objects as go; f = go.Figure(); f.update_layout(separators=',.'); print('ok')"`
Expected: `ok` printed, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add plotly dependency for estadisticas 2.0 charts"
```

---

### Task 2: Pure market/zone stats `market_stats.py`

**Files:**
- Create: `app/ui/market_stats.py`
- Test: `tests/test_market_stats.py`

**Interfaces:**
- Consumes: nothing from other tasks (plain dicts in, pandas only).
- Produces (used by Task 5):
  - Constants: `MIN_ACTIVAS_BARRIO = 3`, `OTROS = "Otros"`, `SIN_ZONA = "Sin zona"`.
  - `props_to_df(props: list[dict]) -> pd.DataFrame` — parses dates, adds `precio_m2` column (None when precio/superficie missing or superficie ≤ 0). Expected dict keys per property: `id, titulo, precio, precio_anterior, superficie_m2, habitaciones, tipo_propiedad, barrio, municipio, origen_web, url_original, activa, favorita, descartada, fecha_scraping, fecha_baja`.
  - `hist_to_df(hist: list[dict]) -> pd.DataFrame` — keys `propiedad_id, precio, fecha`; empty-safe.
  - `kpis_pulso(df, hist_df, now: datetime) -> dict` — keys `nuevas, ventas, precio_m2, bajadas, dias_mercado`, each `{"valor": num|None, "delta": num|None}`.
  - `lectura_mercado(kpis: dict) -> str`.
  - `serie_semanal_entradas(df, now, semanas: int = 12) -> pd.DataFrame` — columns `semana` (Timestamp, week start), `nuevas` (int), exactly `semanas` rows, missing weeks = 0.
  - `serie_mensual_ventas(df) -> pd.DataFrame` — columns `mes` (str "YYYY-MM"), `ventas` (int), chronological.
  - `serie_mensual_precio_m2(df, hist_df) -> pd.DataFrame` — columns `mes, precio_m2, n`.
  - `serie_mensual_precio_m2_por_barrio(df, hist_df) -> pd.DataFrame` — columns `mes, barrio, precio_m2, n`.
  - `tabla_zonas(df, hist_df, now) -> pd.DataFrame` — columns `barrio, activas, precio_m2_mediano, precio_mediano, vendidas_6m, dias_mercado, pct_bajada, tendencia_pct`.
  - `precio_m2_mediano_en(df, hist_df, fecha) -> float | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_stats.py` with exactly this content:

```python
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


# ── kpis_pulso ───────────────────────────────────────────────────────

def test_kpi_nuevas_delta_30_vs_30():
    props = (
        [_prop(id=i, fecha_scraping=NOW - timedelta(days=5)) for i in range(1, 4)]      # 3 en ventana actual
        + [_prop(id=i, fecha_scraping=NOW - timedelta(days=45)) for i in range(4, 6)]   # 2 en anterior
        + [_prop(id=9, fecha_scraping=NOW - timedelta(days=100))]                        # fuera
    )
    k = kpis_pulso(props_to_df(props), hist_to_df([]), NOW)
    assert k["nuevas"] == {"valor": 3, "delta": 1}


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_market_stats.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'ui.market_stats'`.

- [ ] **Step 3: Implement `app/ui/market_stats.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_market_stats.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/market_stats.py tests/test_market_stats.py
git commit -m "feat: pure market stats layer (pulso KPIs, series, zone table) for estadisticas 2.0"
```

---

### Task 3: Pure offer advisor `offer_advisor.py`

**Files:**
- Create: `app/ui/offer_advisor.py`
- Test: `tests/test_offer_advisor.py`

**Interfaces:**
- Consumes: nothing from other tasks. Works on plain dicts with native `datetime` values (NOT pandas Timestamps) — the page passes the raw dicts from its fetch, not DataFrames.
- Produces (used by Task 5):
  - Constants: `VENTANA_VENDIDAS_DIAS = 180`, `MIN_COMPARABLES = 4`, `TOLERANCIA_SUPERFICIE = 0.4`, `TOPE_DIAS_PCT = 5.0`, `PCT_POR_30_DIAS = 1.0`, `PCT_BAJADA_PREVIA = 2.0`, `NIVELES: dict[int, str]` (labels 1–4).
  - `campos_faltantes(favorita: dict) -> dict` — `{"imprescindibles": [...], "mejora": [...]}` (field-name strings).
  - `seleccionar_comparables(favorita: dict, universo: list[dict], now: datetime) -> tuple[list[dict], int | None]`.
  - `valorar(favorita: dict, comparables: list[dict]) -> dict` — `{"precio_m2_mediano", "valor_estimado", "n"}`.
  - `calcular_ajustes(favorita: dict, comparables: list[dict], now: datetime) -> list[dict]` — each `{"concepto": str, "pct": float (<=0), "detalle": str}`.
  - `rango_oferta(favorita: dict, valor_estimado: float, ajustes: list[dict]) -> dict` — `{"oferta_inicial": int, "maximo_razonable": int, "descuento_total_pct": float}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_offer_advisor.py` with exactly this content:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_offer_advisor.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'ui.offer_advisor'`.

- [ ] **Step 3: Implement `app/ui/offer_advisor.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_offer_advisor.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/offer_advisor.py tests/test_offer_advisor.py
git commit -m "feat: transparent comparables-based offer advisor for estadisticas 2.0"
```

---

### Task 4: Plotly chart theme `chart_theme.py`

**Files:**
- Create: `app/ui/chart_theme.py`
- Test: `tests/test_chart_theme.py`

**Interfaces:**
- Consumes: plotly (Task 1).
- Produces (used by Task 5):
  - `COLORWAY: list[str]` — the 8 validated hexes in fixed order.
  - `PLOTLY_CONFIG: dict` — pass as `config=` to every `st.plotly_chart` call.
  - `bar_chart(x, y, nombre: str, hovertemplate: str | None = None) -> go.Figure`
  - `line_chart(df, x: str, y: str, color: str | None = None, y_title: str = "", area: bool = False) -> go.Figure` — long-format df; one trace per distinct `color` value (max 8, colors assigned in COLORWAY order, never cycled).
  - `offer_range_chart(oferta: float, maximo: float, valor_estimado: float, precio_anunciado: float, comparables_eur: list[float]) -> go.Figure` — `comparables_eur` are the comparables' prices normalized to the favorita's size (comparable €/m² × favorita superficie).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chart_theme.py` with exactly this content:

```python
"""Smoke tests del tema Plotly (Estadísticas 2.0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import pandas as pd
import plotly.graph_objects as go
import pytest

from ui.chart_theme import COLORWAY, PLOTLY_CONFIG, bar_chart, line_chart, offer_range_chart


def test_colorway_es_la_paleta_validada():
    assert COLORWAY == ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]


def test_bar_chart_figura_y_tema():
    fig = bar_chart(["a", "b"], [1, 2], "Serie")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.layout.separators == ",."
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_line_chart_una_traza_por_categoria():
    df = pd.DataFrame({
        "mes": ["2026-01", "2026-02"] * 3,
        "v": [1, 2, 3, 4, 5, 6],
        "barrio": ["A", "A", "B", "B", "C", "C"],
    })
    fig = line_chart(df, x="mes", y="v", color="barrio")
    assert len(fig.data) == 3
    colores = [t.line.color for t in fig.data]
    assert colores == COLORWAY[:3]  # orden fijo, sin ciclar


def test_line_chart_mas_de_ocho_series_lanza_error():
    df = pd.DataFrame({"x": list(range(9)), "y": list(range(9)), "c": [str(i) for i in range(9)]})
    with pytest.raises(ValueError):
        line_chart(df, x="x", y="y", color="c")


def test_line_chart_simple_con_area():
    df = pd.DataFrame({"mes": ["2026-01", "2026-02"], "v": [1, 2]})
    fig = line_chart(df, x="mes", y="v", area=True, y_title="€/m²")
    assert len(fig.data) == 1
    assert fig.data[0].fill == "tozeroy"


def test_offer_range_chart_trazas():
    fig = offer_range_chart(140_000, 150_000, 155_000, 200_000, [130_000, 160_000])
    # 1 traza de comparables + 4 marcadores
    assert len(fig.data) == 5


def test_offer_range_chart_sin_comparables():
    fig = offer_range_chart(140_000, 150_000, 155_000, 200_000, [])
    assert len(fig.data) == 4


def test_config_sin_toolbar():
    assert PLOTLY_CONFIG["displayModeBar"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chart_theme.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'ui.chart_theme'`.

- [ ] **Step 3: Implement `app/ui/chart_theme.py`**

```python
"""Tema Plotly común y constructores de figuras para Estadísticas 2.0.

Paleta categórica validada (orden fijo, nunca ciclar más allá de 8 series).
Fondos transparentes para integrarse con el tema claro/oscuro de Streamlit;
el renderizado en página usa st.plotly_chart(fig, config=PLOTLY_CONFIG,
theme="streamlit") para que ejes/tipografía sigan el tema del viewer.
"""

import plotly.graph_objects as go

# Paleta categórica validada (dataviz reference palette) — orden fijo
COLORWAY = ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]
AZUL = COLORWAY[0]
VERDE_OSCURO = "#006300"   # delta positivo (texto éxito, modo claro)
AQUA = COLORWAY[4]
ROJO = COLORWAY[7]
GRIS_MUTED = "#898781"     # tinta muted, válida en claro y oscuro

BASE_LAYOUT = dict(
    colorway=COLORWAY,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    separators=",.",  # decimal coma, miles punto (formato español)
    margin=dict(l=10, r=10, t=30, b=10),
    hoverlabel=dict(font_size=13),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)

PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def _fig(hovermode=None) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**BASE_LAYOUT)
    if hovermode:
        fig.update_layout(hovermode=hovermode)
    return fig


def bar_chart(x, y, nombre: str, hovertemplate=None) -> go.Figure:
    """Barras finas con esquinas redondeadas y tooltip por barra."""
    fig = _fig()
    fig.add_bar(
        x=list(x), y=list(y), name=nombre,
        marker=dict(color=AZUL, cornerradius=4),
        hovertemplate=hovertemplate or "%{x}: %{y}<extra></extra>",
    )
    fig.update_layout(showlegend=False, bargap=0.35)
    return fig


def line_chart(df, x: str, y: str, color=None, y_title: str = "", area: bool = False) -> go.Figure:
    """Líneas con tooltip unificado. Con `color`, una traza por categoría (máx. 8,
    colores en orden fijo de COLORWAY — nunca se cicla)."""
    fig = _fig(hovermode="x unified")
    if color:
        categorias = list(dict.fromkeys(df[color]))
        if len(categorias) > len(COLORWAY):
            raise ValueError(
                f"Máximo {len(COLORWAY)} series (hay {len(categorias)}): agrupa o filtra antes de graficar."
            )
        for i, nombre in enumerate(categorias):
            g = df[df[color] == nombre]
            fig.add_scatter(
                x=g[x], y=g[y], mode="lines", name=str(nombre),
                line=dict(width=2, color=COLORWAY[i], shape="spline", smoothing=0.6),
                hovertemplate="%{y:,.0f}<extra>" + str(nombre) + "</extra>",
            )
    else:
        fig.add_scatter(
            x=df[x], y=df[y], mode="lines", name=y_title or y,
            line=dict(width=2, color=AZUL, shape="spline", smoothing=0.6),
            fill="tozeroy" if area else None,
            fillcolor="rgba(42,120,214,0.12)" if area else None,
            hovertemplate="%{y:,.0f}<extra></extra>",
        )
        fig.update_layout(showlegend=False)
    fig.update_yaxes(title_text=y_title)
    return fig


def offer_range_chart(oferta, maximo, valor_estimado, precio_anunciado, comparables_eur) -> go.Figure:
    """Eje horizontal de precio: comparables como puntos y 4 marcadores verticales
    (oferta inicial, máximo razonable, valor estimado, precio anunciado)."""
    fig = _fig()
    if comparables_eur:
        fig.add_scatter(
            x=list(comparables_eur), y=[0] * len(comparables_eur), mode="markers",
            name="Comparables",
            marker=dict(size=9, color=GRIS_MUTED, opacity=0.55),
            hovertemplate="Comparable: %{x:,.0f} €<extra></extra>",
        )
    marcadores = [
        ("Oferta inicial", oferta, VERDE_OSCURO),
        ("Máximo razonable", maximo, AZUL),
        ("Valor estimado", valor_estimado, AQUA),
        ("Precio anunciado", precio_anunciado, ROJO),
    ]
    for nombre, valor, color in marcadores:
        fig.add_scatter(
            x=[valor], y=[0], mode="markers+text", name=nombre,
            marker=dict(size=18, color=color, symbol="line-ns-open", line=dict(width=3, color=color)),
            text=[nombre], textposition="top center", textfont=dict(size=11, color=color),
            hovertemplate=nombre + ": %{x:,.0f} €<extra></extra>",
        )
    fig.update_yaxes(visible=False, range=[-1, 1.6])
    fig.update_xaxes(title_text="€")
    fig.update_layout(height=230, showlegend=False)
    return fig
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chart_theme.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/chart_theme.py tests/test_chart_theme.py
git commit -m "feat: shared plotly theme with validated palette for estadisticas 2.0"
```

---

### Task 5: Rewrite the page `4_estadisticas.py`

**Files:**
- Modify (full rewrite): `app/pages/4_estadisticas.py`

**Interfaces:**
- Consumes (everything already exists after Tasks 2–4):
  - `ui.market_stats`: `props_to_df, hist_to_df, kpis_pulso, lectura_mercado, serie_semanal_entradas, serie_mensual_ventas, serie_mensual_precio_m2, serie_mensual_precio_m2_por_barrio, tabla_zonas, OTROS, SIN_ZONA`
  - `ui.offer_advisor`: `campos_faltantes, seleccionar_comparables, valorar, calcular_ajustes, rango_oferta, NIVELES, MIN_COMPARABLES`
  - `ui.chart_theme`: `PLOTLY_CONFIG, bar_chart, line_chart, offer_range_chart`
  - `db.database`: `engine, PropiedadCRUD` (`PropiedadCRUD.update(session, id, **kwargs)` and `PropiedadCRUD.get_distinct_barrios(session)` already exist)
- Produces: the final page. No other module imports it.

- [ ] **Step 1: Replace the entire file**

New content of `app/pages/4_estadisticas.py`:

```python
"""Estadísticas 2.0: pulso del mercado, zonas y asistente de ofertas."""

import sys
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine, PropiedadCRUD
from db.models import Propiedad, PrecioHistorico
from ui import market_stats as ms
from ui import offer_advisor as oa
from ui.chart_theme import PLOTLY_CONFIG, bar_chart, line_chart, offer_range_chart

st.set_page_config(page_title="Mercado", page_icon="📊", layout="wide")

TABS = {"pulso": "📈 Pulso", "zonas": "🗺️ Zonas", "ofertas": "🎯 Ofertas"}
MAX_BARRIOS_GRAFICO = 8  # límite de la paleta categórica — nunca ciclar colores


# ── Fetches cacheados (dicts planos, nunca ORM) ───────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_props() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Propiedad)).all()
        return [{
            "id": p.id, "titulo": p.titulo, "precio": p.precio,
            "precio_anterior": p.precio_anterior, "superficie_m2": p.superficie_m2,
            "habitaciones": p.habitaciones, "tipo_propiedad": p.tipo_propiedad,
            "barrio": p.barrio, "municipio": p.municipio, "origen_web": p.origen_web,
            "url_original": p.url_original, "activa": p.activa, "favorita": p.favorita,
            "descartada": p.descartada, "fecha_scraping": p.fecha_scraping,
            "fecha_baja": p.fecha_baja,
        } for p in rows]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_hist() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(PrecioHistorico)).all()
        return [{"propiedad_id": h.propiedad_id, "precio": h.precio, "fecha": h.fecha}
                for h in rows]


def clear_caches():
    fetch_props.clear()
    fetch_hist.clear()


def eur(v) -> str:
    return f"{v:,.0f} €".replace(",", ".")


# ── Pestaña Pulso ─────────────────────────────────────────────────────

def render_pulso(df, hist_df, now):
    k = ms.kpis_pulso(df, hist_df, now)
    c1, c2, c3, c4, c5 = st.columns(5)
    # delta_color: para un comprador, más oferta/bajadas/días = bueno (verde al subir);
    # €/m² y ventas subiendo = malo (rojo al subir) -> inverse.
    c1.metric("🆕 Nuevas (30d)", k["nuevas"]["valor"], delta=k["nuevas"]["delta"])
    c2.metric("🚫 Ventas (30d)", k["ventas"]["valor"], delta=k["ventas"]["delta"],
              delta_color="inverse")
    c3.metric("💶 €/m² mediano",
              eur(k["precio_m2"]["valor"]) if k["precio_m2"]["valor"] is not None else "N/D",
              delta=k["precio_m2"]["delta"], delta_color="inverse")
    c4.metric("📉 Bajadas (30d)", k["bajadas"]["valor"], delta=k["bajadas"]["delta"])
    c5.metric("⏱️ Días en mercado",
              f"{k['dias_mercado']['valor']:.0f}" if k["dias_mercado"]["valor"] is not None else "N/D",
              delta=k["dias_mercado"]["delta"])
    st.info(f"💡 {ms.lectura_mercado(k)}")
    st.caption("Deltas: últimos 30 días frente a los 30 anteriores. Verde = a favor del comprador.")
    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Entradas por semana")
        s = ms.serie_semanal_entradas(df, now)
        etiquetas = s["semana"].dt.strftime("%d %b")
        st.plotly_chart(
            bar_chart(etiquetas, s["nuevas"], "Nuevas",
                      hovertemplate="Semana del %{x}: %{y} nuevas<extra></extra>"),
            config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
        )
    with col_b:
        st.subheader("Ventas por mes")
        sv = ms.serie_mensual_ventas(df)
        if sv.empty:
            st.info("Sin ventas registradas todavía.")
        else:
            st.plotly_chart(
                bar_chart(sv["mes"], sv["ventas"], "Ventas"),
                config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
            )

    st.subheader("Evolución del €/m² mediano (activas)")
    sm = ms.serie_mensual_precio_m2(df, hist_df)
    if sm.empty:
        st.info("Sin historial de precios todavía.")
    else:
        st.plotly_chart(
            line_chart(sm, x="mes", y="precio_m2", y_title="€/m²", area=True),
            config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
        )


# ── Pestaña Zonas ─────────────────────────────────────────────────────

def render_zonas(df, hist_df, now):
    t = ms.tabla_zonas(df, hist_df, now)
    if t.empty:
        st.info("No hay propiedades para agrupar por zona.")
        return

    display = t.copy()
    display["precio_m2_mediano"] = display["precio_m2_mediano"].map(
        lambda v: eur(v) if v is not None and pd.notna(v) else "—")
    display["precio_mediano"] = display["precio_mediano"].map(
        lambda v: eur(v) if v is not None and pd.notna(v) else "—")
    display["dias_mercado"] = display["dias_mercado"].map(
        lambda v: f"{v:.0f}" if v is not None and pd.notna(v) else "—")
    display["pct_bajada"] = display["pct_bajada"].map(
        lambda v: f"{v:.1f}%" if v is not None and pd.notna(v) else "—")
    display["tendencia_pct"] = display["tendencia_pct"].map(
        lambda v: "=" if v is None or pd.isna(v)
        else (f"▲ +{v:.1f}%" if v > 0 else (f"▼ {v:.1f}%" if v < 0 else "= 0%")))
    display.columns = ["Barrio", "Activas", "€/m² mediano", "Precio mediano",
                       "Vendidas (6m)", "Días en mercado", "% con bajada", "Tendencia €/m²"]
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(
        f"Barrios con menos de {ms.MIN_ACTIVAS_BARRIO} activas se agrupan en «{ms.OTROS}». "
        "Tendencia: €/m² mediano de los últimos 90 días frente a los 90 anteriores."
    )
    st.divider()

    st.subheader("Evolución del €/m² por barrio")
    serie = ms.serie_mensual_precio_m2_por_barrio(df, hist_df)
    if serie.empty:
        st.info("Sin historial de precios todavía.")
        return
    barrios = sorted(serie["barrio"].unique())
    defecto = [b for b in barrios if b not in (ms.OTROS, ms.SIN_ZONA)][:3] or barrios[:3]
    seleccion = st.multiselect(
        "Barrios", barrios, default=defecto, max_selections=MAX_BARRIOS_GRAFICO,
        help=f"Máximo {MAX_BARRIOS_GRAFICO} barrios a la vez.",
    )
    if not seleccion:
        st.caption("Selecciona al menos un barrio.")
        return
    filtrada = serie[serie["barrio"].isin(seleccion)]
    st.plotly_chart(
        line_chart(filtrada, x="mes", y="precio_m2", color="barrio", y_title="€/m²"),
        config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
    )
    con_pocos = sorted(filtrada[filtrada["n"] < 3]["barrio"].unique())
    if con_pocos:
        st.warning(
            "⚠️ Líneas con meses de menos de 3 propiedades — interpretar con cautela: "
            + ", ".join(con_pocos)
        )


# ── Pestaña Ofertas ───────────────────────────────────────────────────

CAMPOS_LABEL = {
    "precio": "Precio (€)",
    "superficie_m2": "Superficie (m²)",
    "barrio": "Barrio",
    "tipo_propiedad": "Tipo de propiedad",
}


def form_completar_datos(fav: dict, campos: list, props: list, key: str):
    """Formulario inline para completar campos que faltan; persiste y recarga."""
    with st.form(f"completar_{key}_{fav['id']}"):
        valores = {}
        if "precio" in campos:
            valores["precio"] = st.number_input(CAMPOS_LABEL["precio"], min_value=0, step=1000)
        if "superficie_m2" in campos:
            valores["superficie_m2"] = st.number_input(CAMPOS_LABEL["superficie_m2"], min_value=0, step=1)
        if "barrio" in campos:
            with Session(engine) as session:
                barrios = PropiedadCRUD.get_distinct_barrios(session)
            elegido = st.selectbox(CAMPOS_LABEL["barrio"], [""] + barrios)
            libre = st.text_input("…o escribe un barrio nuevo")
            valores["barrio"] = libre.strip() or elegido
        if "tipo_propiedad" in campos:
            tipos = sorted({p["tipo_propiedad"] for p in props if p["tipo_propiedad"]})
            valores["tipo_propiedad"] = st.selectbox(CAMPOS_LABEL["tipo_propiedad"], [""] + tipos)

        if st.form_submit_button("💾 Guardar y recalcular", type="primary"):
            a_guardar = {k: v for k, v in valores.items() if v}
            if a_guardar:
                with Session(engine) as session:
                    PropiedadCRUD.update(session, fav["id"], **a_guardar)
                clear_caches()
                st.rerun()
            else:
                st.warning("No has rellenado ningún campo.")


def render_ofertas(props: list, now):
    favoritas = [p for p in props if p["favorita"]]
    if not favoritas:
        st.info("No tienes favoritas todavía. Marca alguna con ❤️ en la página de Propiedades.")
        return

    fav = st.selectbox(
        "Favorita a valorar", favoritas,
        format_func=lambda p: f"{(p['titulo'] or 'Sin título')[:60]} — "
                              + (eur(p["precio"]) if p["precio"] else "sin precio"),
    )
    faltan = oa.campos_faltantes(fav)

    if faltan["imprescindibles"]:
        nombres = ", ".join(CAMPOS_LABEL[c] for c in faltan["imprescindibles"])
        st.warning(f"⚠️ No se puede valorar sin: {nombres}. Complétalos aquí:")
        st.markdown("#### 📝 Completa datos para afinar la valoración")
        form_completar_datos(fav, faltan["imprescindibles"] + faltan["mejora"], props, "impr")
        return

    comparables, nivel = oa.seleccionar_comparables(fav, props, now)
    if not comparables:
        st.error(
            "No hay ningún comparable con precio y superficie en tu base de datos "
            "(ni siquiera ampliando a todo el municipio). Añade más fuentes o espera a nuevos datos."
        )
        if faltan["mejora"]:
            with st.expander("📝 Completa datos para afinar la valoración"):
                form_completar_datos(fav, faltan["mejora"], props, "mejora")
        return

    val = oa.valorar(fav, comparables)
    ajustes = oa.calcular_ajustes(fav, comparables, now)
    rango = oa.rango_oferta(fav, val["valor_estimado"], ajustes)

    if val["n"] < oa.MIN_COMPARABLES:
        st.warning(
            f"⚠️ Solo {val['n']} comparable(s) (nivel: {oa.NIVELES[nivel]}). Fiabilidad baja."
        )
    else:
        st.caption(f"Comparables: {val['n']} · criterio: {oa.NIVELES[nivel]}")

    c1, c2, c3 = st.columns(3)
    c1.metric("🎯 Oferta inicial sugerida", eur(rango["oferta_inicial"]),
              delta=f"-{rango['descuento_total_pct']:.1f}% de presión" if rango["descuento_total_pct"] else None,
              delta_color="off")
    c2.metric("✅ Máximo razonable", eur(rango["maximo_razonable"]))
    c3.metric("📌 Precio anunciado", eur(fav["precio"]))

    comparables_eur = [c["precio"] / c["superficie_m2"] * fav["superficie_m2"] for c in comparables]
    st.plotly_chart(
        offer_range_chart(rango["oferta_inicial"], rango["maximo_razonable"],
                          val["valor_estimado"], fav["precio"], comparables_eur),
        config=PLOTLY_CONFIG, theme="streamlit", use_container_width=True,
    )
    st.caption("Los puntos grises son los comparables llevados al tamaño de tu favorita (su €/m² × tu superficie).")

    st.markdown("#### 🧾 Desglose")
    st.markdown(f"- **Valor estimado**: {eur(val['valor_estimado'])} "
                f"(€/m² mediano de comparables: {eur(val['precio_m2_mediano'])} × {fav['superficie_m2']:.0f} m²)")
    for a in ajustes:
        pct_txt = f"{a['pct']:+.1f}%" if a["pct"] else "0%"
        st.markdown(f"- **{a['concepto']}** ({pct_txt}): {a['detalle']}")

    st.markdown("#### 📋 Comparables")
    tabla = pd.DataFrame([{
        "Título": (c["titulo"] or "")[:50],
        "Barrio": c["barrio"] or "—",
        "Tipo": c["tipo_propiedad"] or "—",
        "m²": c["superficie_m2"],
        "Precio": c["precio"],
        "€/m²": round(c["precio"] / c["superficie_m2"]),
        "Estado": "Activa" if c["activa"] else "Vendida",
        "Días en mercado": (c["fecha_baja"] - c["fecha_scraping"]).days
        if not c["activa"] and c["fecha_baja"] and c["fecha_scraping"] else None,
        "Anuncio": c["url_original"],
    } for c in comparables])
    st.dataframe(
        tabla, use_container_width=True, hide_index=True,
        column_config={"Anuncio": st.column_config.LinkColumn("Anuncio", display_text="Abrir")},
    )

    if faltan["mejora"]:
        nombres = ", ".join(CAMPOS_LABEL[c] for c in faltan["mejora"])
        with st.expander(f"📝 Completa datos para afinar la valoración ({nombres})"):
            st.caption(f"Añadir {nombres} afinaría los comparables (criterio actual: {oa.NIVELES[nivel]}).")
            form_completar_datos(fav, faltan["mejora"], props, "mejora")

    st.caption(
        "ℹ️ Heurística orientativa basada en la oferta anunciada observada en tus fuentes; "
        "no es una tasación oficial."
    )


# ── Página ────────────────────────────────────────────────────────────

try:
    st.title("📊 Mercado")

    tab = st.segmented_control(
        "Vista", options=list(TABS.keys()),
        format_func=lambda k: TABS[k],
        default="pulso", key="tab_mercado",
        label_visibility="collapsed", required=True,
    ) or "pulso"

    props = fetch_props()
    hist = fetch_hist()
    if not props:
        st.warning("No hay propiedades en la base de datos.")
        st.stop()

    df = ms.props_to_df(props)
    hist_df = ms.hist_to_df(hist)
    now = datetime.now(UTC).replace(tzinfo=None)

    if tab == "pulso":
        render_pulso(df, hist_df, now)
    elif tab == "zonas":
        render_zonas(df, hist_df, now)
    else:
        render_ofertas(props, now)

except Exception as e:
    st.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
```

- [ ] **Step 2: Compile check and full test suite**

Run: `python -m py_compile app/pages/4_estadisticas.py`
Expected: no output (success).

Run: `python -m pytest`
Expected: all new tests pass; total failures remain exactly the 5 pre-existing ones in `tests/test_scraper_config.py`.

- [ ] **Step 3: Smoke test**

Run `python -m streamlit run app/main.py --server.headless true --server.port 8767` in the background, wait ~6s, `curl -s -o /dev/null -w "%{http_code}" http://localhost:8767/estadisticas` (expect 200, no traceback in the server log), then kill the process. If no live `DATABASE_URL` is available, the page body can't execute against data — in that case verify only boot + syntax and state clearly in your report that live verification is deferred to the human. Do NOT claim manual browser verification you did not perform.

- [ ] **Step 4: Commit**

```bash
git add app/pages/4_estadisticas.py
git commit -m "feat: estadisticas 2.0 - market pulse, zone trends and offer advisor with plotly"
```

---

### Task 6: Final review pass

**Files:**
- Verify only; no planned changes.

- [ ] **Step 1: Full suite + import smoke**

Run: `python -m pytest`
Expected: only the 5 pre-existing failures in `tests/test_scraper_config.py`.

Run: `python -c "import sys; sys.path.insert(0,'app'); import ui.market_stats, ui.offer_advisor, ui.chart_theme; print('ok')"`
Expected: `ok`.

- [ ] **Step 2: Spec cross-check**

Re-read `docs/superpowers/specs/2026-07-16-estadisticas-2.0-design.md` section by section and confirm each requirement maps to shipped code: page structure §1, Pulso KPIs+charts §2, Zonas table+chart §3, Ofertas comparables/valuation/range/missing-data form §4 (incl. a-bis), architecture §5, error handling §6, tests §7. Fix any gap found before closing.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: estadisticas 2.0 review follow-ups"
```

(Skip the commit if Step 2 found nothing.)

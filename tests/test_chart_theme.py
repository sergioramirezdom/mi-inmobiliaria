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

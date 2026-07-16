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

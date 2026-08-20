"""Paleta de colores y tokens de diseño — Propiedades 2.0.

Usage:
    from ui.theme import inject_theme, COLORS, card_style, chip_style
"""

import streamlit as st

# ── Colores principales ───────────────────────────────────────────────
COLORS = {
    # Esmerald Ink (primary)
    "primary": "#064E3B",
    "primary_light": "#059669",
    "primary_pale": "#D1FAE5",
    # Champagne (secondary)
    "champagne": "#F8E7C9",
    "champagne_dark": "#E8D5B0",
    "champagne_light": "#FDF8F0",
    # Neutros
    "charcoal": "#1A1A2E",
    "slate": "#6B7280",
    "slate_light": "#9CA3AF",
    "white": "#FFFFFF",
    # Semantic
    "success": "#16A34A",
    "danger": "#DC2626",
    "warning": "#F59E0B",
    "info": "#2563EB",
}

# ── Tokens de diseño ──────────────────────────────────────────────────
SHADOWS = {
    "sm": "0 1px 3px rgba(0,0,0,0.08)",
    "md": "0 4px 12px rgba(0,0,0,0.1)",
    "lg": "0 8px 24px rgba(0,0,0,0.12)",
    "card": "0 2px 8px rgba(6,78,59,0.06)",
    "card_hover": "0 8px 24px rgba(6,78,59,0.12)",
}

BORDER_RADIUS = {
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "20px",
    "full": "9999px",
}

FONT_SIZES = {
    "xs": "0.7rem",
    "sm": "0.8rem",
    "base": "0.9rem",
    "md": "1rem",
    "lg": "1.2rem",
    "xl": "1.4rem",
    "2xl": "1.8rem",
}


# ── CSS Variables (inyectadas una vez por página) ─────────────────────
def css_variables() -> str:
    """Devuelve un bloque CSS con todas las variables :root."""
    lines = [":root {"]
    for k, v in COLORS.items():
        lines.append(f"  --{k}: {v};")
    for k, v in SHADOWS.items():
        lines.append(f"  --shadow-{k}: {v};")
    for k, v in BORDER_RADIUS.items():
        lines.append(f"  --radius-{k}: {v};")
    for k, v in FONT_SIZES.items():
        lines.append(f"  --font-{k}: {v};")
    lines.append("}")
    return "\n".join(lines)


# ── Estilos inline reutilizables ─────────────────────────────────────
def card_style() -> str:
    """CSS inline para una tarjeta de propiedad."""
    return (
        f"background:{COLORS['white']};"
        f"border-radius:{BORDER_RADIUS['lg']};"
        f"box-shadow:{SHADOWS['card']};"
        f"overflow:hidden;"
        f"transition:transform 0.2s ease, box-shadow 0.2s ease;"
        f"border:1px solid {COLORS['champagne_dark']};"
    )


def chip_style(active: bool = False) -> str:
    """CSS inline para chips de características."""
    if active:
        return (
            f"background:{COLORS['primary']};color:{COLORS['white']};"
            f"border-radius:{BORDER_RADIUS['full']};"
            f"padding:3px 10px;font-size:{FONT_SIZES['xs']};"
            f"font-weight:500;white-space:nowrap;display:inline-block;"
            f"margin:2px 4px 2px 0;"
        )
    return (
        f"background:{COLORS['champagne']};color:{COLORS['primary']};"
        f"border-radius:{BORDER_RADIUS['full']};"
        f"padding:3px 10px;font-size:{FONT_SIZES['xs']};"
        f"font-weight:500;white-space:nowrap;display:inline-block;"
        f"margin:2px 4px 2px 0;"
    )


def price_style() -> str:
    """CSS inline para el precio destacado."""
    return (
        f"font-size:{FONT_SIZES['xl']};font-weight:700;"
        f"color:{COLORS['primary']};line-height:1.2;"
    )


def badge_style(variant: str = "default") -> str:
    """CSS inline para badges de estado.
    
    Variantes: favorite, discarded, visited, inactive, default
    """
    variants = {
        "favorite": (COLORS["danger"], "#FEE2E2"),
        "discarded": (COLORS["slate"], "#F3F4F6"),
        "visited": (COLORS["info"], "#DBEAFE"),
        "inactive": (COLORS["warning"], "#FEF3C7"),
        "default": (COLORS["slate"], COLORS["champagne_light"]),
    }
    fg, bg = variants.get(variant, variants["default"])
    return (
        f"background:{bg};color:{fg};"
        f"border-radius:{BORDER_RADIUS['full']};"
        f"padding:2px 8px;font-size:{FONT_SIZES['xs']};"
        f"font-weight:600;display:inline-flex;align-items:center;"
        f"gap:4px;white-space:nowrap;"
    )


def button_style(variant: str = "ghost") -> str:
    """CSS inline para botones de acción.
    
    Variantes: ghost, primary, danger
    """
    if variant == "primary":
        return (
            f"background:{COLORS['primary']};color:{COLORS['white']};"
            f"border:none;border-radius:{BORDER_RADIUS['md']};"
            f"padding:8px 16px;font-weight:600;cursor:pointer;"
            f"transition:background 0.15s;"
        )
    if variant == "danger":
        return (
            f"background:{COLORS['danger']};color:{COLORS['white']};"
            f"border:none;border-radius:{BORDER_RADIUS['md']};"
            f"padding:8px 16px;font-weight:600;cursor:pointer;"
        )
    # ghost (default)
    return (
        f"background:transparent;color:{COLORS['charcoal']};"
        f"border:none;border-radius:{BORDER_RADIUS['md']};"
        f"padding:6px 10px;cursor:pointer;transition:background 0.15s;"
    )


# ── Inyección global ──────────────────────────────────────────────────
_injected = False


def inject_theme():
    """Inyecta las CSS variables y estilos base en la página Streamlit.
    
    Seguro llamar múltiples veces — solo inyecta la primera vez.
    """
    global _injected
    if _injected:
        return
    _injected = True

    css = f"""
    <style>
    {css_variables()}
    /* Streamlit overrides for v2 theme */
    .stApp {{ background: {COLORS['champagne_light']}; }}
    section[data-testid="stSidebar"] {{
        background: {COLORS['champagne_light']};
        border-right: 1px solid {COLORS['champagne_dark']};
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
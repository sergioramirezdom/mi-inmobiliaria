# Propiedades 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Propiedades page as a triage-first UI: state tabs, visual HTML cards with photo and €/m², form-based filters, and per-card `st.fragment` actions so triage never reloads the whole page.

**Architecture:** The 935-line `app/pages/2_propiedades.py` is split into a pure query layer (`app/ui/property_queries.py`, testable without Streamlit), a card renderer (`app/ui/property_card.py`: pure HTML builder + fragment with action buttons), the existing dialogs moved to `app/ui/property_dialogs.py`, and a thin page that orchestrates tabs/filters/pagination with `st.cache_data`-cached fetches.

**Tech Stack:** Streamlit ≥1.41 (segmented_control, fragment, dialog), SQLModel/SQLAlchemy on PostgreSQL (Neon), pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-propiedades-2.0-design.md`

## Global Constraints

- Streamlit puro: no new dependencies beyond bumping `streamlit>=1.41.0`; must keep working on Streamlit Cloud.
- NULL semantics for numeric filters: a property with the field NULL is INCLUDED (unknown ≠ excluded). Boolean characteristic filters require `True`.
- Cached fetch functions return plain dicts, never live ORM objects.
- Result limit stays at 300; page size stays at 12; grid stays 3 columns.
- All UI copy in Spanish, matching the existing pages' tone and emoji style.
- Existing dialogs (edit, calculadora, fotos, añadir URL) move without functional changes, except `add_url_dialog` opens its own DB session instead of receiving one (the passed-in session dies between dialog reruns).
- Test files add the app dir to `sys.path` exactly like `tests/test_database_barrios.py` does: `sys.path.insert(0, str(Path(__file__).parent.parent / "app"))`.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Streamlit version bump + `app/ui` package

**Files:**
- Modify: `requirements.txt:1`
- Create: `app/ui/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `ui` (pages already do `sys.path.insert(0, <app dir>)`, so imports are `from ui.property_queries import ...`).

- [ ] **Step 1: Bump Streamlit floor**

In `requirements.txt` replace line 1:

```
streamlit>=1.41.0
```

- [ ] **Step 2: Create the package**

Create `app/ui/__init__.py`:

```python
"""UI helpers for Streamlit pages."""
```

- [ ] **Step 3: Install and verify**

Run: `pip install -U "streamlit>=1.41.0"` then `python -c "import streamlit; print(streamlit.__version__); assert hasattr(streamlit, 'segmented_control') and hasattr(streamlit, 'fragment')"`
Expected: version ≥ 1.41.0 printed, no AssertionError.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt app/ui/__init__.py
git commit -m "chore: bump streamlit to >=1.41 and add app/ui package for propiedades 2.0"
```

---

### Task 2: Query layer `property_queries.py`

**Files:**
- Create: `app/ui/property_queries.py`
- Test: `tests/test_property_queries.py`

**Interfaces:**
- Consumes: `db.models.Propiedad`.
- Produces (used by Tasks 3 and 5):
  - `CARACTERISTICAS: dict[str, str]` — label → Propiedad field name.
  - `SORT_OPTIONS: dict[str, tuple[str, str]]` — label → (field, "asc"|"desc").
  - `tab_conditions(tab: str) -> list` — SQLAlchemy conditions for `"nuevas"|"todas"|"favoritas"|"descartadas"|"vendidas"`; raises `ValueError` otherwise.
  - `filter_conditions(filters: dict) -> list` — conditions from the filters dict (keys: `precio_min`, `precio_max`, `m2_min`, `hab_min`, `banos_min` ints; `tipos`, `distritos`, `caracteristicas` lists; `search` str; all optional).
  - `build_stmt(tab: str, filters: dict, sort_key: str)` — full `select(Propiedad)` with conditions, order, `.limit(300)`.
  - `precio_por_m2(precio, superficie) -> int | None`.
  - `prop_to_dict(prop: Propiedad, fuente_manual_id: int | None = None) -> dict` — keys: `id, titulo, precio, bajada, precio_m2, superficie, habitaciones, banos, tipo, barrio, municipio, chips, fotos, url, origen, dias, es_manual, activa, estado, vista, favorita, descartada`.
  - `counts_from_rows(rows) -> dict` — rows of `(activa, vista, descartada, favorita)` tuples → counts per tab key.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_property_queries.py`:

```python
"""Tests for the pure query layer of Propiedades 2.0."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Propiedad
from sqlalchemy import or_
from ui.property_queries import (
    CARACTERISTICAS,
    SORT_OPTIONS,
    build_stmt,
    counts_from_rows,
    filter_conditions,
    precio_por_m2,
    prop_to_dict,
    tab_conditions,
)


# ── tab_conditions ────────────────────────────────────────────────────

def test_tab_nuevas_is_active_not_discarded_not_viewed():
    conds = tab_conditions("nuevas")
    expected = [Propiedad.activa == True, Propiedad.descartada == False, Propiedad.vista == False]
    assert len(conds) == 3
    assert all(c.compare(e) for c, e in zip(conds, expected))


def test_tab_todas_is_active_not_discarded():
    conds = tab_conditions("todas")
    expected = [Propiedad.activa == True, Propiedad.descartada == False]
    assert len(conds) == 2
    assert all(c.compare(e) for c, e in zip(conds, expected))


def test_tab_favoritas_descartadas_vendidas():
    assert tab_conditions("favoritas")[0].compare(Propiedad.favorita == True)
    assert tab_conditions("descartadas")[0].compare(Propiedad.descartada == True)
    assert tab_conditions("vendidas")[0].compare(Propiedad.activa == False)


def test_tab_unknown_raises():
    with pytest.raises(ValueError):
        tab_conditions("nope")


# ── filter_conditions ─────────────────────────────────────────────────

def test_numeric_filters_include_null():
    conds = filter_conditions({"precio_min": 100_000})
    assert len(conds) == 1
    assert conds[0].compare(or_(Propiedad.precio >= 100_000, Propiedad.precio == None))


def test_zero_or_missing_filters_produce_no_conditions():
    assert filter_conditions({}) == []
    assert filter_conditions({"precio_min": 0, "m2_min": 0, "search": "", "tipos": []}) == []


def test_caracteristicas_require_true():
    conds = filter_conditions({"caracteristicas": ["Terraza", "Ascensor"]})
    assert len(conds) == 2
    assert conds[0].compare(Propiedad.terraza == True)
    assert conds[1].compare(Propiedad.ascensor == True)


def test_search_matches_titulo_or_descripcion():
    conds = filter_conditions({"search": "patio"})
    assert len(conds) == 1
    assert conds[0].compare(
        or_(Propiedad.titulo.ilike("%patio%"), Propiedad.descripcion.ilike("%patio%"))
    )


def test_tipos_and_distritos_use_in():
    conds = filter_conditions({"tipos": ["piso"], "distritos": ["Centro"]})
    assert len(conds) == 2
    assert conds[0].compare(Propiedad.tipo_propiedad.in_(["piso"]))
    assert conds[1].compare(Propiedad.distrito.in_(["Centro"]))


# ── build_stmt ────────────────────────────────────────────────────────

def test_build_stmt_compiles_and_limits():
    stmt = build_stmt("nuevas", {"precio_max": 200_000}, "Precio (menor)")
    sql = str(stmt)
    assert "LIMIT" in sql
    assert "ORDER BY" in sql


def test_build_stmt_unknown_sort_raises():
    with pytest.raises(KeyError):
        build_stmt("todas", {}, "no existe")


# ── precio_por_m2 ─────────────────────────────────────────────────────

def test_precio_por_m2():
    assert precio_por_m2(189_000, 102) == 1853
    assert precio_por_m2(None, 102) is None
    assert precio_por_m2(189_000, None) is None
    assert precio_por_m2(189_000, 0) is None


# ── prop_to_dict ──────────────────────────────────────────────────────

def _prop(**kwargs):
    defaults = dict(
        id=1,
        hash_unico="x",
        url_original="https://example.com/1",
        fuente_id=7,
        origen_web="example.com",
        titulo="Piso céntrico",
        precio=189_000.0,
        superficie_m2=102.0,
        habitaciones=3,
        banos=2,
        tipo_propiedad="piso",
        barrio="Centro",
        municipio="El Puerto de Santa María",
        terraza=True,
        ascensor=True,
        fecha_scraping=datetime.utcnow() - timedelta(days=2),
        activa=True,
    )
    defaults.update(kwargs)
    return Propiedad(**defaults)


def test_prop_to_dict_basics():
    d = prop_to_dict(_prop(), fuente_manual_id=99)
    assert d["id"] == 1
    assert d["precio_m2"] == 1853
    assert d["bajada"] is None
    assert d["dias"] == 2
    assert d["es_manual"] is False
    assert d["chips"] == ["Ascensor", "Terraza"]  # CARACTERISTICAS order
    assert d["url"] == "https://example.com/1"


def test_prop_to_dict_bajada_only_when_lower():
    d = prop_to_dict(_prop(precio_anterior=195_000.0))
    assert d["bajada"] == 6_000
    d2 = prop_to_dict(_prop(precio_anterior=180_000.0))
    assert d2["bajada"] is None


def test_prop_to_dict_manual_badge():
    d = prop_to_dict(_prop(fuente_id=99), fuente_manual_id=99)
    assert d["es_manual"] is True


# ── counts_from_rows ──────────────────────────────────────────────────

def test_counts_from_rows():
    rows = [
        # (activa, vista, descartada, favorita)
        (True, False, False, False),   # nueva + todas
        (True, True, False, True),     # todas + favorita
        (True, True, True, False),     # descartada
        (False, True, False, False),   # vendida
    ]
    c = counts_from_rows(rows)
    assert c == {"nuevas": 1, "todas": 2, "favoritas": 1, "descartadas": 1, "vendidas": 1}


def test_counts_from_rows_empty():
    assert counts_from_rows([]) == {"nuevas": 0, "todas": 0, "favoritas": 0, "descartadas": 0, "vendidas": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_property_queries.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'ui.property_queries'`.

- [ ] **Step 3: Implement `app/ui/property_queries.py`**

```python
"""Capa de consultas de Propiedades 2.0 — funciones puras, sin Streamlit."""

from datetime import datetime, UTC

from sqlalchemy import or_
from sqlmodel import select

from db.models import Propiedad

# label → nombre de campo en Propiedad (el orden define el orden de los chips)
CARACTERISTICAS = {
    "Ascensor": "ascensor",
    "Garaje": "garaje",
    "Trastero": "trastero",
    "Terraza": "terraza",
    "Balcón": "balcon",
    "Patio": "patio",
    "Piscina": "piscina",
    "A/C": "aire_acondicionado",
    "Amueblado": "amueblado",
    "Mascotas": "mascotas",
}

SORT_OPTIONS = {
    "Más reciente": ("fecha_scraping", "desc"),
    "Más antiguo": ("fecha_scraping", "asc"),
    "Precio (menor)": ("precio", "asc"),
    "Precio (mayor)": ("precio", "desc"),
    "m² (mayor)": ("superficie_m2", "desc"),
}

RESULT_LIMIT = 300


def tab_conditions(tab: str) -> list:
    """Condiciones SQL de cada pestaña de estado."""
    if tab == "nuevas":
        return [Propiedad.activa == True, Propiedad.descartada == False, Propiedad.vista == False]
    if tab == "todas":
        return [Propiedad.activa == True, Propiedad.descartada == False]
    if tab == "favoritas":
        return [Propiedad.favorita == True]
    if tab == "descartadas":
        return [Propiedad.descartada == True]
    if tab == "vendidas":
        return [Propiedad.activa == False]
    raise ValueError(f"Pestaña desconocida: {tab}")


def filter_conditions(filters: dict) -> list:
    """Condiciones SQL del formulario de filtros.

    Los numéricos incluyen NULL (dato desconocido no excluye); las
    características exigen True; tipos/distritos usan IN.
    """
    conds = []
    if filters.get("precio_min"):
        conds.append(or_(Propiedad.precio >= filters["precio_min"], Propiedad.precio == None))
    if filters.get("precio_max"):
        conds.append(or_(Propiedad.precio <= filters["precio_max"], Propiedad.precio == None))
    if filters.get("m2_min"):
        conds.append(or_(Propiedad.superficie_m2 >= filters["m2_min"], Propiedad.superficie_m2 == None))
    if filters.get("hab_min"):
        conds.append(or_(Propiedad.habitaciones >= filters["hab_min"], Propiedad.habitaciones == None))
    if filters.get("banos_min"):
        conds.append(or_(Propiedad.banos >= filters["banos_min"], Propiedad.banos == None))
    if filters.get("tipos"):
        conds.append(Propiedad.tipo_propiedad.in_(filters["tipos"]))
    if filters.get("distritos"):
        conds.append(Propiedad.distrito.in_(filters["distritos"]))
    for label in filters.get("caracteristicas", []):
        conds.append(getattr(Propiedad, CARACTERISTICAS[label]) == True)
    if filters.get("search"):
        s = f"%{filters['search']}%"
        conds.append(or_(Propiedad.titulo.ilike(s), Propiedad.descripcion.ilike(s)))
    return conds


def build_stmt(tab: str, filters: dict, sort_key: str):
    """Select completo de la pestaña: condiciones + orden + límite."""
    stmt = select(Propiedad)
    for cond in tab_conditions(tab) + filter_conditions(filters):
        stmt = stmt.where(cond)
    field, direction = SORT_OPTIONS[sort_key]
    col = getattr(Propiedad, field)
    stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc())
    return stmt.limit(RESULT_LIMIT)


def precio_por_m2(precio, superficie):
    if not precio or not superficie:
        return None
    return round(precio / superficie)


def prop_to_dict(prop: Propiedad, fuente_manual_id: int | None = None) -> dict:
    """Dict plano para la tarjeta — sin objetos ORM vivos."""
    bajada = None
    if prop.precio and prop.precio_anterior and prop.precio_anterior > prop.precio:
        bajada = round(prop.precio_anterior - prop.precio)
    dias = None
    if prop.fecha_scraping:
        dias = (datetime.now(UTC).replace(tzinfo=None) - prop.fecha_scraping).days
    return {
        "id": prop.id,
        "titulo": prop.titulo,
        "precio": prop.precio,
        "bajada": bajada,
        "precio_m2": precio_por_m2(prop.precio, prop.superficie_m2),
        "superficie": prop.superficie_m2,
        "habitaciones": prop.habitaciones,
        "banos": prop.banos,
        "tipo": prop.tipo_propiedad,
        "barrio": prop.barrio,
        "municipio": prop.municipio,
        "chips": [label for label, field in CARACTERISTICAS.items() if getattr(prop, field)],
        "fotos": prop.fotos or [],
        "url": prop.url_original,
        "origen": prop.origen_web,
        "dias": dias,
        "es_manual": prop.fuente_id == fuente_manual_id,
        "activa": prop.activa,
        "estado": prop.estado,
        "vista": prop.vista,
        "favorita": prop.favorita,
        "descartada": prop.descartada,
    }


def counts_from_rows(rows) -> dict:
    """Contadores de pestañas desde tuplas (activa, vista, descartada, favorita)."""
    c = {"nuevas": 0, "todas": 0, "favoritas": 0, "descartadas": 0, "vendidas": 0}
    for activa, vista, descartada, favorita in rows:
        if activa and not descartada:
            c["todas"] += 1
            if not vista:
                c["nuevas"] += 1
        if favorita:
            c["favoritas"] += 1
        if descartada:
            c["descartadas"] += 1
        if not activa:
            c["vendidas"] += 1
    return c
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_property_queries.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ui/property_queries.py tests/test_property_queries.py
git commit -m "feat: pure query layer for propiedades 2.0 (tabs, filters, dicts, counts)"
```

---

### Task 3: Card renderer `property_card.py`

**Files:**
- Create: `app/ui/property_card.py`
- Test: `tests/test_property_card.py`

**Interfaces:**
- Consumes: dicts produced by `prop_to_dict` (Task 2); dialogs from Task 4 (`edit_property_dialog`, `calculadora_modal`, `fotos_dialog`) — imported lazily inside the fragment so this task's pure part is testable before Task 4 exists.
- Produces (used by Task 5):
  - `fmt_eur(v: float) -> str` — `189000 → "189.000 €"`.
  - `card_html(p: dict) -> str` — pure HTML for one card.
  - `render_card(p: dict, on_write: callable) -> None` — `@st.fragment` that renders HTML + action buttons; calls `on_write()` after every DB write.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_property_card.py`:

```python
"""Tests for the pure HTML card builder of Propiedades 2.0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from ui.property_card import card_html, fmt_eur


def _p(**kwargs):
    base = {
        "id": 1,
        "titulo": "Piso céntrico",
        "precio": 189_000.0,
        "bajada": None,
        "precio_m2": 1853,
        "superficie": 102.0,
        "habitaciones": 3,
        "banos": 2,
        "tipo": "piso",
        "barrio": "Centro",
        "municipio": "El Puerto de Santa María",
        "chips": ["Ascensor", "Terraza"],
        "fotos": ["https://img.example.com/1.jpg"],
        "url": "https://example.com/1",
        "origen": "example.com",
        "dias": 2,
        "es_manual": False,
        "activa": True,
        "estado": None,
        "vista": False,
        "favorita": False,
        "descartada": False,
    }
    base.update(kwargs)
    return base


def test_fmt_eur_spanish_thousands():
    assert fmt_eur(189_000) == "189.000 €"
    assert fmt_eur(1_500) == "1.500 €"


def test_card_shows_price_and_m2():
    html = card_html(_p())
    assert "189.000 €" in html
    assert "1.853 €/m²" in html


def test_card_bajada_only_when_present():
    assert "↓" not in card_html(_p())
    html = card_html(_p(bajada=6_000))
    assert "↓" in html and "6.000 €" in html


def test_card_photo_and_placeholder():
    html = card_html(_p())
    assert '<img src="https://img.example.com/1.jpg"' in html
    html_sin = card_html(_p(fotos=[]))
    assert "<img" not in html_sin
    assert "🏠" in html_sin


def test_card_chips_and_location():
    html = card_html(_p())
    assert "Ascensor" in html and "Terraza" in html
    assert "Centro, El Puerto de Santa María" in html


def test_card_escapes_title_html():
    html = card_html(_p(titulo='<script>alert("x")</script>'))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_card_inactive_strikethrough():
    html = card_html(_p(activa=False, estado="Vendida"))
    assert "<s>" in html and "Vendida" in html


def test_card_missing_data_degrades():
    html = card_html(_p(precio=None, precio_m2=None, superficie=None, habitaciones=None, banos=None, dias=None))
    assert "Precio N/D" in html
    assert "€/m²" not in html


def test_card_manual_badge():
    assert "📌 Manual" in card_html(_p(es_manual=True))
    assert "📌 Manual" not in card_html(_p())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_property_card.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'ui.property_card'`.

- [ ] **Step 3: Implement `app/ui/property_card.py`**

```python
"""Tarjeta visual de propiedad: HTML puro + fragment de acciones."""

import html as html_lib

import streamlit as st
from sqlmodel import Session

from db.database import engine, PropiedadCRUD
from db.models import Propiedad

_PLACEHOLDER = (
    '<div style="width:100%;aspect-ratio:16/9;{display}align-items:center;'
    'justify-content:center;background:#f0f2f6;border-radius:8px;font-size:2.5rem;">🏠</div>'
)

_CHIP = (
    '<span style="display:inline-block;background:#eef1f6;border-radius:12px;'
    'padding:1px 10px;margin:2px 4px 2px 0;font-size:0.78rem;">{label}</span>'
)


def fmt_eur(v) -> str:
    return f"{v:,.0f}".replace(",", ".") + " €"


def _foto_html(p: dict) -> str:
    if p["fotos"]:
        return (
            f'<img src="{html_lib.escape(p["fotos"][0], quote=True)}" '
            'style="width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;" '
            "onerror=\"this.style.display='none';this.nextElementSibling.style.display='flex';\">"
            + _PLACEHOLDER.format(display="display:none;")
        )
    return _PLACEHOLDER.format(display="display:flex;")


def card_html(p: dict) -> str:
    """HTML completo de una tarjeta a partir del dict de prop_to_dict."""
    titulo = html_lib.escape(p["titulo"] or "Sin título")[:80]
    if not p["activa"]:
        titulo = f"<s>{titulo}</s> 🚫 {html_lib.escape(p['estado'] or 'Vendida')}"

    precio = fmt_eur(p["precio"]) if p["precio"] else "Precio N/D"
    bajada = (
        f' <span style="color:#21a366;font-size:0.95rem;font-weight:600;">↓ −{fmt_eur(p["bajada"])}</span>'
        if p["bajada"] else ""
    )
    m2_line = (
        f'<div style="color:#6b7280;font-size:0.85rem;">{fmt_eur(p["precio_m2"])[:-2]} €/m²</div>'
        if p["precio_m2"] else ""
    )

    resumen = " · ".join(
        x for x in [
            html_lib.escape(p["tipo"]) if p["tipo"] else None,
            f'{p["superficie"]:.0f} m²' if p["superficie"] else None,
            f'{p["habitaciones"]} hab' if p["habitaciones"] else None,
            f'{p["banos"]} baños' if p["banos"] else None,
        ] if x
    )
    ubicacion = ", ".join(html_lib.escape(x) for x in [p["barrio"], p["municipio"]] if x)
    chips = "".join(_CHIP.format(label=html_lib.escape(c)) for c in p["chips"])

    meta = []
    if p["origen"]:
        meta.append(f"🌐 {html_lib.escape(p['origen'])}")
    if p["dias"] is not None:
        meta.append("hoy" if p["dias"] == 0 else f"hace {p['dias']}d")
    if p["es_manual"]:
        meta.append("📌 Manual")

    return (
        f"{_foto_html(p)}"
        f'<div style="font-weight:600;margin-top:6px;line-height:1.3;">{titulo}</div>'
        f'<div style="font-size:1.35rem;font-weight:700;margin-top:2px;">{precio}{bajada}</div>'
        f"{m2_line}"
        f'<div style="font-size:0.9rem;margin-top:4px;">{resumen}</div>'
        + (f'<div style="font-size:0.85rem;color:#6b7280;">📍 {ubicacion}</div>' if ubicacion else "")
        + (f'<div style="margin-top:4px;">{chips}</div>' if chips else "")
        + (f'<div style="font-size:0.78rem;color:#9ca3af;margin-top:4px;">{" · ".join(meta)}</div>' if meta else "")
    )


def _write(p: dict, on_write, **fields):
    """Escribe campos en BD, actualiza el dict local y re-renderiza solo la tarjeta."""
    try:
        with Session(engine) as session:
            PropiedadCRUD.update(session, p["id"], **fields)
        p.update(fields)
        on_write()
        st.rerun(scope="fragment")
    except Exception as e:
        st.error(f"Error al guardar: {e}")


@st.fragment
def render_card(p: dict, on_write):
    """Tarjeta completa: HTML + fila de acciones. Cada acción re-ejecuta solo este fragment."""
    from ui.property_dialogs import calculadora_modal, edit_property_dialog, fotos_dialog

    with st.container(border=True):
        st.markdown(card_html(p), unsafe_allow_html=True)

        b = st.columns(7)
        if b[0].button("❤️" if p["favorita"] else "🤍", key=f"fav_{p['id']}", help="Favorita"):
            _write(p, on_write, favorita=not p["favorita"], vista=True)
        if b[1].button("↩️" if p["descartada"] else "❌", key=f"disc_{p['id']}",
                       help="Restaurar" if p["descartada"] else "Descartar"):
            _write(p, on_write, descartada=not p["descartada"], vista=True)
        if b[2].button("✏️", key=f"edit_{p['id']}", help="Editar"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            edit_property_dialog(prop)
        if b[3].button("🧮", key=f"calc_{p['id']}", help="Calculadora"):
            with Session(engine) as session:
                prop = session.get(Propiedad, p["id"])
            calculadora_modal(prop)
        if p["fotos"]:
            if b[4].button("📸", key=f"fotos_{p['id']}", help="Ver fotos"):
                st.session_state[f"foto_idx_{p['id']}"] = 0
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                fotos_dialog(prop)
        b[5].link_button("🔗", p["url"], help="Abrir anuncio")
        if b[6].button("✓" if p["vista"] else "👁", key=f"view_{p['id']}", help="Marcar vista"):
            _write(p, on_write, vista=not p["vista"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_property_card.py -v`
Expected: all PASS (the tests only import `card_html`/`fmt_eur`; importing the module pulls in `streamlit`, which is installed).

- [ ] **Step 5: Commit**

```bash
git add app/ui/property_card.py tests/test_property_card.py
git commit -m "feat: visual property card with photo, price drop, eur/m2 and fragment actions"
```

---

### Task 4: Move dialogs to `property_dialogs.py`

**Files:**
- Create: `app/ui/property_dialogs.py`
- Reference (do not modify yet — Task 5 rewrites it): `app/pages/2_propiedades.py`

**Interfaces:**
- Consumes: `db.database.engine/PropiedadCRUD`, `db.models`, `utils.calculadora`, `scraper.url_extractor`.
- Produces (used by Tasks 3 and 5):
  - `get_or_create_fuente_manual(session) -> int`
  - `add_url_dialog() -> None` — `@st.dialog`, now takes NO session argument.
  - `edit_property_dialog(prop: Propiedad) -> None` — `@st.dialog`, unchanged.
  - `calculadora_modal(prop: Propiedad) -> None` — `@st.dialog`, unchanged.
  - `fotos_dialog(prop: Propiedad) -> None` — `@st.dialog`, unchanged.

- [ ] **Step 1: Create the module with header + moved code**

Create `app/ui/property_dialogs.py` starting with this header:

```python
"""Modales de la página Propiedades: editar, calculadora, fotos y añadir por URL.

Código movido desde app/pages/2_propiedades.py sin cambios funcionales,
salvo add_url_dialog, que ahora abre su propia sesión de BD.
"""

import streamlit as st
from sqlmodel import Session, select

from db.database import engine, PropiedadCRUD
from db.models import Propiedad, PrecioHistorico
from utils.calculadora import (
    calcular_compraventa,
    calcular_gastos_hipoteca,
    calcular_aportacion_necesaria,
    calcular_hipoteca,
)
```

Then copy, verbatim from the current `app/pages/2_propiedades.py` (commit `da799e2` state):

1. Lines 25–41 (`_get_or_create_fuente_manual`) — rename the function to `get_or_create_fuente_manual` (drop the underscore; it becomes public API).
2. Lines 44–127 (`add_url_dialog`) — with the two changes in Step 2 below.
3. Lines 149–295 (`edit_property_dialog`) — verbatim.
4. Lines 298–388 (`calculadora_modal`) — verbatim.
5. Lines 391–417 (`fotos_dialog`) — verbatim.

- [ ] **Step 2: Make `add_url_dialog` self-contained**

Change its signature from `def add_url_dialog(session):` to `def add_url_dialog():`, and replace the body of the save handler (the `if st.button("💾 Guardar", ...)` block) so all DB work happens in a fresh session:

```python
    if st.button("💾 Guardar", disabled=not precio or not url.strip()):
        try:
            hash_unico = hashlib.sha256(url.strip().encode()).hexdigest()
            with Session(engine) as session:
                fuente_manual_id = get_or_create_fuente_manual(session)
                propiedad = Propiedad(
                    hash_unico=hash_unico,
                    url_original=url.strip(),
                    fuente_id=fuente_manual_id,
                    origen_web=urlparse(url.strip()).netloc,
                    titulo=titulo or url.strip(),
                    precio=float(precio),
                    superficie_m2=superficie or None,
                    habitaciones=habitaciones or None,
                    banos=banos or None,
                    municipio=municipio or None,
                    tipo_propiedad=tipo_propiedad,
                    descripcion=notas_campo or None,
                    activa=True,
                    fecha_scraping=datetime.utcnow(),
                )
                session.add(propiedad)
                session.commit()
                session.refresh(propiedad)
                if propiedad.precio:
                    session.add(PrecioHistorico(propiedad_id=propiedad.id, precio=propiedad.precio))
                    session.commit()
                titulo_guardado = propiedad.titulo[:50]
            st.session_state["add_url_extracted"] = {}
            st.session_state["add_url_value"] = ""
            st.success(f"✅ Propiedad guardada: {titulo_guardado}")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")
```

Also update the internal call `_get_or_create_fuente_manual(session)` → `get_or_create_fuente_manual(session)` (inside the moved save block above it is already correct), and remove the now-redundant local imports inside `add_url_dialog` for anything the module header already imports (`Propiedad`, `PrecioHistorico`); keep `import asyncio`, `import hashlib`, `from urllib.parse import urlparse`, `from datetime import datetime`, `from scraper.url_extractor import extract_from_url` as local imports exactly as they are today.

- [ ] **Step 3: Verify the module imports and nothing broke**

Run: `python -c "import sys; sys.path.insert(0, 'app'); import ui.property_dialogs as d; print([f for f in dir(d) if not f.startswith('_')])"` (from repo root)
Expected: list includes `add_url_dialog`, `calculadora_modal`, `edit_property_dialog`, `fotos_dialog`, `get_or_create_fuente_manual`.

Run: `pytest`
Expected: full suite PASSES (the old page file still exists untouched; no test imports it).

- [ ] **Step 4: Commit**

```bash
git add app/ui/property_dialogs.py
git commit -m "refactor: move property dialogs to app/ui/property_dialogs (self-contained sessions)"
```

---

### Task 5: Rewrite the page `2_propiedades.py`

**Files:**
- Modify (full rewrite): `app/pages/2_propiedades.py`

**Interfaces:**
- Consumes: everything produced by Tasks 2–4:
  - `ui.property_queries`: `build_stmt(tab, filters, sort_key)`, `filter_conditions(filters)`, `prop_to_dict(prop, fuente_manual_id)`, `counts_from_rows(rows)`, `CARACTERISTICAS`, `SORT_OPTIONS`
  - `ui.property_card`: `render_card(p, on_write)`
  - `ui.property_dialogs`: `add_url_dialog()`, `get_or_create_fuente_manual(session)`
- Produces: the final page. No other module imports it.

- [ ] **Step 1: Replace the entire file**

New content of `app/pages/2_propiedades.py`:

```python
"""Propiedades 2.0: triaje por pestañas, tarjetas visuales, filtros en formulario."""

import json
import math
import sys
from pathlib import Path

import streamlit as st
from sqlalchemy import distinct, update as sa_update
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import engine
from db.models import Propiedad
from ui.property_card import render_card
from ui.property_dialogs import add_url_dialog, get_or_create_fuente_manual
from ui.property_queries import (
    CARACTERISTICAS,
    SORT_OPTIONS,
    build_stmt,
    counts_from_rows,
    filter_conditions,
    prop_to_dict,
)

st.set_page_config(page_title="Propiedades", page_icon="🏘️", layout="wide")

PAGE_SIZE = 12
TABS = {
    "nuevas": "🆕 Nuevas",
    "todas": "📋 Todas",
    "favoritas": "❤️ Favoritas",
    "descartadas": "❌ Descartadas",
    "vendidas": "🚫 Vendidas",
}
DEFAULT_FILTERS = {
    "precio_min": 0, "precio_max": 0, "m2_min": 0, "hab_min": 0, "banos_min": 0,
    "tipos": [], "distritos": [], "caracteristicas": [], "search": "",
}
FILTER_WIDGET_KEYS = [
    "f_precio_min", "f_precio_max", "f_m2_min", "f_hab_min", "f_banos_min",
    "f_tipos", "f_distritos", "f_caracteristicas", "f_search",
]


# ── Fetches cacheados ─────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def fetch_props(tab: str, filters_json: str, sort_key: str) -> list[dict]:
    filters = json.loads(filters_json)
    with Session(engine) as session:
        fuente_manual_id = get_or_create_fuente_manual(session)
        props = session.exec(build_stmt(tab, filters, sort_key)).all()
        return [prop_to_dict(p, fuente_manual_id) for p in props]


@st.cache_data(ttl=60, show_spinner=False)
def fetch_counts() -> dict:
    with Session(engine) as session:
        rows = session.exec(
            select(Propiedad.activa, Propiedad.vista, Propiedad.descartada, Propiedad.favorita)
        ).all()
    return counts_from_rows(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_filter_options() -> tuple[list, list]:
    with Session(engine) as session:
        tipos = session.exec(
            select(distinct(Propiedad.tipo_propiedad)).where(Propiedad.tipo_propiedad != None).limit(50)
        ).all()
        distritos = session.exec(
            select(distinct(Propiedad.distrito)).where(Propiedad.distrito != None).limit(50)
        ).all()
    return sorted(t for t in tipos if t), sorted(d for d in distritos if d)


def clear_prop_caches():
    fetch_props.clear()
    fetch_counts.clear()


def reset_page():
    st.session_state.page = 1


def filtros_activos_resumen(f: dict) -> str:
    parts = []
    if f["precio_min"]:
        parts.append(f"≥{f['precio_min']:,.0f} €".replace(",", "."))
    if f["precio_max"]:
        parts.append(f"≤{f['precio_max']:,.0f} €".replace(",", "."))
    if f["m2_min"]:
        parts.append(f"≥{f['m2_min']} m²")
    if f["hab_min"]:
        parts.append(f"≥{f['hab_min']} hab")
    if f["banos_min"]:
        parts.append(f"≥{f['banos_min']} baños")
    parts += f["tipos"] + f["distritos"] + f["caracteristicas"]
    if f["search"]:
        parts.append(f"«{f['search']}»")
    return " · ".join(parts)


# ── Estado ────────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state.page = 1
if "filters" not in st.session_state:
    st.session_state.filters = dict(DEFAULT_FILTERS)
if "bulk_discard_confirm" not in st.session_state:
    st.session_state.bulk_discard_confirm = False

try:
    # ── Cabecera ──────────────────────────────────────────────────────
    col_title, col_add = st.columns([5, 1], vertical_alignment="bottom")
    with col_title:
        st.title("🏘️ Propiedades")
    with col_add:
        if st.button("➕ Añadir URL", use_container_width=True):
            add_url_dialog()

    # ── Pestañas de estado ────────────────────────────────────────────
    counts = fetch_counts()
    tab = st.segmented_control(
        "Estado",
        options=list(TABS.keys()),
        format_func=lambda k: f"{TABS[k]} ({counts[k]})",
        default="nuevas",
        key="tab",
        label_visibility="collapsed",
        on_change=reset_page,
    ) or "nuevas"

    # ── Filtros ───────────────────────────────────────────────────────
    tipos_opts, distritos_opts = fetch_filter_options()
    with st.expander("🔍 Filtros", expanded=False):
        with st.form("filtros", border=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.number_input("Precio mín (€)", min_value=0, step=10_000, key="f_precio_min")
            c2.number_input("Precio máx (€)", min_value=0, step=10_000, key="f_precio_max")
            c3.number_input("m² mín", min_value=0, step=10, key="f_m2_min")
            c4.number_input("Hab. mín", min_value=0, step=1, key="f_hab_min")
            c5.number_input("Baños mín", min_value=0, step=1, key="f_banos_min")
            c6, c7 = st.columns(2)
            c6.multiselect("Tipo", tipos_opts, key="f_tipos")
            c7.multiselect("Distrito", distritos_opts, key="f_distritos")
            st.multiselect("Características (debe tener todas)", list(CARACTERISTICAS.keys()), key="f_caracteristicas")
            st.text_input("Buscar en título/descripción", key="f_search")

            col_apply, col_clear = st.columns([1, 1])
            aplicar = col_apply.form_submit_button("Aplicar", type="primary", use_container_width=True)
            limpiar = col_clear.form_submit_button("Limpiar", use_container_width=True)

    if aplicar:
        st.session_state.filters = {
            "precio_min": st.session_state.f_precio_min,
            "precio_max": st.session_state.f_precio_max,
            "m2_min": st.session_state.f_m2_min,
            "hab_min": st.session_state.f_hab_min,
            "banos_min": st.session_state.f_banos_min,
            "tipos": st.session_state.f_tipos,
            "distritos": st.session_state.f_distritos,
            "caracteristicas": st.session_state.f_caracteristicas,
            "search": st.session_state.f_search.strip(),
        }
        st.session_state.page = 1
    if limpiar:
        st.session_state.filters = dict(DEFAULT_FILTERS)
        st.session_state.page = 1
        for k in FILTER_WIDGET_KEYS:
            st.session_state.pop(k, None)
        st.rerun()

    filters = st.session_state.filters

    # ── Barra de resultados ───────────────────────────────────────────
    props = fetch_props(tab, json.dumps(filters, sort_keys=True), st.session_state.get("sort", "Más reciente"))
    total = len(props)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(st.session_state.page, total_pages)
    st.session_state.page = page

    col_sort, col_info = st.columns([1, 3], vertical_alignment="bottom")
    with col_sort:
        st.selectbox("Ordenar por", list(SORT_OPTIONS.keys()), key="sort", on_change=reset_page)
    with col_info:
        resumen = filtros_activos_resumen(filters)
        st.markdown(f"**{total}** resultados" + (f" &nbsp;·&nbsp; 🔍 {resumen}" if resumen else ""))

    st.divider()

    # ── Grid de tarjetas ──────────────────────────────────────────────
    if not props:
        st.info("No hay propiedades en esta pestaña con los filtros actuales.")
    else:
        page_items = props[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        cols = st.columns(3)
        for i, p in enumerate(page_items):
            with cols[i % 3]:
                render_card(p, on_write=clear_prop_caches)

        # ── Paginación + visto todo ───────────────────────────────────
        col_prev, col_mid, col_next = st.columns([1, 2, 1])
        if col_prev.button("← Anterior", disabled=page <= 1, use_container_width=True):
            st.session_state.page = page - 1
            st.rerun()
        with col_mid:
            st.caption(f"Página {page} de {total_pages} · {total} propiedades")
            if tab == "nuevas" and st.button("✓ Visto todo (esta página)", use_container_width=True):
                with Session(engine) as session:
                    session.execute(
                        sa_update(Propiedad)
                        .where(Propiedad.id.in_([p["id"] for p in page_items]))
                        .values(vista=True)
                    )
                    session.commit()
                clear_prop_caches()
                st.rerun()
        if col_next.button("Siguiente →", disabled=page >= total_pages, use_container_width=True):
            st.session_state.page = page + 1
            st.rerun()

    # ── Herramientas ──────────────────────────────────────────────────
    with st.expander("⚙️ Herramientas"):
        st.subheader("🗑️ Descarte masivo")
        st.caption("Descarta todas las propiedades activas que coinciden con los filtros aplicados (todas las páginas).")
        with Session(engine) as session:
            bulk_stmt = select(Propiedad.id).where(Propiedad.activa == True, Propiedad.descartada == False)
            for cond in filter_conditions(filters):
                bulk_stmt = bulk_stmt.where(cond)
            bulk_ids = list(session.exec(bulk_stmt).all())

        if not bulk_ids:
            st.caption("Ninguna propiedad activa sin descartar con el filtro actual.")
        elif not st.session_state.bulk_discard_confirm:
            if st.button(f"🗑️ Descartar todas ({len(bulk_ids)})"):
                st.session_state.bulk_discard_confirm = True
                st.rerun()
        else:
            st.warning(f"⚠️ ¿Marcar {len(bulk_ids)} propiedades como descartadas?")
            col_yes, col_no = st.columns(2)
            if col_yes.button("✅ Sí, descartar", type="primary", use_container_width=True):
                with Session(engine) as session:
                    session.execute(
                        sa_update(Propiedad).where(Propiedad.id.in_(bulk_ids)).values(descartada=True, vista=True)
                    )
                    session.commit()
                st.session_state.bulk_discard_confirm = False
                clear_prop_caches()
                st.success(f"✅ {len(bulk_ids)} descartadas")
                st.rerun()
            if col_no.button("❌ Cancelar", use_container_width=True):
                st.session_state.bulk_discard_confirm = False
                st.rerun()

        st.divider()
        st.subheader("🔍 Verificar vendidas")
        with Session(engine) as session:
            active_count = len(session.exec(select(Propiedad.id).where(Propiedad.activa == True)).all())
        st.caption(f"{active_count} propiedades activas a verificar. Descarga cada ficha y marca como vendidas las que estén reservadas o vendidas.")
        if st.button("🔍 Verificar ahora", key="verify_sold_btn"):
            import asyncio
            from scraper.sold_checker import check_sold_properties as _check_sold
            with st.spinner(f"Verificando {active_count} propiedades... (puede tardar varios minutos)"):
                with Session(engine) as verify_session:
                    sold_stats = asyncio.run(_check_sold(verify_session))
            st.success(f"✅ Completado — {sold_stats.get('vendidas', 0)} vendidas, {sold_stats.get('errores', 0)} errores")
            clear_prop_caches()
            st.rerun()

except Exception as e:
    st.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest`
Expected: all PASS (no test imports the page module; Tasks 2–3 tests cover the logic).

- [ ] **Step 3: Manual verification with the running app**

Run: `streamlit run app/main.py`, open the Propiedades page and verify:

1. Lands on 🆕 Nuevas with correct counters on every tab; switching tabs changes the grid and resets to page 1.
2. Cards show photo (or 🏠 placeholder), price, €/m², summary line, location, chips, meta; sold tab shows strikethrough titles.
3. ❤️ and ❌ act instantly WITHOUT full page reload (only the card flickers); the property stays in place until the tab is reloaded; counters update after a rerun (cache cleared).
4. ✏️, 🧮 and 📸 open the same dialogs as before; 🔗 opens the listing; ➕ Añadir URL extracts and saves.
5. Filters apply only on "Aplicar"; "Limpiar" resets widgets and results; the active-filter summary shows next to the result count; NULL semantics: a property without price still appears with a price filter set.
6. Sorting works and resets to page 1; ← → paginate; "✓ Visto todo" empties the Nuevas page after rerun.
7. Herramientas: bulk discard asks for confirmation and works over the applied filters; "Verificar vendidas" runs.

- [ ] **Step 4: Commit**

```bash
git add app/pages/2_propiedades.py
git commit -m "feat: propiedades 2.0 - state tabs, visual cards, form filters, fragment triage"
```

---

### Task 6: Final review pass

**Files:**
- Verify only; no planned changes.

- [ ] **Step 1: Full suite + quick import smoke test**

Run: `pytest`
Expected: all PASS.

Run: `python -c "import sys; sys.path.insert(0,'app'); import ui.property_queries, ui.property_card, ui.property_dialogs; print('ok')"`
Expected: `ok`.

- [ ] **Step 2: Spec cross-check**

Re-read `docs/superpowers/specs/2026-07-16-propiedades-2.0-design.md` section by section and confirm each requirement maps to shipped code (tabs §1, card §2, filters §3, performance §4, preserved dialogs/tools §5, code layout §6, error handling §7, tests §8). Fix any gap found before closing.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: propiedades 2.0 review follow-ups"
```

(Skip the commit if Step 2 found nothing.)

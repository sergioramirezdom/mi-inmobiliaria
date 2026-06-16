# Manual URL Property Tracking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to paste a single property URL from any small agency, auto-extract data, manually complete the form, and have the scheduler monitor it for price drops and sold status.

**Architecture:** A pure `url_extractor.py` handles HTTP fetch + HTML parsing (testable). A `ManualScraper` wraps it for the sold_checker interface. The UI adds a `@st.dialog` to `2_propiedades.py` with a two-step flow (URL → extract → form → save). All manual properties link to a special `Fuente(nombre="Manual", activa=False)` row auto-created on first use.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup4, Streamlit, SQLModel/PostgreSQL (Neon Tech), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/scraper/url_extractor.py` | Create | HTTP fetch + HTML parsing → dict |
| `app/scraper/manual_scraper.py` | Create | Sold/price monitoring interface for sold_checker |
| `app/scraper/sold_checker.py` | Modify | Wire ManualScraper + price change detection for manual props |
| `app/scraper/paginated_scraper.py` | Modify | Wire ManualScraper (consistency) |
| `app/pages/2_propiedades.py` | Modify | Add dialog + sidebar button + "📌 Manual" badge |
| `tests/test_url_extractor.py` | Create | Unit tests for `_parse_html` and `_parse_price` |

---

## Task 1: Create `app/scraper/url_extractor.py`

**Files:**
- Create: `app/scraper/url_extractor.py`
- Create: `tests/test_url_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_url_extractor.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.url_extractor import _parse_html, _parse_price, _parse_float


def test_parse_price_european_thousands():
    assert _parse_price("195.000") == 195000.0

def test_parse_price_with_comma_decimal():
    assert _parse_price("195.000,50") == 195000.50

def test_parse_price_plain():
    assert _parse_price("195000") == 195000.0

def test_parse_price_invalid():
    assert _parse_price("no-price") is None

def test_parse_float_comma():
    assert _parse_float("69,84") == 69.84

def test_parse_float_dot():
    assert _parse_float("69.84") == 69.84


def test_parse_html_price_from_meta():
    html = '''<html><head>
        <meta property="og:price:amount" content="195000">
    </head><body></body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_price_from_text():
    html = '''<html><body>
        <p>Precio de venta: 195.000 €</p>
    </body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_price_below_10k_ignored():
    html = '''<html><body><p>Gastos comunidad: 80 €. Precio: 195.000 €</p></body></html>'''
    data = _parse_html(html)
    assert data["precio"] == 195000.0


def test_parse_html_title_from_og():
    html = '''<html><head>
        <meta property="og:title" content="Magnífico piso en El Puerto">
    </head><body><h1>Otro título</h1></body></html>'''
    data = _parse_html(html)
    assert data["titulo"] == "Magnífico piso en El Puerto"


def test_parse_html_title_from_h1():
    html = '''<html><body><h1>Piso en venta en El Puerto</h1></body></html>'''
    data = _parse_html(html)
    assert data["titulo"] == "Piso en venta en El Puerto"


def test_parse_html_surface():
    html = '''<html><body><p>120 m² construidos, 3 habitaciones</p></body></html>'''
    data = _parse_html(html)
    assert data["superficie_m2"] == 120.0


def test_parse_html_rooms_and_baths():
    html = '''<html><body><p>3 habitaciones, 2 baños</p></body></html>'''
    data = _parse_html(html)
    assert data["habitaciones"] == 3
    assert data["banos"] == 2


def test_parse_html_rooms_dormitorios():
    html = '''<html><body><p>4 dormitorios y 2 baños</p></body></html>'''
    data = _parse_html(html)
    assert data["habitaciones"] == 4


def test_parse_html_sold_keyword_vendida():
    html = '''<html><body><p>Esta propiedad está vendida.</p><p>Precio: 195.000 €</p></body></html>'''
    data = _parse_html(html)
    assert data["activa"] is False
    assert data["estado"] == "Vendida"


def test_parse_html_sold_keyword_reservado():
    html = '''<html><body><p>RESERVADO. Contacte para más info.</p></body></html>'''
    data = _parse_html(html)
    assert data["activa"] is False


def test_parse_html_surface_over_2000_ignored():
    html = '''<html><body><p>Finca de 5000 m², 3 habitaciones</p></body></html>'''
    data = _parse_html(html)
    assert "superficie_m2" not in data
```

- [ ] **Step 2: Run tests — must fail**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -m pytest tests/test_url_extractor.py -v 2>&1 | tail -10
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `app/scraper/url_extractor.py`**

```python
"""Generic property data extractor for individual URLs."""

import re
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

_SOLD_KEYWORDS = ("vendido", "vendida", "reservado", "reservada")


async def extract_from_url(url: str) -> dict:
    """
    Fetch a property page and extract basic data.
    Always returns a dict — never raises.
    On HTTP/network error sets "error" key.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, verify=True, timeout=15) as client:
            response = await client.get(url, headers=BROWSER_HEADERS)
            if response.status_code == 404:
                return {"error": "URL no encontrada (404)"}
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}
            html = response.text
    except Exception as e:
        return {"error": str(e)}

    return _parse_html(html)


def _parse_html(html: str) -> dict:
    """Parse HTML and extract property fields. Pure function — no HTTP calls."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    lower_text = page_text.lower()
    data: dict = {}

    # Sold detection — check first 3000 chars
    for keyword in _SOLD_KEYWORDS:
        if keyword in lower_text[:3000]:
            return {"activa": False, "estado": keyword.capitalize()}

    # Price — meta tags first, then regex in page text
    for meta_name in ("og:price:amount", "product:price:amount", "price"):
        tag = (
            soup.find("meta", attrs={"property": meta_name})
            or soup.find("meta", attrs={"name": meta_name})
        )
        if tag and tag.get("content"):
            price = _parse_price(tag["content"])
            if price and price > 10_000:
                data["precio"] = price
                break

    if "precio" not in data:
        for m in re.finditer(r"([\d.,]+)\s*€", page_text):
            price = _parse_price(m.group(1))
            if price and price > 10_000:
                data["precio"] = price
                break

    # Title — og:title, then first <h1>
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        data["titulo"] = og_title["content"].strip()
    else:
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

    # Surface m² — first match < 2000
    m = re.search(r"(\d[\d.,]*)\s*m[²2]", page_text, re.IGNORECASE)
    if m:
        val = _parse_float(m.group(1))
        if val and val < 2000:
            data["superficie_m2"] = val

    # Rooms
    m = re.search(r"(\d+)\s*(?:hab|dormitor|dorm)", page_text, re.IGNORECASE)
    if m:
        data["habitaciones"] = int(m.group(1))

    # Bathrooms
    m = re.search(r"(\d+)\s*ba[ñn]", page_text, re.IGNORECASE)
    if m:
        data["banos"] = int(m.group(1))

    # Municipio — meta locality tags
    for meta_name in ("og:locality", "locality"):
        tag = (
            soup.find("meta", attrs={"property": meta_name})
            or soup.find("meta", attrs={"name": meta_name})
        )
        if tag and tag.get("content"):
            data["municipio"] = tag["content"].strip()
            break

    return data


def _parse_price(text: str) -> Optional[float]:
    """Parse European price string: '195.000' or '195.000,50' → float."""
    text = str(text).strip().replace(" ", "")
    if "." in text and "," in text:
        # Both: dot=thousands, comma=decimal → "195.000,50" → 195000.50
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and len(text.split(",")[-1]) == 3:
        # "195,000" → thousands separator (no decimal)
        text = text.replace(",", "")
    elif "." in text and len(text.split(".")[-1]) == 3:
        # "195.000" → thousands separator
        text = text.replace(".", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_float(text: str) -> Optional[float]:
    """Parse European decimal: '69,84' or '69.84' → 69.84"""
    text = str(text).strip()
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 4: Run tests — must pass**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -m pytest tests/test_url_extractor.py -v 2>&1 | tail -20
```

Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
git add app/scraper/url_extractor.py tests/test_url_extractor.py
git commit -m "feat: add url_extractor.py with generic property HTML parser"
```

---

## Task 2: Create `app/scraper/manual_scraper.py`

**Files:**
- Create: `app/scraper/manual_scraper.py`

- [ ] **Step 1: Create `app/scraper/manual_scraper.py`**

```python
"""Monitoring scraper for manually-added properties."""

import logging
from typing import Any, Dict

from .config import ScraperConfig
from .url_extractor import extract_from_url

logger = logging.getLogger(__name__)


class ManualScraper:
    """
    Used by sold_checker for properties with detail_scraper_type="manual_auto".
    Detects 404 (gone), sold keywords, and price changes.
    """

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        result = await extract_from_url(url)

        if "error" in result:
            err = result["error"]
            if "404" in err or "Not Found" in err:
                logger.info(f"HTTP 404 — marcando como no disponible: {url}")
                return {"url_original": url, "activa": False, "estado": "No disponible"}
            logger.warning(f"No se pudo verificar {url}: {err}")
            return {"url_original": url, "activa": True}

        if not result.get("activa", True):
            return {
                "url_original": url,
                "activa": False,
                "estado": result.get("estado", "Vendida"),
            }

        data: Dict[str, Any] = {"url_original": url, "activa": True}
        if "precio" in result:
            data["precio"] = result["precio"]
        return data
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -c "
import ast
ast.parse(open('app/scraper/manual_scraper.py').read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Verify import works**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -c "
import sys; sys.path.insert(0, 'app')
from scraper.manual_scraper import ManualScraper
print('Import OK')
"
```

Expected: `Import OK`

- [ ] **Step 4: Commit**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
git add app/scraper/manual_scraper.py
git commit -m "feat: add ManualScraper for monitoring manually-added properties"
```

---

## Task 3: Wire ManualScraper into `sold_checker.py` and `paginated_scraper.py`

**Files:**
- Modify: `app/scraper/sold_checker.py`
- Modify: `app/scraper/paginated_scraper.py`

- [ ] **Step 1: Read both files before editing**

```bash
head -30 /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal/app/scraper/sold_checker.py
head -25 /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal/app/scraper/paginated_scraper.py
```

- [ ] **Step 2: Edit `app/scraper/sold_checker.py`**

**Change A** — add import after `from .puertopiso_scraper import PuertoPisoScraper` (line 15):
```python
from .manual_scraper import ManualScraper
```

**Change B** — add elif in `_get_scraper()` before the final `return`:
```python
    elif detail_type == "manual_auto":
        return ManualScraper(config)
```

**Change C** — in `check_sold_properties()`, add price change detection for manual properties in the `else` branch. The current else branch (lines 83-85) reads:
```python
            else:
                logger.debug(f"[{i}/{stats['total']}] ✅ Activa: {prop.titulo[:60]}")
                stats["activas"] += 1
```

Replace it with:
```python
            else:
                stats["activas"] += 1
                # Price change detection for manual properties (no regular scrape cycle)
                if config.detail_scraper_type == "manual_auto":
                    nuevo_precio = details.get("precio")
                    if nuevo_precio and prop.precio and abs(nuevo_precio - prop.precio) > 100:
                        precio_anterior = prop.precio
                        prop.precio_anterior = precio_anterior
                        prop.precio = nuevo_precio
                        prop.updated_at = datetime.utcnow()
                        session.add(prop)
                        from db.models import PrecioHistorico
                        session.add(PrecioHistorico(propiedad_id=prop.id, precio=nuevo_precio))
                        session.commit()
                        if nuevo_precio < precio_anterior:
                            bajada = round(100 * (precio_anterior - nuevo_precio) / precio_anterior, 1)
                            logger.info(f"[{i}/{stats['total']}] 📉 Manual bajada {bajada}%: {prop.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")
                            stats.setdefault("bajadas_precio", []).append({
                                "titulo": prop.titulo,
                                "url": prop.url_original,
                                "precio_anterior": precio_anterior,
                                "precio_nuevo": nuevo_precio,
                                "bajada_pct": bajada,
                            })
                        else:
                            logger.info(f"[{i}/{stats['total']}] 📈 Manual subida: {prop.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")
                    else:
                        logger.debug(f"[{i}/{stats['total']}] ✅ Activa: {prop.titulo[:60]}")
                else:
                    logger.debug(f"[{i}/{stats['total']}] ✅ Activa: {prop.titulo[:60]}")
```

- [ ] **Step 3: Edit `app/scraper/paginated_scraper.py`**

**Change A** — add import after `from .jimenezruiz_scraper import JimenezRuizScraper`:
```python
from .manual_scraper import ManualScraper
```

**Change B** — add elif branch where detail scraper is chosen (after `elif detail_type == "puertopiso":` block):
```python
        elif detail_type == "manual_auto":
            self.detail_scraper = ManualScraper(fuente_config)
```

- [ ] **Step 4: Verify syntax**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -c "
import ast
for f in ['app/scraper/sold_checker.py', 'app/scraper/paginated_scraper.py']:
    ast.parse(open(f).read())
    print('OK', f)
"
```

Expected: `OK` for both files.

- [ ] **Step 5: Commit**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
git add app/scraper/sold_checker.py app/scraper/paginated_scraper.py
git commit -m "feat: wire ManualScraper into sold_checker and paginated_scraper"
```

---

## Task 4: Add dialog + button + badge to `app/pages/2_propiedades.py`

**Files:**
- Modify: `app/pages/2_propiedades.py`

- [ ] **Step 1: Read the top of the file and the sidebar section**

```bash
head -25 /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal/app/pages/2_propiedades.py
grep -n "with st.sidebar\|st.title.*Filtros\|st.divider" /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal/app/pages/2_propiedades.py | head -10
grep -n "def render_property_card\|titulo_display\|st.markdown.*titulo" /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal/app/pages/2_propiedades.py | head -10
```

- [ ] **Step 2: Add imports at the top of `2_propiedades.py`**

The current imports section ends around line 20 with `from utils.calculadora import ...`. Add after it:

```python
import asyncio
import hashlib
from urllib.parse import urlparse
from db.models import Fuente
from scraper.url_extractor import extract_from_url
```

- [ ] **Step 3: Add `_get_or_create_fuente_manual` helper before the `@st.dialog` functions**

Insert this function before the line `@st.dialog("🧮 Calculadora", ...)` (around line 192):

```python
def _get_or_create_fuente_manual(session) -> int:
    """Return the id of the 'Manual' fuente, creating it if it doesn't exist."""
    fuente = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
    if not fuente:
        fuente = Fuente(
            nombre="Manual",
            url="manual://manual",
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas='{"detail_scraper_type": "manual_auto"}',
        )
        session.add(fuente)
        session.commit()
        session.refresh(fuente)
    return fuente.id
```

- [ ] **Step 4: Add `add_url_dialog` function (after `_get_or_create_fuente_manual`)**

```python
@st.dialog("➕ Añadir propiedad por URL", width="large")
def add_url_dialog(session):
    """Dialog to add a property by pasting a URL and optionally auto-extracting data."""
    st.caption("Pega la URL de la página de detalle de la propiedad.")

    url = st.text_input("URL de la propiedad", placeholder="https://mbfinca.com/inmueble/...")

    if "manual_extracted" not in st.session_state:
        st.session_state.manual_extracted = {}

    if st.button("🔍 Extraer datos", disabled=not url):
        with st.spinner("Extrayendo datos..."):
            result = asyncio.run(extract_from_url(url))
        if "error" in result:
            st.error(f"No se pudo extraer: {result['error']}")
            st.session_state.manual_extracted = {}
        elif not result.get("activa", True):
            st.warning("Esta propiedad parece estar vendida o reservada.")
            st.session_state.manual_extracted = {}
        else:
            st.session_state.manual_extracted = result
            st.success("Datos extraídos. Revisa y completa el formulario.")

    ext = st.session_state.manual_extracted

    st.divider()
    titulo = st.text_input("Título", value=ext.get("titulo", ""))
    precio = st.number_input(
        "Precio (€) *",
        min_value=0.0,
        value=float(ext.get("precio", 0.0)),
        step=1000.0,
        format="%.0f",
    )
    if precio == 0:
        st.warning("El precio es obligatorio para guardar.")

    col1, col2, col3 = st.columns(3)
    with col1:
        superficie = st.number_input("Superficie m²", min_value=0.0, value=float(ext.get("superficie_m2", 0.0)), step=1.0, format="%.0f")
    with col2:
        habitaciones = st.number_input("Habitaciones", min_value=0, value=int(ext.get("habitaciones", 0)), step=1)
    with col3:
        banos = st.number_input("Baños", min_value=0, value=int(ext.get("banos", 0)), step=1)

    municipio = st.text_input("Municipio", value=ext.get("municipio", "El Puerto de Santa María"))
    tipo = st.selectbox("Tipo de propiedad", ["piso", "casa", "chalet", "ático", "dúplex", "local", "otro"])
    notas_prop = st.text_area("Notas (opcional)", height=80)

    col_save, col_cancel = st.columns(2)
    with col_cancel:
        if st.button("Cancelar", use_container_width=True):
            st.session_state.manual_extracted = {}
            st.rerun()
    with col_save:
        if st.button("💾 Guardar", use_container_width=True, disabled=(not url or precio == 0), type="primary"):
            fuente_id = _get_or_create_fuente_manual(session)
            hash_unico = hashlib.sha256(url.encode("utf-8")).hexdigest()

            existing = session.exec(
                select(Propiedad).where(Propiedad.hash_unico == hash_unico)
            ).first()
            if existing:
                st.error("Esta URL ya está registrada en la base de datos.")
                return

            propiedad = Propiedad(
                hash_unico=hash_unico,
                url_original=url,
                fuente_id=fuente_id,
                origen_web=urlparse(url).netloc,
                titulo=titulo or url,
                precio=precio,
                superficie_m2=superficie if superficie > 0 else None,
                habitaciones=habitaciones if habitaciones > 0 else None,
                banos=banos if banos > 0 else None,
                municipio=municipio or None,
                tipo_propiedad=tipo,
                descripcion=notas_prop or None,
                activa=True,
                fecha_scraping=datetime.utcnow(),
            )
            session.add(propiedad)
            session.commit()
            session.refresh(propiedad)
            session.add(PrecioHistorico(propiedad_id=propiedad.id, precio=precio))
            session.commit()
            st.session_state.manual_extracted = {}
            st.success(f"✅ Propiedad guardada: {propiedad.titulo[:60]}")
            st.rerun()
```

- [ ] **Step 5: Add "➕ Añadir URL" button in the sidebar**

In the sidebar section (around line 458), find `with st.sidebar:` followed by `st.title("🔍 Filtros")`. Add the button **before** `st.title("🔍 Filtros")`:

```python
        with st.sidebar:
            if st.button("➕ Añadir URL", use_container_width=True, type="primary"):
                add_url_dialog(session)

            st.title("🔍 Filtros")
```

- [ ] **Step 6: Add "📌 Manual" badge to `render_property_card`**

The function `render_property_card(prop)` currently builds `titulo_display` like this (around line 193):
```python
        titulo_display = prop.titulo[:70] if prop.titulo else 'Sin título'
        if not prop.activa:
            titulo_display = f"~~{titulo_display}~~ 🚫 {prop.estado or 'Vendida'}"
        st.markdown(f"### {titulo_display}")
```

Replace with:
```python
        titulo_display = prop.titulo[:70] if prop.titulo else 'Sin título'
        if not prop.activa:
            titulo_display = f"~~{titulo_display}~~ 🚫 {prop.estado or 'Vendida'}"
        manual_badge = " 📌" if st.session_state.get("fuente_manual_id") == prop.fuente_id else ""
        st.markdown(f"### {titulo_display}{manual_badge}")
```

Then, where the `session` is open (around line 342 where `st.title("🏘️ Propiedades")` is shown), add this line to populate the session_state value:

```python
        fuente_manual = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
        st.session_state["fuente_manual_id"] = fuente_manual.id if fuente_manual else -1
```

- [ ] **Step 7: Verify syntax**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -c "
import ast
ast.parse(open('app/pages/2_propiedades.py').read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 8: Run all tests**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
conda run -n mi_inmobiliaria_env python -m pytest tests/test_url_extractor.py tests/test_calculadora.py -v 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 9: Commit and push**

```bash
cd /Users/Sergio/Documents/Docker/mi-inmobiliaria-personal
git add app/pages/2_propiedades.py
git commit -m "feat: add manual URL property dialog and badge in 2_propiedades.py"
git push origin master
```

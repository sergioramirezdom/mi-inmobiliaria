# Alonsaga Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add alonsaga.com as a new scraping source, covering the Pinar Alto / Crevillet / Menesteo zone of El Puerto de Santa María.

**Architecture:** New `AlonsagaScraper` class (same pattern as `GuadaleteScraper`) handles detail pages via httpx + BeautifulSoup with regex field extraction. A single-line change in `generic.py` adds `data-path` attribute fallback for URL extraction (alonsaga cards use `data-path` instead of `<a href>`). Three registry wires connect the new class to `sold_checker.py`, `paginated_scraper.py`, and `1_fuentes.py`.

**Tech Stack:** Python 3.11, httpx, BeautifulSoup4 (lxml), pytest, Streamlit, SQLModel/PostgreSQL.

## Global Constraints

- Follow `GuadaleteScraper` as the reference implementation — same class structure, same header dict, same `_parse_price_eu` helper pattern.
- `municipio` is always hardcoded to `"El Puerto de Santa María"` — never extracted from page.
- Photos: collect only `<img src>` URLs that contain `fotoshs.imghs.net`.
- Tipo: extracted from the URL path segment after `/en_venta/` (e.g. `/detalle/en_venta/piso/` → `"piso"`).
- All tests run with: `conda run -n mi_inmobiliaria_env python -m pytest <path> -v`

---

## Files

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/scraper/alonsaga_scraper.py` | Detail page scraper class |
| Create | `tests/test_alonsaga_scraper.py` | Unit tests for scraper logic |
| Modify | `app/scraper/generic.py` lines 280-288 | Add `data-path` URL fallback |
| Modify | `app/pages/1_fuentes.py` lines 19-27, 31-95 | Register "Alonsaga" in options + template |
| Modify | `app/scraper/sold_checker.py` lines 14-32 | Wire elif alonsaga |
| Modify | `app/scraper/paginated_scraper.py` lines 17-86 | Wire elif alonsaga |

---

### Task 1: `AlonsagaScraper` — detail scraper + tests

**Files:**
- Create: `app/scraper/alonsaga_scraper.py`
- Create: `tests/test_alonsaga_scraper.py`

**Interfaces:**
- Produces: `AlonsagaScraper(config: ScraperConfig = None)` with `async def scrape_property_details(url: str) -> Dict[str, Any]`
- Consumed by: Task 3 (sold_checker), Task 4 (paginated_scraper)

- [ ] **Step 1: Write failing tests**

Create `tests/test_alonsaga_scraper.py`:

```python
"""Unit tests for AlonsagaScraper — pure logic, no HTTP calls."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.alonsaga_scraper import (
    _parse_price_eu,
    _extract_tipo_from_url,
    _extract_fotos,
)
from bs4 import BeautifulSoup


def test_parse_price_eu_dot_thousands():
    assert _parse_price_eu("180.000") == 180000.0


def test_parse_price_eu_with_comma_decimal():
    assert _parse_price_eu("250.000,50") == 250000.5


def test_parse_price_eu_plain():
    assert _parse_price_eu("95000") == 95000.0


def test_parse_price_eu_invalid():
    assert _parse_price_eu("no price") is None


def test_extract_tipo_piso():
    url = "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto/123/"
    assert _extract_tipo_from_url(url) == "piso"


def test_extract_tipo_chalet():
    url = "https://www.alonsaga.com/detalle/en_venta/chalet/cadiz/el_puerto/zona/456/"
    assert _extract_tipo_from_url(url) == "chalet"


def test_extract_tipo_unknown():
    url = "https://www.alonsaga.com/detalle/en_venta/cadiz/el_puerto/"
    assert _extract_tipo_from_url(url) is None


def test_extract_fotos_filters_by_domain():
    html = """
    <html><body>
      <img src="https://fotoshs.imghs.net/path/photo1.jpg">
      <img src="https://other.com/photo.jpg">
      <img src="https://fotoshs.imghs.net/path/photo2.jpg">
      <img src="/static/logo.png">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup)
    assert fotos == [
        "https://fotoshs.imghs.net/path/photo1.jpg",
        "https://fotoshs.imghs.net/path/photo2.jpg",
    ]


def test_extract_fotos_empty_when_none():
    soup = BeautifulSoup("<html><body><p>no images</p></body></html>", "lxml")
    assert _extract_fotos(soup) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_scraper.py -v 2>&1 | tail -20
```

Expected: `ImportError` or `ModuleNotFoundError` — file doesn't exist yet.

- [ ] **Step 3: Create `app/scraper/alonsaga_scraper.py`**

```python
"""Detail scraper for alonsaga.com."""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
from .config import ScraperConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alonsaga.com"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}


class AlonsagaScraper:
    """Detail scraper for Alonsaga Inmobiliaria."""

    def __init__(self, config: ScraperConfig = None):
        self.config = config or ScraperConfig()

    async def scrape_property_details(self, url: str) -> Dict[str, Any]:
        if not url.startswith("http"):
            url = BASE_URL + url

        data: Dict[str, Any] = {"url_original": url, "activa": True}

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=BROWSER_HEADERS, timeout=self.config.timeout)
                if response.status_code == 404:
                    logger.info(f"HTTP 404 — marcando como no disponible: {url}")
                    data["activa"] = False
                    data["estado"] = "No disponible"
                    return data
                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    return data
                html = response.text
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return data

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True)
        lower_text = page_text.lower()

        # Sold detection
        for keyword in ("vendido", "vendida", "reservado", "reservada"):
            if keyword in lower_text:
                data["activa"] = False
                data["estado"] = keyword.capitalize()
                return data

        # Title
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

        # Price: format "180.000 €" or "180.000€"
        price_match = re.search(r"([\d.]+(?:,\d+)?)\s*€", page_text)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Numeric fields via regex
        patterns = [
            (r"(\d+)\s*[Hh]abitaciones?", "habitaciones"),
            (r"(\d+)\s*[Bb]años?", "banos"),
            (r"([\d.,]+)\s*m²", "superficie_m2"),
        ]
        for pattern, field in patterns:
            if field in data:
                continue
            m = re.search(pattern, page_text)
            if m:
                val = m.group(1).replace(".", "").replace(",", ".")
                try:
                    data[field] = int(float(val)) if field in ("habitaciones", "banos") else float(val)
                except (ValueError, TypeError):
                    pass

        # Fixed municipio
        data["municipio"] = "El Puerto de Santa María"

        # Property type from URL
        tipo = _extract_tipo_from_url(url)
        if tipo:
            data["tipo_propiedad"] = tipo

        # Photos
        fotos = _extract_fotos(soup)
        if fotos:
            data["fotos"] = fotos

        # Description: first block element with >150 chars and no nested block children
        for tag in soup.find_all(["div", "section", "p"]):
            text = tag.get_text(strip=True)
            if len(text) > 150 and not tag.find_all(["div", "section"]):
                data.setdefault("descripcion", text[:2000])
                break

        return data


def _parse_price_eu(text: str) -> Optional[float]:
    """Parse European price string: '180.000' → 180000.0, '250.000,50' → 250000.5"""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _extract_tipo_from_url(url: str) -> Optional[str]:
    """Extract property type from URL path: /detalle/en_venta/{tipo}/... → tipo"""
    m = re.search(r"/en_venta/([^/]+)/", url)
    if m:
        tipo = m.group(1)
        tipo_map = {
            "piso": "piso", "chalet": "chalet", "casa": "casa",
            "local": "local", "garaje": "garaje", "oficina": "oficina",
            "terreno": "terreno", "finca": "finca", "duplex": "duplex",
            "atico": "atico", "apartamento": "apartamento",
        }
        return tipo_map.get(tipo, tipo) if tipo not in ("cadiz", "el_puerto_de_santa_maria") else None
    return None


def _extract_fotos(soup: BeautifulSoup) -> List[str]:
    """Return all img src URLs that belong to the alonsaga photo CDN."""
    return [
        img["src"]
        for img in soup.find_all("img", src=True)
        if "fotoshs.imghs.net" in img["src"]
    ]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_scraper.py -v 2>&1 | tail -15
```

Expected: `9 passed` (all tests green).

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "feat: add AlonsagaScraper detail scraper with tests"
```

---

### Task 2: `generic.py` — add `data-path` URL fallback

**Files:**
- Modify: `app/scraper/generic.py` lines 280-288

**Interfaces:**
- Consumes: nothing new
- Produces: `GenericScraper._extract_field("link")` now falls back to `data-path` attribute when `href` and `onclick` yield nothing

- [ ] **Step 1: Write failing test**

Add to `tests/test_alonsaga_scraper.py` (append at the bottom):

```python
import asyncio
from unittest.mock import patch, MagicMock
from scraper.generic import GenericScraper
from scraper.config import ScraperConfig, SelectorsConfig


def test_generic_scraper_extracts_data_path_url():
    """GenericScraper._extract_field should extract URL from data-path attribute."""
    config = ScraperConfig(selectors=SelectorsConfig(property_container="div.card"))
    scraper = GenericScraper(config)
    scraper.base_url = "https://www.alonsaga.com"

    html = '<div class="card" data-path="/detalle/en_venta/piso/cadiz/123/">Piso</div>'
    soup = BeautifulSoup(html, "lxml")
    element = soup.select_one("div.card")

    url = scraper._extract_field(element, "link")
    assert url == "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/123/"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_scraper.py::test_generic_scraper_extracts_data_path_url -v 2>&1 | tail -10
```

Expected: `FAILED` — `assert None == "https://..."`

- [ ] **Step 3: Add `data-path` fallback in `generic.py`**

In `app/scraper/generic.py`, find the block ending around line 286 (after the `onclick` URL patterns block that ends with `return self._resolve_url(quoted)`). Insert the new fallback **before** the `except Exception` line:

```python
                # Try data-path attribute (used by JS-navigated sites like alonsaga.com)
                data_path_match = re.search(r'data-path=["\']([^"\']+)["\']', element_html)
                if data_path_match:
                    return self._resolve_url(data_path_match.group(1))
```

The relevant section in `generic.py` currently looks like this (lines ~281-289):

```python
                    # If no pattern matched, try to extract any URL-like string
                    # Look for paths or full URLs
                    all_quoted = re.findall(r"['\"]([^'\"]+)['\"]", onclick_content)
                    for quoted in all_quoted:
                        if quoted.startswith(('http', '/', '/propiedad', 'propiedad', 'ficha')):
                            return self._resolve_url(quoted)

            except Exception as e:
                self.logger.debug(f"Link regex failed: {e}")
```

Replace with:

```python
                    # If no pattern matched, try to extract any URL-like string
                    # Look for paths or full URLs
                    all_quoted = re.findall(r"['\"]([^'\"]+)['\"]", onclick_content)
                    for quoted in all_quoted:
                        if quoted.startswith(('http', '/', '/propiedad', 'propiedad', 'ficha')):
                            return self._resolve_url(quoted)

                # Try data-path attribute (used by JS-navigated sites like alonsaga.com)
                data_path_match = re.search(r'data-path=["\']([^"\']+)["\']', element_html)
                if data_path_match:
                    return self._resolve_url(data_path_match.group(1))

            except Exception as e:
                self.logger.debug(f"Link regex failed: {e}")
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_scraper.py -v 2>&1 | tail -15
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/scraper/generic.py tests/test_alonsaga_scraper.py
git commit -m "fix: add data-path URL fallback in GenericScraper for JS-navigated sites"
```

---

### Task 3: Wire `sold_checker.py` + `paginated_scraper.py`

**Files:**
- Modify: `app/scraper/sold_checker.py` lines 14-32
- Modify: `app/scraper/paginated_scraper.py` lines 17-86

**Interfaces:**
- Consumes: `AlonsagaScraper` from Task 1
- Produces: `detail_type == "alonsaga"` dispatches to `AlonsagaScraper` in both files

- [ ] **Step 1: Write failing tests**

Create `tests/test_alonsaga_wiring.py`:

```python
"""Tests that 'alonsaga' detail_scraper_type routes to AlonsagaScraper."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.sold_checker import _get_scraper
from scraper.alonsaga_scraper import AlonsagaScraper
from scraper.config import ScraperConfig


def test_sold_checker_routes_alonsaga():
    config = ScraperConfig(detail_scraper_type="alonsaga")
    scraper = _get_scraper("alonsaga", config)
    assert isinstance(scraper, AlonsagaScraper)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_wiring.py -v 2>&1 | tail -10
```

Expected: `FAILED` — `_get_scraper("alonsaga", ...)` returns `PuertoInmobiliariaScraper`, not `AlonsagaScraper`.

- [ ] **Step 3: Add import + elif in `sold_checker.py`**

In `app/scraper/sold_checker.py`, find the top-level imports block. It currently ends with:

```python
from .manual_scraper import ManualScraper
```

Add the Alonsaga import after it:

```python
from .manual_scraper import ManualScraper
from .alonsaga_scraper import AlonsagaScraper
```

Then find the elif chain. It currently ends with:

```python
    elif detail_type == "manual_auto":
        return ManualScraper(config)
    return PuertoInmobiliariaScraper(config)
```

Add the new elif before the final `return`:

```python
    elif detail_type == "manual_auto":
        return ManualScraper(config)
    elif detail_type == "alonsaga":
        return AlonsagaScraper(config)
    return PuertoInmobiliariaScraper(config)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/test_alonsaga_wiring.py -v 2>&1 | tail -10
```

Expected: `1 passed`.

- [ ] **Step 5: Add import + elif in `paginated_scraper.py`**

In `app/scraper/paginated_scraper.py`, find the top-level imports block. It currently ends with:

```python
from .manual_scraper import ManualScraper
```

Add the Alonsaga import after it:

```python
from .manual_scraper import ManualScraper
from .alonsaga_scraper import AlonsagaScraper
```

Then find the elif chain. It currently ends with:

```python
        elif detail_type == "manual_auto":
            self.detail_scraper = ManualScraper(fuente_config)
        else:
```

Add the new elif before the `else`:

```python
        elif detail_type == "manual_auto":
            self.detail_scraper = ManualScraper(fuente_config)
        elif detail_type == "alonsaga":
            self.detail_scraper = AlonsagaScraper(fuente_config)
        else:
```

- [ ] **Step 6: Run full test suite**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all `test_alonsaga_*` tests pass. Pre-existing failures in `test_scraper_config.py` are unrelated.

- [ ] **Step 7: Commit**

```bash
git add app/scraper/sold_checker.py app/scraper/paginated_scraper.py tests/test_alonsaga_wiring.py
git commit -m "feat: wire AlonsagaScraper into sold_checker and paginated_scraper"
```

---

### Task 4: Register in `1_fuentes.py`

**Files:**
- Modify: `app/pages/1_fuentes.py` lines 19-27 (`DETAIL_SCRAPER_OPTIONS`) and lines 31-95 (`SCRAPER_CONFIG_TEMPLATES`)

**Interfaces:**
- Consumes: nothing — UI registration only
- Produces: "Alonsaga" visible in the fuente selector dropdown + config template auto-populated

- [ ] **Step 1: Add to `DETAIL_SCRAPER_OPTIONS`**

In `app/pages/1_fuentes.py`, find:

```python
DETAIL_SCRAPER_OPTIONS = [
    ("Automático (genérico)", None),
    ("Puerto Inmobiliaria", "puerto"),
    ("Mobilia", "mobilia"),
    ("Punto Hogar", "puntohogar"),
    ("Guadalete", "guadalete"),
    ("Jiménez Ruiz", "jimenezruiz"),
    ("Puerto Piso", "puertopiso"),
]
```

Replace with:

```python
DETAIL_SCRAPER_OPTIONS = [
    ("Automático (genérico)", None),
    ("Puerto Inmobiliaria", "puerto"),
    ("Mobilia", "mobilia"),
    ("Punto Hogar", "puntohogar"),
    ("Guadalete", "guadalete"),
    ("Jiménez Ruiz", "jimenezruiz"),
    ("Puerto Piso", "puertopiso"),
    ("Alonsaga", "alonsaga"),
]
```

- [ ] **Step 2: Add config template to `SCRAPER_CONFIG_TEMPLATES`**

In `app/pages/1_fuentes.py`, find the end of `SCRAPER_CONFIG_TEMPLATES` — the last entry before `}` closing the dict. It ends with the `"puertopiso"` entry. Add a new entry after it:

```python
    "alonsaga": {
        "detail_scraper_type": "alonsaga",
        "selectors": {
            "property_container": "div.cardAnuncio",
            "title": "span.titulo",
            "price": "div.precio",
        },
        "pagination_param": "Pagina",
        "pagination_start": 0,
        "pagination_skip_first": True,
        "use_results_per_page": False,
    },
```

- [ ] **Step 3: Verify the UI renders correctly**

```bash
conda run -n mi_inmobiliaria_env python -c "
import sys; sys.path.insert(0, 'app')
from pages import 1_fuentes  # can't import directly due to leading digit
"
```

Since direct import fails due to the `1_` prefix, verify syntactically instead:

```bash
conda run -n mi_inmobiliaria_env python -m py_compile app/pages/1_fuentes.py && echo "OK"
```

Expected: `OK` (no syntax errors).

- [ ] **Step 4: Run full test suite**

```bash
conda run -n mi_inmobiliaria_env python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all previous + new tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/pages/1_fuentes.py
git commit -m "feat: register Alonsaga scraper in fuentes UI"
```

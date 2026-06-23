# Extracción de Zona — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer el campo `barrio` (zona) en todos los scrapers del sistema con una cobertura objetivo >85%.

**Architecture:** Nuevo módulo compartido `zona_utils.py` con `extract_from_url` y `extract_from_html`. Cada scraper que no extrae zona añade un bloque de 3 líneas antes de `return data`. `description_enricher.py` expone una función pública para auto-aplicar barrio en `paginated_scraper.py` como último recurso.

**Tech Stack:** Python 3.10+, httpx, BeautifulSoup4/lxml, pytest, re, urllib.parse.

## Global Constraints

- Entorno conda: todos los comandos se ejecutan con `conda run -n mi_inmobiliaria_env`
- Directorio raíz: `/Users/Sergio/Documents/Docker/mi-inmobiliaria-personal`
- Tests se ejecutan desde la raíz: `conda run -n mi_inmobiliaria_env pytest tests/ -v`
- Nunca sobreescribir `barrio` si ya tiene valor: `if not data.get("barrio")`
- `sys.path.insert(0, ...)` al inicio de test files (ver tests/test_alonsaga_scraper.py como referencia)

---

### Task 1: Crear `zona_utils.py` con tests

**Files:**
- Create: `app/scraper/zona_utils.py`
- Create: `tests/test_zona_utils.py`

**Interfaces:**
- Produces:
  - `extract_from_url(url: str) -> Optional[str]`
  - `extract_from_html(page_text: str, soup=None) -> Optional[str]`

- [ ] **Step 1: Escribir los tests que deben fallar**

```python
# tests/test_zona_utils.py
"""Unit tests for zona_utils — pure logic, no HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.zona_utils import extract_from_url, extract_from_html
from bs4 import BeautifulSoup


# --- extract_from_url ---

def test_extract_from_url_alonsaga():
    url = "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/64234783889.265000/"
    assert extract_from_url(url) == "Pinar Alto Crevillet Menesteo"

def test_extract_from_url_generic_zona_after_municipio():
    url = "https://example.com/venta/piso/el_puerto_de_santa_maria/centro/12345/"
    assert extract_from_url(url) == "Centro"

def test_extract_from_url_no_municipio_returns_none():
    url = "https://www.guadalete.com/inmuebles/pisos/ig1234"
    assert extract_from_url(url) is None

def test_extract_from_url_only_tipo_after_municipio_returns_none():
    url = "https://example.com/venta/el_puerto_de_santa_maria/piso/12345"
    assert extract_from_url(url) is None

def test_extract_from_url_empty_returns_none():
    assert extract_from_url("") is None


# --- extract_from_html ---

def test_extract_from_html_zona_label():
    text = "Superficie 80m² Zona: Pinar Alto, Precio 180.000€"
    assert extract_from_html(text) == "Pinar Alto"

def test_extract_from_html_barrio_label():
    text = "Barrio: El Centro, municipio El Puerto"
    assert extract_from_html(text) == "El Centro"

def test_extract_from_html_title_en_pattern():
    text = "Terreno rural en Pedanías Este - Jerez de la Frontera"
    assert extract_from_html(text) == "Pedanías Este"

def test_extract_from_html_no_zona_returns_none():
    text = "Piso de 3 habitaciones, 2 baños, 90m². Precio 200.000€."
    assert extract_from_html(text) is None

def test_extract_from_html_soup_h1_used():
    html = '<html><body><h1>Piso en Vistahermosa - El Puerto de Santa María</h1></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    result = extract_from_html("Sin zona en texto.", soup)
    assert result == "Vistahermosa"

def test_extract_from_html_result_max_60_chars():
    long_zona = "A" * 70
    text = f"Zona: {long_zona}, Precio 100€"
    result = extract_from_html(text)
    assert result is not None
    assert len(result) <= 60
```

- [ ] **Step 2: Verificar que fallan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_zona_utils.py -v
```
Expected: `ModuleNotFoundError: No module named 'scraper.zona_utils'`

- [ ] **Step 3: Implementar `zona_utils.py`**

```python
# app/scraper/zona_utils.py
"""Shared helpers for extracting zona/barrio from URL and HTML."""

import re
from typing import Optional
from urllib.parse import urlparse

MUNICIPIO_SLUGS = {
    "el_puerto_de_santa_maria", "el-puerto-de-santa-maria",
    "cadiz", "puerto_de_santa_maria", "puerto-de-santa-maria",
    "san_fernando", "jerez_de_la_frontera", "rota", "chipiona",
    "sanlucar_de_barrameda", "chiclana_de_la_frontera",
    "la_barca_de_la_florida",
}

SKIP_SEGMENTS = {
    "en_venta", "en_alquiler", "venta", "alquiler",
    "piso", "chalet", "casa", "local", "garaje", "terreno",
    "apartamento", "duplex", "atico", "finca", "oficina",
    "detalle", "buscador", "inmuebles", "cadiz", "www",
}

_ID_RE = re.compile(r"^\d[\d.]*$|^[a-f0-9]{10,}$", re.IGNORECASE)


def extract_from_url(url: str) -> Optional[str]:
    """Return zona from URL path segment after a known municipio slug, or None."""
    if not url:
        return None
    try:
        path = urlparse(url).path
    except Exception:
        return None

    segments = [s for s in path.split("/") if s]
    found_municipio = False

    for seg in segments:
        seg_lower = seg.lower()
        if seg_lower in MUNICIPIO_SLUGS:
            found_municipio = True
            continue
        if not found_municipio:
            continue
        if seg_lower in SKIP_SEGMENTS:
            continue
        if _ID_RE.match(seg):
            continue
        zona = seg.replace("_", " ").replace("-", " ").title()
        if len(zona) > 2:
            return zona

    return None


_HTML_PATTERNS = [
    re.compile(r"Zona[:\s]+([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s\-]{1,49})(?=[,\n<]|$)", re.IGNORECASE),
    re.compile(r"Barrio[:\s]+([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s\-]{1,49})(?=[,\n<]|$)", re.IGNORECASE),
    re.compile(r"\ben ([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,49}?) -\s*(?:El Puerto|Jerez|Cádiz|Cadiz|Rota|San Fernando)", re.IGNORECASE),
    re.compile(r"\bzona de ([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,39}?)[,\.]", re.IGNORECASE),
    re.compile(r"\bbarrio (?:de )?([\wáéíóúñÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ\s]{1,39}?)[,\.]", re.IGNORECASE),
]

_STOP_WORDS = {"la", "el", "los", "las", "un", "una", "del", "de", "en", "por", "su"}


def extract_from_html(page_text: str, soup=None) -> Optional[str]:
    """Return zona from page text (and optional soup for h1/title priority), or None."""
    sources = []

    if soup is not None:
        for tag_name in ("h1", "title"):
            el = soup.find(tag_name)
            if el:
                sources.append(el.get_text(" ", strip=True))

    sources.append(page_text)

    for text in sources:
        for pattern in _HTML_PATTERNS:
            m = pattern.search(text)
            if m:
                zona = m.group(1).strip()[:60].strip()
                if len(zona) > 2 and zona.lower() not in _STOP_WORDS:
                    return zona

    return None
```

- [ ] **Step 4: Verificar que pasan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_zona_utils.py -v
```
Expected: todos `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app/scraper/zona_utils.py tests/test_zona_utils.py
git commit -m "feat: add zona_utils shared helpers (extract_from_url, extract_from_html)"
```

---

### Task 2: Wiring zona_utils en 6 scrapers

**Files:**
- Modify: `app/scraper/puertopiso_scraper.py`
- Modify: `app/scraper/punto_hogar_scraper.py`
- Modify: `app/scraper/guadalete_scraper.py`
- Modify: `app/scraper/alonsaga_scraper.py`
- Modify: `app/scraper/jimenezruiz_scraper.py`
- Modify: `app/scraper/url_extractor.py`
- Create: `tests/test_zona_wiring.py`

**Interfaces:**
- Consumes: `extract_from_url`, `extract_from_html` de `zona_utils` (Task 1)

- [ ] **Step 1: Escribir tests de wiring**

```python
# tests/test_zona_wiring.py
"""Smoke tests: zona_utils wired into each scraper — pure logic, no HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from unittest.mock import AsyncMock, patch
import pytest


@pytest.mark.asyncio
async def test_alonsaga_extracts_barrio_from_url():
    from scraper.alonsaga_scraper import AlonsagaScraper

    fake_html = """<html><body>
        <h1>Piso en venta</h1>
        <p>180.000 €</p>
    </body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = AlonsagaScraper()
        result = await s.scrape_property_details(
            "https://www.alonsaga.com/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/123/"
        )
    assert result.get("barrio") == "Pinar Alto Crevillet Menesteo"


@pytest.mark.asyncio
async def test_puertopiso_extracts_barrio_from_html():
    from scraper.puertopiso_scraper import PuertoPisoScraper

    fake_html = """<html><head><title>Piso en Vistahermosa - El Puerto de Santa María</title></head>
        <body><h1>Fantástico piso</h1><p>200.000 €</p></body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = PuertoPisoScraper()
        result = await s.scrape_property_details("https://puertopiso.com/buscador/inmueble.php?id=123")
    assert result.get("barrio") == "Vistahermosa"


@pytest.mark.asyncio
async def test_punto_hogar_extracts_barrio_from_html():
    from scraper.punto_hogar_scraper import PuntoHogarScraper

    fake_html = """<html><body>
        <h1>Piso</h1>
        <p>Zona: El Buzo, precio 150.000€</p>
        <div class="precio-destacado">150.000€</div>
    </body></html>"""

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_html
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        s = PuntoHogarScraper()
        result = await s.scrape_property_details("https://www.puntohogarinmobiliaria.com/venta/piso/el-puerto/123")
    assert result.get("barrio") == "El Buzo"
```

- [ ] **Step 2: Instalar pytest-asyncio si no está disponible**

```bash
conda run -n mi_inmobiliaria_env pip show pytest-asyncio
```
Si no está instalado: `conda run -n mi_inmobiliaria_env pip install pytest-asyncio`

Añadir al inicio de `tests/test_zona_wiring.py` si pytest-asyncio lo requiere:
```python
import pytest
pytestmark = pytest.mark.asyncio
```

- [ ] **Step 3: Verificar que los tests fallan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_zona_wiring.py -v
```
Expected: los 3 tests FAIL (barrio = None)

- [ ] **Step 4: Añadir zona_utils a `alonsaga_scraper.py`**

En `app/scraper/alonsaga_scraper.py`, añadir import junto a los otros imports del módulo:
```python
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
```

Sustituir el bloque antes de `return data` al final de `scrape_property_details` (actualmente termina con el bloque de descripción):
```python
        # Zona fallback: URL first, then HTML
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data
```

- [ ] **Step 5: Añadir zona_utils a `puertopiso_scraper.py`**

En `app/scraper/puertopiso_scraper.py`, añadir import junto a los otros:
```python
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
```

Localizar el bloque de zona existente (línea ~137):
```python
        m = re.search(r"Zona[:\s]+([^\n<]+)", page_text, re.IGNORECASE)
        if m:
            zona = m.group(1).strip()
            if zona and len(zona) < 60:
                data["barrio"] = zona
```
Sustituirlo por:
```python
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)
```

- [ ] **Step 6: Añadir zona_utils a `punto_hogar_scraper.py`**

En `app/scraper/punto_hogar_scraper.py`, añadir import:
```python
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
```

Añadir justo antes de `return data` al final de `scrape_property_details`:
```python
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data
```

- [ ] **Step 7: Añadir zona_utils a `guadalete_scraper.py`**

En `app/scraper/guadalete_scraper.py`, añadir import:
```python
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
```

Añadir justo antes de `return data` al final de `scrape_property_details`:
```python
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data
```

- [ ] **Step 8: Añadir zona_utils a `jimenezruiz_scraper.py`**

En `app/scraper/jimenezruiz_scraper.py`, añadir import:
```python
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html
```

Añadir justo antes de `return data` al final de `scrape_property_details` (actualmente termina con el bloque de `fotos`):
```python
        if not data.get("barrio"):
            data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)

        return data
```

- [ ] **Step 9: Añadir zona_utils a `url_extractor.py`**

`url_extractor.py` tiene una función `extract_from_url` que entra en conflicto de nombre. Usar alias.

Añadir import al inicio del archivo (después de los imports existentes):
```python
from .zona_utils import (
    extract_from_url as _zona_from_url,
    extract_from_html as _zona_from_html,
)
```

En la función `_parse_html(html: str)`, añadir el parámetro `url: str = ""` y el bloque de zona al final, justo antes de `return data`:
```python
def _parse_html(html: str, url: str = "") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    # ... (resto del código sin cambios) ...

    # Zona fallback
    if not data.get("barrio"):
        data["barrio"] = (
            (_zona_from_url(url) if url else None)
            or _zona_from_html(page_text, soup)
        )

    return data
```

En la función `extract_from_url(url: str)` (la función HTTP), cambiar la llamada a `_parse_html`:
```python
    return _parse_html(html, url=url)
```

- [ ] **Step 10: Verificar que los tests pasan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_zona_wiring.py -v
```
Expected: los 3 tests `PASSED`

- [ ] **Step 11: Verificar que todos los tests anteriores siguen pasando**

```bash
conda run -n mi_inmobiliaria_env pytest tests/ -v
```
Expected: todos `PASSED`

- [ ] **Step 12: Commit**

```bash
git add app/scraper/alonsaga_scraper.py app/scraper/puertopiso_scraper.py \
        app/scraper/punto_hogar_scraper.py app/scraper/guadalete_scraper.py \
        app/scraper/jimenezruiz_scraper.py app/scraper/url_extractor.py \
        tests/test_zona_wiring.py
git commit -m "feat: wire zona_utils into 6 scrapers for barrio extraction"
```

---

### Task 3: Verificar puerto_inmobiliaria y mobilia — fix si es necesario

**Files:**
- Modify (solo si barrio falla): `app/scraper/puerto_inmobiliaria.py`
- Modify (solo si barrio falla): `app/scraper/mobilia_scraper.py`

**Interfaces:**
- Consumes: `extract_from_url`, `extract_from_html` de `zona_utils` (Task 1)

- [ ] **Step 1: Verificar puerto_inmobiliaria con página real**

```bash
conda run -n mi_inmobiliaria_env python3 -c "
import asyncio, sys
sys.path.insert(0, 'app')
from scraper.puerto_inmobiliaria import PuertoInmobiliariaScraper

async def test():
    s = PuertoInmobiliariaScraper()
    # Usar una URL real de una propiedad activa en puertoinmobiliaria.net
    # Obtener una URL ejecutando: grep -r 'puertoinmobiliaria' en la BD o usar una hardcoded conocida
    result = await s.scrape_property_details('https://www.puertoinmobiliaria.net/pisos_venta_el_puerto_de_santa_maria/')
    print('barrio:', result.get('barrio'))
    print('municipio:', result.get('municipio'))

asyncio.run(test())
"
```

Si `barrio` tiene valor → scraper funciona, no hay nada que hacer.

Si `barrio` es `None` → añadir import y fallback igual que en Task 2:

```python
# Al inicio de puerto_inmobiliaria.py:
from .zona_utils import extract_from_url as _zona_from_url, extract_from_html as _zona_from_html

# Justo antes de return data:
if not data.get("barrio"):
    data["barrio"] = _zona_from_url(url) or _zona_from_html(page_text, soup)
```

- [ ] **Step 2: Verificar mobilia_scraper con página real**

```bash
conda run -n mi_inmobiliaria_env python3 -c "
import asyncio, sys
sys.path.insert(0, 'app')
from scraper.mobilia_scraper import MobiliaScraper

async def test():
    s = MobiliaScraper()
    result = await s.scrape_property_details('https://www.alpica.es/detalle/piso-en-venta-el-puerto-de-santa-maria/')
    print('barrio:', result.get('barrio'))

asyncio.run(test())
"
```

Si `barrio` tiene valor → funciona, no hay nada que hacer.

Si `barrio` es `None` → añadir el mismo fallback de 3 líneas.

- [ ] **Step 3: Commit (solo si hubo cambios)**

```bash
git add app/scraper/puerto_inmobiliaria.py app/scraper/mobilia_scraper.py
git commit -m "fix: add zona_utils fallback to puerto_inmobiliaria and/or mobilia scrapers"
```
Si no hubo cambios, saltar este step.

---

### Task 4: Auto-apply barrio desde description_enricher en paginated_scraper

**Files:**
- Modify: `app/scraper/description_enricher.py`
- Modify: `app/scraper/paginated_scraper.py`
- Create: `tests/test_enricher_barrio.py`

**Interfaces:**
- Consumes: `prop.titulo`, `prop.descripcion` (strings) — no requiere objeto DB
- Produces: `extract_barrio_from_text(titulo: str, descripcion: str) -> Optional[str]`

- [ ] **Step 1: Escribir test para la nueva función**

```python
# tests/test_enricher_barrio.py
"""Tests for extract_barrio_from_text in description_enricher."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.description_enricher import extract_barrio_from_text


def test_extracts_urbanizacion():
    titulo = "Piso en urbanización Las Redes"
    descripcion = "Bonito piso en urbanización Las Redes, cerca de la playa."
    assert extract_barrio_from_text(titulo, descripcion) == "Las Redes"


def test_extracts_zona_keyword():
    titulo = "Piso en venta"
    descripcion = "Situado en zona Pinar Alto, con vistas al mar."
    result = extract_barrio_from_text(titulo, descripcion)
    assert result is not None
    assert "Pinar" in result


def test_returns_none_when_no_zona():
    titulo = "Piso en venta"
    descripcion = "3 habitaciones, 2 baños, 90m². Muy luminoso."
    assert extract_barrio_from_text(titulo, descripcion) is None


def test_returns_none_for_empty_input():
    assert extract_barrio_from_text("", "") is None
    assert extract_barrio_from_text(None, None) is None
```

- [ ] **Step 2: Verificar que fallan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_enricher_barrio.py -v
```
Expected: `ImportError: cannot import name 'extract_barrio_from_text'`

- [ ] **Step 3: Añadir `extract_barrio_from_text` a `description_enricher.py`**

Añadir esta función al final de `app/scraper/description_enricher.py`, después de `extract_suggestions`:

```python
def extract_barrio_from_text(titulo: str, descripcion: str) -> Optional[str]:
    """
    Extract barrio/zona from free text (titulo + descripcion).
    Returns cleaned string or None. Does not require a DB object.
    """
    titulo = titulo or ""
    descripcion = descripcion or ""
    raw = " ".join(filter(None, [titulo, descripcion]))
    if not raw:
        return None

    raw_lower = raw.lower()
    zone_patterns = [
        r"urbanizaci[oó]n\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,30}?)(?=\s*[,.\n]|$)",
        r"urb\.\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,30}?)(?=\s*[,.\n]|$)",
        r"zona\s+([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,25}?)(?=\s*[,.\n]|$)",
        r"barrio\s+(?:de\s+)?([\wáéíóúñÁÉÍÓÚÑ][^,.\n]{2,25}?)(?=\s*[,.\n]|$)",
    ]
    stopwords = {"la", "el", "los", "las", "un", "una", "del", "de"}
    for pattern in zone_patterns:
        m = re.search(pattern, raw_lower)
        if m:
            zona = m.group(1).strip().title()
            if len(zona) > 2 and zona.lower() not in stopwords:
                return zona

    return None
```

- [ ] **Step 4: Verificar que los tests pasan**

```bash
conda run -n mi_inmobiliaria_env pytest tests/test_enricher_barrio.py -v
```
Expected: todos `PASSED`

- [ ] **Step 5: Integrar en `paginated_scraper.py`**

En `app/scraper/paginated_scraper.py`, añadir el import al inicio del archivo (junto a otros imports):
```python
from .description_enricher import extract_barrio_from_text
```

Localizar el bloque que sigue a `raw_data.update(details)` (alrededor de la línea 270). Añadir justo después:
```python
                        try:
                            details = await self.detail_scraper.scrape_property_details(url_original)
                            raw_data.update(details)
                        except Exception as e:
                            self.logger.warning(f"Could not enrich property: {e}")

                        # Auto-apply barrio from description if still missing
                        if not raw_data.get("barrio"):
                            raw_data["barrio"] = extract_barrio_from_text(
                                raw_data.get("titulo", ""),
                                raw_data.get("descripcion", ""),
                            )
```

- [ ] **Step 6: Verificar suite completa**

```bash
conda run -n mi_inmobiliaria_env pytest tests/ -v
```
Expected: todos `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/scraper/description_enricher.py app/scraper/paginated_scraper.py \
        tests/test_enricher_barrio.py
git commit -m "feat: auto-apply barrio from description_enricher in paginated_scraper"
```

---

## Orden de ejecución

1. Task 1 (zona_utils) — prerequisito para todo lo demás
2. Task 2 (wiring 6 scrapers) — depende de Task 1
3. Task 3 (verificar puerto/mobilia) — depende de Task 1, independiente de Task 2
4. Task 4 (enricher auto-apply) — independiente de Tasks 2 y 3

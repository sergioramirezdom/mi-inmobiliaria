# Extracción de Imágenes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obtener imágenes de una propiedad a partir de la URL de su ficha, para los 5 portales que hoy no las extraen, con previsualización antes de guardar.

**Architecture:** Un módulo puro `app/scraper/foto_extractor.py` extrae URLs de imagen del HTML mediante filtros de calidad y agrupación por carpeta. Se consume desde un botón en la tarjeta de propiedad (con modal de confirmación) y como respaldo automático en los scrapers que no traen fotos propias.

**Tech Stack:** Python 3.12, BeautifulSoup4, httpx, Streamlit, pytest.

Spec: `docs/superpowers/specs/2026-07-20-extraccion-imagenes-design.md`

## Global Constraints

- **`extraer_fotos` es una función PURA**: recibe `html: str` y `url: str`, devuelve `list[str]`. No hace HTTP, no toca BD, no importa Streamlit. Es lo que permite testear el algoritmo con HTML fijo en vez de contra portales reales.
- **Nunca se pisan fotos existentes.** El respaldo en scrapers solo actúa `if not data.get("fotos")`. Los extractores específicos (`alonsaga`, `jimenezruiz`, `puertopiso`) son más precisos y mandan.
- **Se guardan URLs, no imágenes.** No se descarga ni rehospeda nada; `Propiedad.fotos` es `ARRAY(String)`.
- `obtener_fotos` **nunca lanza excepciones**: devuelve `{"error": "..."}`, igual que `url_extractor.extract_from_url`.
- Comentarios y textos de UI en español, como el resto del repo.
- Los tests hacen `sys.path.insert(0, ".../app")` y luego `from scraper.X import ...` — **no** `from app.scraper.X`. No hay `conftest.py`: cada fichero define sus fixtures.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `app/scraper/foto_extractor.py` (crear) | Recolección, filtros, agrupación y fetch. Núcleo puro + envoltorio async. |
| `app/ui/property_dialogs.py` (modificar) | Modal `buscar_fotos_dialog` con previsualización. |
| `app/ui/property_card.py` (modificar) | Botón 🔍 en el hueco `b[4]`. |
| `app/scraper/url_extractor.py` (modificar) | `_parse_html` emite `fotos` — cubre `manual_scraper` y "añadir por URL". |
| `app/scraper/mobilia_scraper.py` (modificar) | Respaldo antes de `return data` (línea 144). |
| `app/scraper/guadalete_scraper.py` (modificar) | Respaldo antes de `return data` (línea 131). |
| `app/scraper/punto_hogar_scraper.py` (modificar) | Respaldo antes de `return data` (línea 116). |
| `app/scraper/puerto_inmobiliaria.py` (modificar) | Respaldo antes de `return enriched_data` (línea 106). |
| `tests/test_foto_extractor.py` (crear) | Algoritmo con HTML fijo. |
| `tests/test_foto_extractor_wiring.py` (crear) | Respaldo activo en scrapers, sin pisar fotos propias. |

`manual_scraper.py` **no se toca**: no parsea HTML, delega en `url_extractor.extract_from_url`. Al añadir `fotos` en `_parse_html` queda cubierto automáticamente.

---

### Task 1: Filtros y recolección de candidatas

**Files:**
- Create: `app/scraper/foto_extractor.py`
- Create: `tests/test_foto_extractor.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `_sin_query(url: str) -> str`
  - `_carpeta(url: str) -> str`
  - `_es_imagen(url: str) -> bool`
  - `_descartable(url: str) -> bool`

Estas cuatro funciones son las reglas de calidad. Se hacen primero y aisladas porque cada una es una fuente potencial de falsos negativos (descartar una foto buena) o de ruido (colar un logo).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_foto_extractor.py`:

```python
"""Tests del extractor genérico de fotos — lógica pura, sin HTTP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from scraper.foto_extractor import _carpeta, _descartable, _es_imagen, _sin_query


@pytest.mark.parametrize("entrada,esperado", [
    ("https://p.com/f/a.jpg?w=800", "https://p.com/f/a.jpg"),
    ("https://p.com/f/a.jpg", "https://p.com/f/a.jpg"),
    ("https://p.com/f/a.jpg?w=1200&h=600", "https://p.com/f/a.jpg"),
])
def test_sin_query(entrada, esperado):
    assert _sin_query(entrada) == esperado


def test_carpeta_agrupa_por_directorio():
    assert _carpeta("https://p.com/fotos/2024/a.jpg") == "p.com/fotos/2024"
    assert _carpeta("https://p.com/fotos/2024/b.jpg") == "p.com/fotos/2024"
    assert _carpeta("https://p.com/otro/c.jpg") != _carpeta("https://p.com/fotos/2024/a.jpg")


def test_carpeta_incluye_dominio():
    """Dos CDNs distintos con la misma ruta no deben agruparse juntos."""
    assert _carpeta("https://a.com/f/x.jpg") != _carpeta("https://b.com/f/x.jpg")


@pytest.mark.parametrize("url,esperado", [
    ("https://p.com/a.jpg", True),
    ("https://p.com/a.jpeg", True),
    ("https://p.com/a.png", True),
    ("https://p.com/a.webp", True),
    ("https://p.com/a.JPG", True),
    ("https://p.com/a.jpg?w=800", True),   # el query no debe estorbar
    ("https://p.com/a.svg", False),
    ("https://p.com/pagina.html", False),
    ("https://p.com/sinextension", False),
])
def test_es_imagen(url, esperado):
    assert _es_imagen(url) is esperado


@pytest.mark.parametrize("url", [
    "https://p.com/img/logo.png",
    "https://p.com/banner-home.jpg",
    "https://p.com/icons/mail.png",
    "https://p.com/f/thumb_a.jpg",
    "https://p.com/f/small_a.jpg",
    "https://p.com/avatar.jpg",
    "https://p.com/sprite.png",
    "https://p.com/placeholder.jpg",
    "https://p.com/blank.png",
    "https://p.com/a.svg",
    "https://p.com/a.gif",
    "https://p.com/a.ico",
])
def test_descartable_true(url):
    assert _descartable(url) is True


@pytest.mark.parametrize("url", [
    "https://p.com/fotos/casa-salon.jpg",
    "https://p.com/media/2024/01/piso.jpeg",
    "https://p.com/f/a.png",
])
def test_descartable_false(url):
    assert _descartable(url) is False
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_foto_extractor.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scraper.foto_extractor'`

- [ ] **Step 3: Implementar los helpers**

Crear `app/scraper/foto_extractor.py`:

```python
"""Extracción genérica de fotos a partir del HTML de una ficha.

Mismo reparto que url_extractor: una función pura con el algoritmo y un
envoltorio async fino para el fetch. La parte pura se testea con HTML fijo,
nunca contra portales reales (cambian y volverían los tests inestables).
"""

import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

# Formatos que nunca son la foto de un piso.
_EXT_MALAS = (".svg", ".gif", ".ico")
_EXT_BUENAS = (".jpg", ".jpeg", ".png", ".webp")

# Fragmentos de ruta propios de la plantilla del portal, no del anuncio.
_RUTA_MALA = (
    "logo", "banner", "icon", "avatar", "sprite",
    "placeholder", "thumb", "small", "blank",
)

# Por debajo de esto es iconografía. Solo se aplica cuando el <img> declara
# width/height: conocer el tamaño real exigiría descargar cada imagen.
_MIN_DIM = 300


def _sin_query(url: str) -> str:
    """Quita query y fragmento: '?w=800' y '?w=1200' son la misma foto."""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def _carpeta(url: str) -> str:
    """Dominio + directorio, sin el nombre de fichero.

    Es la clave de agrupación: las fotos de un anuncio viven juntas en el
    CDN, mientras que los adornos de la plantilla están dispersos.
    """
    p = urlparse(url)
    return f"{p.netloc}{p.path.rsplit('/', 1)[0]}"


def _es_imagen(url: str) -> bool:
    """True si la extensión (ignorando el query) es de imagen aprovechable."""
    return _sin_query(url).lower().endswith(_EXT_BUENAS)


def _descartable(url: str) -> bool:
    """True si la URL es iconografía o decoración del portal."""
    limpia = _sin_query(url).lower()
    if limpia.endswith(_EXT_MALAS):
        return True
    return any(malo in limpia for malo in _RUTA_MALA)
```

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_foto_extractor.py -v`
Expected: todos PASSED (28 casos)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/foto_extractor.py tests/test_foto_extractor.py
git commit -m "feat: filtros de calidad para extraccion de fotos"
```

---

### Task 2: Algoritmo de extracción y fetch

**Files:**
- Modify: `app/scraper/foto_extractor.py`
- Modify: `tests/test_foto_extractor.py`

**Interfaces:**
- Consumes: los helpers de Task 1
- Produces:
  - `extraer_fotos(html: str, url: str = "") -> list[str]` — PURA
  - `async obtener_fotos(url: str) -> dict` — `{"fotos": [...]}` o `{"error": "..."}`

Todos los casos de test de este task han sido verificados ejecutando el algoritmo antes de escribir el plan: los 12 pasan con la implementación del Step 3.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_foto_extractor.py`:

```python
from scraper.foto_extractor import extraer_fotos

BASE = "https://portal.com/piso/1"


def test_galeria_normal():
    html = '<img src="/f/a.jpg"><img src="/f/b.jpg"><img src="/f/c.jpg">'
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/f/a.jpg",
        "https://portal.com/f/b.jpg",
        "https://portal.com/f/c.jpg",
    ]


def test_descarta_svg_y_gif():
    html = '<img src="/f/a.jpg"><img src="/x.svg"><img src="/y.gif">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_descarta_logo_y_thumb():
    html = ('<img src="/f/a.jpg"><img src="/img/logo.png">'
            '<img src="/f/thumb_b.jpg">')
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_lee_data_src_de_carga_diferida():
    html = '<img data-src="/f/a.jpg"><img data-src="/f/b.jpg">'
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/f/a.jpg",
        "https://portal.com/f/b.jpg",
    ]


def test_coge_la_foto_grande_del_enlace():
    """Patrón de puertopiso: la miniatura va en <img>, la grande en <a href>."""
    html = '<a href="/f/big1.jpg"><img src="/f/small1.jpg"></a>'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/big1.jpg"]


def test_resuelve_urls_relativas():
    html = '<img src="fotos/a.jpg">'
    assert extraer_fotos(html, "https://portal.com/piso/1/") == [
        "https://portal.com/piso/1/fotos/a.jpg"
    ]


def test_deduplica_por_query_string():
    html = '<img src="/f/a.jpg?w=800"><img src="/f/a.jpg?w=1200">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/a.jpg"]


def test_gana_la_carpeta_con_mas_fotos():
    """La galería del anuncio contra adornos dispersos de la plantilla."""
    html = ('<img src="/g/1.jpg"><img src="/g/2.jpg"><img src="/g/3.jpg">'
            '<img src="/g/4.jpg"><img src="/otro/x.jpg"><img src="/mas/y.jpg">')
    assert extraer_fotos(html, BASE) == [
        "https://portal.com/g/1.jpg",
        "https://portal.com/g/2.jpg",
        "https://portal.com/g/3.jpg",
        "https://portal.com/g/4.jpg",
    ]


def test_fallback_a_og_image():
    html = ('<meta property="og:image" content="/f/principal.jpg">'
            '<img src="/logo.png">')
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/principal.jpg"]


def test_descarta_imagenes_con_dimension_declarada_pequena():
    html = '<img src="/f/a.jpg" width="50"><img src="/f/b.jpg" width="800">'
    assert extraer_fotos(html, BASE) == ["https://portal.com/f/b.jpg"]


def test_html_vacio():
    assert extraer_fotos("", BASE) == []


def test_html_sin_imagenes():
    assert extraer_fotos("<p>hola</p>", BASE) == []
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_foto_extractor.py -v -k "galeria or carpeta_con or og_image"`
Expected: FAIL con `ImportError: cannot import name 'extraer_fotos'`

- [ ] **Step 3: Implementar el algoritmo**

Añadir al final de `app/scraper/foto_extractor.py`:

```python
def _dimension_declarada_pequena(tag) -> bool:
    """True si el <img> declara width/height por debajo de _MIN_DIM."""
    for attr in ("width", "height"):
        valor = tag.get(attr)
        if not valor:
            continue
        m = re.match(r"^\s*(\d+)", str(valor))
        if m and int(m.group(1)) < _MIN_DIM:
            return True
    return False


def _recolectar_candidatas(soup, url: str) -> List[str]:
    """Todas las URLs de imagen del documento, ya absolutas.

    Mira src, data-src/data-original (carga diferida), srcset, y los <a href>
    que apunten a una imagen: algunos portales cuelgan la miniatura del <img>
    y la foto grande del enlace que la envuelve.
    """
    candidatas: List[str] = []

    for img in soup.find_all("img"):
        if _dimension_declarada_pequena(img):
            continue
        for attr in ("src", "data-src", "data-original"):
            valor = img.get(attr)
            if valor and not valor.startswith("data:"):
                candidatas.append(urljoin(url, valor.strip()))
        srcset = img.get("srcset")
        if srcset:
            for parte in srcset.split(","):
                cand = parte.strip().split(" ")[0]
                if cand and not cand.startswith("data:"):
                    candidatas.append(urljoin(url, cand))

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith("data:"):
            absoluta = urljoin(url, href)
            if _es_imagen(absoluta):
                candidatas.append(absoluta)

    return candidatas


def extraer_fotos(html: str, url: str = "") -> List[str]:
    """Devuelve las URLs de las fotos del anuncio. Función pura, sin HTTP.

    Recolecta, filtra por formato y ruta, deduplica ignorando el query, y se
    queda con el grupo de imágenes que comparte carpeta más numeroso. Si no
    queda nada, cae a og:image.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    candidatas = [
        u for u in _recolectar_candidatas(soup, url)
        if _es_imagen(u) and not _descartable(u)
    ]

    # Deduplicar preservando el orden de aparición, que suele ser el orden
    # real de la galería.
    vistas = set()
    limpias: List[str] = []
    for u in candidatas:
        sin_query = _sin_query(u)
        if sin_query not in vistas:
            vistas.add(sin_query)
            limpias.append(sin_query)

    if limpias:
        grupos: dict = {}
        for u in limpias:
            grupos.setdefault(_carpeta(u), []).append(u)
        return max(grupos.values(), key=len)

    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return [_sin_query(urljoin(url, og["content"]))]

    return []


async def obtener_fotos(url: str) -> dict:
    """Descarga una ficha y extrae sus fotos.

    Nunca lanza: en caso de error devuelve {"error": "..."}, igual que
    url_extractor.extract_from_url.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, verify=True,
                                     timeout=15) as client:
            response = await client.get(url, headers=BROWSER_HEADERS)
            if response.status_code == 404:
                return {"error": "URL no encontrada (404)"}
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}
            html = response.text
    except Exception as e:
        return {"error": str(e)}

    return {"fotos": extraer_fotos(html, url=url)}
```

Nota sobre `test_coge_la_foto_grande_del_enlace`: funciona porque `small1.jpg` cae por el filtro `small` de `_RUTA_MALA` y `big1.jpg` entra por el `<a href>`. Es el patrón real de `puertopiso`, donde la miniatura lleva `small`/`thumb` en el nombre.

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_foto_extractor.py -v`
Expected: todos PASSED (los 28 de Task 1 + 12 nuevos)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/foto_extractor.py tests/test_foto_extractor.py
git commit -m "feat: algoritmo generico de extraccion de fotos"
```

---

### Task 3: Botón y modal de previsualización

**Files:**
- Modify: `app/ui/property_dialogs.py` (añadir al final)
- Modify: `app/ui/property_card.py:118-123`

**Interfaces:**
- Consumes: `obtener_fotos()` de Task 2
- Produces: `buscar_fotos_dialog(prop, on_write=None)`

Antes de escribir nada, leer `app/ui/property_dialogs.py` líneas 40-70 (el patrón `asyncio.run` del diálogo "añadir por URL") y `fotos_dialog` (líneas 373-399), y seguir su estilo: decorador `@st.dialog`, uso de `Session(engine)`, y `PropiedadCRUD.update`.

- [ ] **Step 1: Escribir el modal**

Añadir al final de `app/ui/property_dialogs.py`:

```python
@st.dialog("🔍 Buscar fotos", width="large")
def buscar_fotos_dialog(prop, on_write=None):
    """Descarga la ficha, extrae imágenes y deja elegir cuáles guardar.

    Se previsualiza antes de guardar porque el extractor es genérico: en
    portales que sirven las fotos del anuncio y las del widget de
    'propiedades similares' desde la misma carpeta, no puede distinguirlas.
    """
    import asyncio

    from scraper.foto_extractor import obtener_fotos

    with st.spinner("Descargando la ficha…"):
        resultado = asyncio.run(obtener_fotos(prop.url_original))

    if "error" in resultado:
        st.error(f"No se pudo acceder a la ficha: {resultado['error']}")
        return

    fotos = resultado.get("fotos") or []
    if not fotos:
        st.warning("No se encontraron imágenes en esta ficha.")
        return

    if len(fotos) < 5:
        st.warning(
            f"Solo se han encontrado {len(fotos)} imágenes. "
            "Puede que este portal las cargue por JavaScript."
        )

    st.caption(f"{len(fotos)} imágenes encontradas. Desmarca las que no correspondan.")

    seleccion = []
    columnas = st.columns(4)
    for idx, foto in enumerate(fotos):
        with columnas[idx % 4]:
            st.markdown(
                f'<img src="{html_lib.escape(foto, quote=True)}" '
                f'style="width:100%;height:110px;object-fit:cover;border-radius:4px;">',
                unsafe_allow_html=True,
            )
            if st.checkbox("Usar", value=True, key=f"foto_sel_{prop.id}_{idx}"):
                seleccion.append(foto)

    st.divider()
    if st.button(
        f"💾 Guardar {len(seleccion)} fotos",
        type="primary",
        use_container_width=True,
        disabled=not seleccion,
        key=f"foto_save_{prop.id}",
    ):
        with Session(engine) as session:
            PropiedadCRUD.update(session, prop.id, fotos=seleccion)
        st.success(f"✅ Guardadas {len(seleccion)} fotos")
        if on_write:
            on_write()
        st.rerun()
```

`html_lib`, `st`, `Session`, `engine` y `PropiedadCRUD` ya están importados en ese fichero (los usa `fotos_dialog`). Verificarlo antes de añadir imports nuevos.

- [ ] **Step 2: Añadir el botón a la tarjeta**

En `app/ui/property_card.py`, sustituir el bloque de las líneas 118-123:

```python
        if p["fotos"]:
            if b[4].button("📸", key=f"fotos_{p['id']}", help="Ver fotos"):
                st.session_state[f"foto_idx_{p['id']}"] = 0
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                fotos_dialog(prop)
```

por:

```python
        if p["fotos"]:
            if b[4].button("📸", key=f"fotos_{p['id']}", help="Ver fotos"):
                st.session_state[f"foto_idx_{p['id']}"] = 0
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                fotos_dialog(prop)
        else:
            if b[4].button("🔍", key=f"buscar_fotos_{p['id']}", help="Buscar fotos"):
                with Session(engine) as session:
                    prop = session.get(Propiedad, p["id"])
                buscar_fotos_dialog(prop, on_write=on_write)
```

Y añadir `buscar_fotos_dialog` al import de la línea 99:

```python
    from ui.property_dialogs import (
        calculadora_modal, edit_property_dialog, fotos_dialog, buscar_fotos_dialog,
    )
```

El hueco `b[4]` estaba libre cuando no hay fotos, así que no hacen falta columnas nuevas ni cambios de layout.

- [ ] **Step 3: Verificar que los tests de UI siguen verdes**

Run: `pytest tests/test_property_card.py tests/test_fotos_dialog.py -v`
Expected: 0 fallos.

Si `test_property_card.py` afirma algo sobre el número de botones renderizados, actualizarlo: ahora `b[4]` tiene botón en ambas ramas.

- [ ] **Step 4: Probar a mano en la app**

Run: `streamlit run app/main.py`

En **Propiedades**, buscar una propiedad sin fotos (mostrará 🔍 en lugar de 📸) y pulsar el botón. Comprobar los tres caminos:
- ficha accesible con galería → aparecen miniaturas marcadas, se pueden desmarcar y guardar
- tras guardar, la tarjeta pasa a mostrar 📸
- una URL rota → mensaje de error, sin traza

Cerrar la app al terminar.

- [ ] **Step 5: Commit**

```bash
git add app/ui/property_dialogs.py app/ui/property_card.py
git commit -m "feat: boton y modal para buscar fotos desde la ficha"
```

---

### Task 4: Respaldo automático en los scrapers

**Files:**
- Modify: `app/scraper/url_extractor.py:126`
- Modify: `app/scraper/mobilia_scraper.py:144`
- Modify: `app/scraper/guadalete_scraper.py:131`
- Modify: `app/scraper/punto_hogar_scraper.py:116`
- Modify: `app/scraper/puerto_inmobiliaria.py:106`
- Create: `tests/test_foto_extractor_wiring.py`

**Interfaces:**
- Consumes: `extraer_fotos()` de Task 2
- Produces: nada que consuman tareas posteriores

**Cuidado con los returns tempranos.** `guadalete`, `punto_hogar` y `puerto_inmobiliaria` tienen varios `return` (404, HTTP no-200, vendida). Las líneas indicadas arriba son **el return final**, el único donde hay HTML parseado. No insertar en los tempranos: ahí no existe la variable de HTML.

`manual_scraper.py` **no se toca**: no parsea HTML, delega en `url_extractor.extract_from_url`. Queda cubierto por el cambio en `_parse_html`, que además arregla el diálogo "añadir por URL", hoy también sin fotos.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_foto_extractor_wiring.py`:

```python
"""El respaldo genérico de fotos está conectado en los scrapers sin extractor propio."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from unittest.mock import MagicMock, patch

import pytest

try:
    from unittest.mock import AsyncMock
except ImportError:
    class AsyncMock(MagicMock):
        async def __call__(self, *args, **kwargs):
            return super().__call__(*args, **kwargs)


HTML_CON_GALERIA = """
<html><body>
  <h1>Piso en venta</h1>
  <p>180.000 €</p>
  <img src="/fotos/anuncio/1.jpg">
  <img src="/fotos/anuncio/2.jpg">
  <img src="/fotos/anuncio/3.jpg">
  <img src="/img/logo.png">
</body></html>
"""

ESPERADAS = [
    "https://ejemplo.com/fotos/anuncio/1.jpg",
    "https://ejemplo.com/fotos/anuncio/2.jpg",
    "https://ejemplo.com/fotos/anuncio/3.jpg",
]


def test_url_extractor_emite_fotos():
    """Cubre manual_scraper y el diálogo 'añadir por URL'."""
    from scraper.url_extractor import _parse_html

    data = _parse_html(HTML_CON_GALERIA, url="https://ejemplo.com/piso/1")
    assert data.get("fotos") == ESPERADAS


def test_url_extractor_sin_fotos_no_pone_la_clave():
    from scraper.url_extractor import _parse_html

    data = _parse_html("<html><body><p>Piso</p></body></html>",
                       url="https://ejemplo.com/piso/1")
    assert "fotos" not in data or data["fotos"] == []


@pytest.mark.asyncio
async def test_punto_hogar_rellena_fotos_por_respaldo():
    from scraper.config import ScraperConfig
    from scraper.punto_hogar_scraper import PuntoHogarScraper

    with patch("httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = HTML_CON_GALERIA
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        scraper = PuntoHogarScraper(ScraperConfig())
        data = await scraper.scrape_property_details("https://ejemplo.com/piso/1")

    assert data.get("fotos") == ESPERADAS
```

Antes de escribirlos, abrir `tests/test_zona_wiring.py` y copiar exactamente su forma de mockear `httpx.AsyncClient`; si difiere de la de arriba, manda la del repo. Cada scraper construye el cliente a su manera (`mobilia` y `puerto_inmobiliaria` usan `self.fetch_content`, no `httpx` directo), así que **basta con un test de wiring para `punto_hogar`** más los dos de `url_extractor`: el resto es la misma inserción de tres líneas, ya cubierta por los tests del algoritmo.

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_foto_extractor_wiring.py -v`
Expected: FAIL — `assert None == [...]`, porque todavía no se emite `fotos`.

- [ ] **Step 3: Conectar `url_extractor`**

En `app/scraper/url_extractor.py`, añadir el import junto a los de `zona_utils` (línea 9):

```python
from .foto_extractor import extraer_fotos
```

Y en `_parse_html`, **justo antes** del `return data` de la línea 126:

```python
    fotos = extraer_fotos(html, url=url)
    if fotos:
        data["fotos"] = fotos
```

- [ ] **Step 4: Conectar los cuatro scrapers**

En cada uno, añadir el import `from .foto_extractor import extraer_fotos` junto a los demás imports relativos del fichero, e insertar el bloque de respaldo justo antes del return final indicado.

`app/scraper/mobilia_scraper.py`, antes del `return data` de la línea 144 (la variable con el HTML es `content`):

```python
            if not data.get("fotos"):
                fotos = extraer_fotos(content, url=property_url)
                if fotos:
                    data["fotos"] = fotos
```

`app/scraper/guadalete_scraper.py`, antes del `return data` de la línea 131 (variable `html`):

```python
        if not data.get("fotos"):
            fotos = extraer_fotos(html, url=url)
            if fotos:
                data["fotos"] = fotos
```

`app/scraper/punto_hogar_scraper.py`, antes del `return data` de la línea 116 (variable `html`):

```python
        if not data.get("fotos"):
            fotos = extraer_fotos(html, url=url)
            if fotos:
                data["fotos"] = fotos
```

`app/scraper/puerto_inmobiliaria.py`, antes del `return enriched_data` de la línea 106 (variable `content`, y el dict se llama `enriched_data`):

```python
            if not enriched_data.get("fotos"):
                fotos = extraer_fotos(content, url=property_url)
                if fotos:
                    enriched_data["fotos"] = fotos
```

Respetar la indentación de cada sitio: `mobilia` y `puerto_inmobiliaria` insertan dentro de un `try`, así que llevan un nivel más que `guadalete` y `punto_hogar`.

- [ ] **Step 5: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_foto_extractor_wiring.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Verificar que ningún scraper se ha roto**

Run: `pytest -q`
Expected: 0 fallos. Presta atención a `test_alonsaga_scraper.py`, `test_generic_scraper.py` y `test_propiedades_url_dialog.py`: si alguno afirma la ausencia de la clave `fotos`, ahora puede aparecer, y hay que actualizar la expectativa (no el código).

- [ ] **Step 7: Commit**

```bash
git add app/scraper/url_extractor.py app/scraper/mobilia_scraper.py \
        app/scraper/guadalete_scraper.py app/scraper/punto_hogar_scraper.py \
        app/scraper/puerto_inmobiliaria.py tests/test_foto_extractor_wiring.py
git commit -m "feat: respaldo generico de fotos en los scrapers sin extractor propio"
```

---

## Verificación final

- [ ] `pytest -q` → 0 fallos
- [ ] La app arranca; una propiedad sin fotos muestra 🔍 y otra con fotos muestra 📸
- [ ] El modal previsualiza, permite desmarcar y guarda; la tarjeta pasa a 📸
- [ ] Una URL rota muestra un error legible, no una traza
- [ ] Los extractores propios siguen mandando: una propiedad de `alonsaga` conserva sus fotos filtradas por ID
- [ ] `git log --oneline` muestra un commit por task

## Fuera de alcance

- Backfill masivo del histórico (se resuelve propiedad a propiedad desde la UI)
- Descargar o rehospedar imágenes (se guardan URLs)
- Reescribir los 3 extractores específicos existentes
- Portales que carguen la galería por JavaScript: `httpx` no ejecuta JS, así que ahí el extractor devolverá pocas imágenes o ninguna. El aviso de "menos de 5" es la señal de ese caso.

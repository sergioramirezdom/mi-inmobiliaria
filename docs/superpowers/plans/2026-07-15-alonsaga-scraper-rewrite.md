# Alonsaga Scraper Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `AlonsagaScraper` so the Alonsaga source collects data again, matching alonsaga.com's redesigned HTML/URLs (spec: `docs/superpowers/specs/2026-07-15-alonsaga-scraper-rewrite-design.md`).

**Architecture:** `app/scraper/alonsaga_scraper.py` exposes small pure helper functions (`_extract_tipo_from_url`, `_extract_property_id_from_url`, `_extract_fotos`, `_extract_room_count`, `_extract_descripcion`) that `AlonsagaScraper.scrape_property_details()` composes. Each helper is rewritten independently with its own unit test against a small HTML snippet (no live HTTP calls in tests, matching the existing pattern in `tests/test_alonsaga_scraper.py`). No changes to `generic.py`, `paginated_scraper.py`, or `sold_checker.py` — the routing/wiring for `detail_scraper_type="alonsaga"` is untouched.

**Tech Stack:** Python 3.12, BeautifulSoup4 (`lxml` parser), pytest (`asyncio_mode = auto`), httpx (unused by these changes — no network code touched).

## Global Constraints

- No HTTP calls inside unit tests — use static HTML snippets (existing project convention, see `tests/test_alonsaga_scraper.py`).
- `_extract_fotos` filenames use the format `https://www.inmoserver.com/fotos/{cliente}/wm/{property_id}_{hash}.jpg[?compression_params]` — filter and dedupe on this.
- Habitaciones/baños badge lives inside `div#inmueble2_caracteristicas`; the same icon classes (`fa-bed`, `fa-bath`) are reused lower on the page inside the "similares" widget — extraction MUST be scoped to `#inmueble2_caracteristicas`.
- New detail URL format: `https://www.alonsaga.com/Venta-{Tipo}-{Municipio}-{zona}-{id}` (no trailing slash in observed samples, but must tolerate one).

---

### Task 1: Rewrite `_extract_tipo_from_url` for the new URL format

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py:132-144`
- Test: `tests/test_alonsaga_scraper.py:29-41`

**Interfaces:**
- Produces: `_extract_tipo_from_url(url: str) -> Optional[str]` (signature unchanged, only behavior changes)

- [ ] **Step 1: Replace the existing tipo tests with new-format URLs**

Replace lines 29-41 of `tests/test_alonsaga_scraper.py`:

```python
def test_extract_tipo_casa():
    url = "https://www.alonsaga.com/Venta-Casa-El-Puerto-de-Santa-María-crevillet-pinar-alto-5022"
    assert _extract_tipo_from_url(url) == "casa"


def test_extract_tipo_piso():
    url = "https://www.alonsaga.com/Venta-Piso-El-Puerto-de-Santa-María-Carretera-de-sanlucar-3991"
    assert _extract_tipo_from_url(url) == "piso"


def test_extract_tipo_with_trailing_slash():
    url = "https://www.alonsaga.com/Venta-Vivienda-El-Puerto-de-Santa-María-Vistahermosa-1234/"
    assert _extract_tipo_from_url(url) == "vivienda"


def test_extract_tipo_unknown():
    url = "https://www.alonsaga.com/encargo_venta"
    assert _extract_tipo_from_url(url) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_tipo -v`
Expected: FAIL — `test_extract_tipo_casa`, `test_extract_tipo_piso`, `test_extract_tipo_with_trailing_slash` fail (old regex doesn't match new URL format); `test_extract_tipo_unknown` passes trivially.

- [ ] **Step 3: Rewrite `_extract_tipo_from_url`**

Replace lines 132-144 of `app/scraper/alonsaga_scraper.py`:

```python
def _extract_tipo_from_url(url: str) -> Optional[str]:
    """Extract property type from URL path: /Venta-{Tipo}-{Municipio}-...-{id} → tipo (lowercase)"""
    m = re.search(r"/Venta-([A-Za-z]+)-", url)
    if m:
        return m.group(1).lower()
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_tipo -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "fix: update Alonsaga tipo_propiedad extraction for new URL format"
```

---

### Task 2: Add `_extract_property_id_from_url`

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py` (new function, place after `_extract_tipo_from_url`)
- Test: `tests/test_alonsaga_scraper.py` (new tests, place after Task 1's tests)

**Interfaces:**
- Consumes: nothing new
- Produces: `_extract_property_id_from_url(url: str) -> Optional[str]` — used by Task 3 and Task 5

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_alonsaga_scraper.py` (after the `test_extract_tipo_unknown` test added in Task 1):

```python
from scraper.alonsaga_scraper import _extract_property_id_from_url


def test_extract_property_id():
    url = "https://www.alonsaga.com/Venta-Casa-El-Puerto-de-Santa-María-crevillet-pinar-alto-5022"
    assert _extract_property_id_from_url(url) == "5022"


def test_extract_property_id_trailing_slash():
    url = "https://www.alonsaga.com/Venta-Piso-El-Puerto-de-Santa-María-Carretera-de-sanlucar-3991/"
    assert _extract_property_id_from_url(url) == "3991"


def test_extract_property_id_none_when_missing():
    url = "https://www.alonsaga.com/encargo_venta"
    assert _extract_property_id_from_url(url) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_property_id -v`
Expected: FAIL with `ImportError: cannot import name '_extract_property_id_from_url'`

- [ ] **Step 3: Implement `_extract_property_id_from_url`**

Add to `app/scraper/alonsaga_scraper.py`, directly after `_extract_tipo_from_url`:

```python
def _extract_property_id_from_url(url: str) -> Optional[str]:
    """Extract the numeric property id at the end of the detail URL."""
    m = re.search(r"-(\d+)/?$", url)
    return m.group(1) if m else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_property_id -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "feat: add Alonsaga property id extraction helper"
```

---

### Task 3: Rewrite `_extract_fotos` to filter by property id

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py:147-153`
- Test: `tests/test_alonsaga_scraper.py:44-63`

**Interfaces:**
- Consumes: `_extract_property_id_from_url` (Task 2) — used by the caller in Task 5, not by `_extract_fotos` itself
- Produces: `_extract_fotos(soup: BeautifulSoup, property_id: str) -> List[str]` (signature changed: now takes `property_id`)

- [ ] **Step 1: Replace the existing fotos tests**

Replace lines 44-63 of `tests/test_alonsaga_scraper.py`:

```python
def test_extract_fotos_filters_by_property_id():
    html = """
    <html><body>
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg">
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_def456.jpg?auto=compress&cs=tinysrgb&h=650&w=940">
      <img src="https://www.inmoserver.com/fotos/1266/wm/3945_other.jpg">
      <img src="https://other.com/photo.jpg">
      <img src="/static/logo.png">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup, "5022")
    assert fotos == [
        "https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg",
        "https://www.inmoserver.com/fotos/1266/wm/5022_def456.jpg",
    ]


def test_extract_fotos_dedupes_compressed_variant():
    html = """
    <html><body>
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg">
      <img src="https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg?auto=compress&cs=tinysrgb&h=650&w=940">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos(soup, "5022")
    assert fotos == ["https://www.inmoserver.com/fotos/1266/wm/5022_abc123.jpg"]


def test_extract_fotos_empty_when_none():
    soup = BeautifulSoup("<html><body><p>no images</p></body></html>", "lxml")
    assert _extract_fotos(soup, "5022") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_fotos -v`
Expected: FAIL — `TypeError: _extract_fotos() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Rewrite `_extract_fotos`**

Replace lines 147-153 of `app/scraper/alonsaga_scraper.py`:

```python
def _extract_fotos(soup: BeautifulSoup, property_id: str) -> List[str]:
    """Return unique photo URLs belonging to this property (excludes 'similares' widget photos)."""
    marker = f"/wm/{property_id}_"
    seen = set()
    fotos = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if marker not in src:
            continue
        base = src.split("?")[0]
        if base not in seen:
            seen.add(base)
            fotos.append(base)
    return fotos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_fotos -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "fix: filter Alonsaga photos by property id on new inmoserver.com CDN"
```

---

### Task 4: Add `_extract_room_count` (icon-based habitaciones/baños)

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py` (new function, place after `_extract_fotos`)
- Test: `tests/test_alonsaga_scraper.py` (new tests, place after Task 3's tests)

**Interfaces:**
- Consumes: nothing new
- Produces: `_extract_room_count(soup: BeautifulSoup, icon_class: str) -> Optional[int]` — used by Task 6 (`scrape_property_details`) with `icon_class="fa-bed"` and `icon_class="fa-bath"`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_alonsaga_scraper.py` (after the fotos tests added in Task 3):

```python
from scraper.alonsaga_scraper import _extract_room_count


def test_extract_room_count_reads_icon_badge():
    html = """
    <html><body>
      <div id="inmueble2_caracteristicas">
        <div><i class='fas fa-bed'></i><span class='p-2'>5</span></div>
        <div><i class='fas fa-bath'></i><span class='p-2'>2</span></div>
        <div><i class='fas fa-warehouse'></i><span class='p-2'>1</span></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 5
    assert _extract_room_count(soup, "fa-bath") == 2


def test_extract_room_count_ignores_similares_widget():
    """The 'similares' carousel reuses fa-bed/fa-bath outside #inmueble2_caracteristicas — must be ignored."""
    html = """
    <html><body>
      <div id="inmueble2_caracteristicas">
        <div><i class='fas fa-bed'></i><span class='p-2'>5</span></div>
      </div>
      <div class="inmuebles_similares_habitaciones">
        <i class="fas fa-bed"></i><span class="p-2">99</span>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 5


def test_extract_room_count_none_when_container_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_room_count(soup, "fa-bed") is None


def test_extract_room_count_none_when_icon_missing():
    html = "<div id='inmueble2_caracteristicas'><div><i class='fas fa-bath'></i><span>2</span></div></div>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_room_count -v`
Expected: FAIL with `ImportError: cannot import name '_extract_room_count'`

- [ ] **Step 3: Implement `_extract_room_count`**

Add to `app/scraper/alonsaga_scraper.py`, directly after `_extract_fotos`:

```python
def _extract_room_count(soup: BeautifulSoup, icon_class: str) -> Optional[int]:
    """Read the numeric badge next to a feature icon inside #inmueble2_caracteristicas.

    Scoped to that container because the 'similares' widget further down the
    page reuses the same fa-bed/fa-bath icon classes for other properties.
    """
    container = soup.select_one("#inmueble2_caracteristicas")
    if not container:
        return None
    icon = container.select_one(f"i.{icon_class}")
    if not icon:
        return None
    span = icon.find_next_sibling("span")
    if not span:
        return None
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_room_count -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "feat: add icon-based habitaciones/banos extraction for Alonsaga"
```

---

### Task 5: Add `_extract_descripcion`

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py` (new function, place after `_extract_room_count`)
- Test: `tests/test_alonsaga_scraper.py` (new tests, place after Task 4's tests)

**Interfaces:**
- Consumes: nothing new
- Produces: `_extract_descripcion(soup: BeautifulSoup) -> Optional[str]` — used by Task 6

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_alonsaga_scraper.py` (after the room-count tests added in Task 4):

```python
from scraper.alonsaga_scraper import _extract_descripcion


def test_extract_descripcion_reads_new_container():
    long_text = "Casa reformada con jardín y piscina. " * 3
    html = f"<p id='inmueble2_datos_adicionales'>{long_text}</p>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_descripcion(soup) == long_text.strip()


def test_extract_descripcion_none_when_missing():
    soup = BeautifulSoup("<html><body><p>otro parrafo</p></body></html>", "lxml")
    assert _extract_descripcion(soup) is None


def test_extract_descripcion_none_when_too_short():
    soup = BeautifulSoup("<p id='inmueble2_datos_adicionales'>corto</p>", "lxml")
    assert _extract_descripcion(soup) is None


def test_extract_descripcion_truncates_to_2000_chars():
    long_text = "x" * 3000
    html = f"<p id='inmueble2_datos_adicionales'>{long_text}</p>"
    soup = BeautifulSoup(html, "lxml")
    result = _extract_descripcion(soup)
    assert len(result) == 2000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_descripcion -v`
Expected: FAIL with `ImportError: cannot import name '_extract_descripcion'`

- [ ] **Step 3: Implement `_extract_descripcion`**

Add to `app/scraper/alonsaga_scraper.py`, directly after `_extract_room_count`:

```python
def _extract_descripcion(soup: BeautifulSoup) -> Optional[str]:
    """Alonsaga puts the full description text in p#inmueble2_datos_adicionales."""
    p = soup.select_one("p#inmueble2_datos_adicionales")
    if not p:
        return None
    text = p.get_text(strip=True)
    return text[:2000] if len(text) > 50 else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_alonsaga_scraper.py -k extract_descripcion -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/scraper/alonsaga_scraper.py tests/test_alonsaga_scraper.py
git commit -m "feat: add Alonsaga description extraction for new HTML container"
```

---

### Task 6: Wire the new helpers into `scrape_property_details`

**Files:**
- Modify: `app/scraper/alonsaga_scraper.py:34-120` (the `scrape_property_details` method body)

**Interfaces:**
- Consumes: `_extract_tipo_from_url` (Task 1), `_extract_property_id_from_url` (Task 2), `_extract_fotos` (Task 3), `_extract_room_count` (Task 4), `_extract_descripcion` (Task 5)
- Produces: `AlonsagaScraper.scrape_property_details(url) -> Dict[str, Any]` (same signature, corrected behavior)

- [ ] **Step 1: Replace the title, rooms/baths, tipo, photos, and description blocks**

In `app/scraper/alonsaga_scraper.py`, replace lines 67-114 (from the `# Title:` comment through the `# Description:` block) with:

```python
        # Title: h1 text as-is (the old "Alonsaga X - " prefix no longer appears)
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

        # Price: format "180.000 €" or "180.000€"
        price_match = re.search(r"([\d.]+(?:,\d+)?)\s*€", page_text)
        if price_match:
            data["precio"] = _parse_price_eu(price_match.group(1))

        # Superficie via regex (format: "75 m²")
        m2_match = re.search(r"([\d.,]+)\s*m²", page_text)
        if m2_match:
            val = m2_match.group(1).replace(".", "").replace(",", ".")
            try:
                data["superficie_m2"] = float(val)
            except (ValueError, TypeError):
                pass

        # Habitaciones/banos: icon badges inside #inmueble2_caracteristicas
        habitaciones = _extract_room_count(soup, "fa-bed")
        if habitaciones is not None:
            data["habitaciones"] = habitaciones
        banos = _extract_room_count(soup, "fa-bath")
        if banos is not None:
            data["banos"] = banos

        # Fixed municipio
        data["municipio"] = "El Puerto de Santa María"

        # Property type from URL
        tipo = _extract_tipo_from_url(url)
        if tipo:
            data["tipo_propiedad"] = tipo

        # Photos: filtered by this property's id to exclude the "similares" widget
        property_id = _extract_property_id_from_url(url)
        if property_id:
            fotos = _extract_fotos(soup, property_id)
            if fotos:
                data["fotos"] = fotos

        # Description: alonsaga puts the full text in p#inmueble2_datos_adicionales
        desc = _extract_descripcion(soup)
        if desc:
            data["descripcion"] = desc
```

- [ ] **Step 2: Run the full Alonsaga test file to confirm nothing broke**

Run: `pytest tests/test_alonsaga_scraper.py tests/test_alonsaga_wiring.py -v`
Expected: PASS (all tests green)

- [ ] **Step 3: Commit**

```bash
git add app/scraper/alonsaga_scraper.py
git commit -m "fix: wire new Alonsaga extraction helpers into scrape_property_details"
```

---

### Task 7: Manual smoke test against the live site

**Files:** none (verification only, no code changes)

- [ ] **Step 1: Run a one-off script against a real Alonsaga detail page**

Run (from the repo root, with the project's Python environment active — needs `httpx`, `beautifulsoup4`, `lxml`):

```bash
python -c "
import asyncio, sys
sys.path.insert(0, 'app')
from scraper.alonsaga_scraper import AlonsagaScraper

async def main():
    scraper = AlonsagaScraper()
    data = await scraper.scrape_property_details('https://www.alonsaga.com/Venta-Casa-El-Puerto-de-Santa-Mar%C3%ADa-crevillet-pinar-alto-5022')
    for k, v in data.items():
        if k in ('descripcion', 'fotos'):
            print(k, '=', (str(v)[:80] + '...') if v else v)
        else:
            print(k, '=', v)

asyncio.run(main())
"
```

Expected output includes non-empty `titulo`, `precio` around `350000.0`, `superficie_m2` around `315.0`, `habitaciones=5`, `banos=2`, `tipo_propiedad='casa'`, `municipio='El Puerto de Santa María'`, a non-empty `descripcion`, and a non-empty `fotos` list where every URL contains `/wm/5022_`.

- [ ] **Step 2: If any field is missing or wrong, stop and re-open the relevant task above — do not proceed to Task 8 until this passes.**

---

### Task 8: Update the live Fuente record (manual, in the Streamlit app)

**Files:** none (data change via UI, not code)

- [ ] **Step 1: Open the app and edit the Alonsaga source**

Run: `streamlit run app/main.py`, go to the "Fuentes" page, open the existing "Alonsaga" source for editing.

- [ ] **Step 2: Update the URL field to:**

```
https://www.alonsaga.com/buscar.php?o=Venta&po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa&check_zona%5B%5D=crevillet-pinar+alto
```

- [ ] **Step 3: Update the "Notas" JSON field to:**

```json
{
  "detail_scraper_type": "alonsaga",
  "selectors": {
    "property_container": "div.listado5_contendor_inmueble",
    "title": "div.listado5_contendor_inmueble_datos_titulo"
  },
  "patterns": { "price_pattern": "([\\d.,]+)\\s*€" },
  "pagination_param": "pag",
  "pagination_start": 1,
  "pagination_skip_first": true,
  "use_results_per_page": false
}
```

- [ ] **Step 4: Save, then run a single scrape cycle for this source only**

Run: `python scripts/scheduler.py --once --force`

Expected: log output shows the Alonsaga source finding and saving properties (`nuevas` > 0 if there are new listings, or `duplicadas` > 0 on a re-run), no more "0 properties found" / consecutive empty pages.

---

## Self-Review Notes

- **Spec coverage:** Section 1 (Fuente config) → Task 8. Section 2 (scraper rewrite table) → Tasks 1-6, one row per helper, all covered. Section 3 (tests) → each rewrite task carries its own test rewrite/addition; `test_alonsaga_wiring.py` and `test_generic_scraper_extracts_data_path_url` are explicitly left untouched per spec, no task modifies them.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command with expected output.
- **Type consistency:** `_extract_fotos(soup, property_id: str)`, `_extract_room_count(soup, icon_class: str) -> Optional[int]`, `_extract_descripcion(soup) -> Optional[str]`, `_extract_property_id_from_url(url) -> Optional[str]` — signatures match between the task that defines them and the task (6) that calls them.

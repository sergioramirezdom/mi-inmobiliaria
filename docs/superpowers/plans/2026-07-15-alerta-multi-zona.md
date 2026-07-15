# Alerta Multi-Zona Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `FiltroAlerta` match against several zones/keywords instead of one, so a property matches if it's in *any* of the specified zones (spec: `docs/superpowers/specs/2026-07-15-alerta-multi-zona-design.md`).

**Architecture:** `criterios_json["barrio"]` stays a single string but may now hold several comma-separated zones (same storage pattern already used for `amenidades`). `FilterMatcher._match_criterion` gains OR-across-zones logic. `PropiedadCRUD.get_distinct_barrios` supplies suggestions for a new `st.multiselect` (with free-entry) replacing the old `st.text_input` in `app/pages/3_alertas.py`. No DB schema change, no migration.

**Tech Stack:** Python 3.12, SQLModel/SQLAlchemy, Streamlit 1.54 (`st.multiselect(..., accept_new_options=True)`), pytest.

## Global Constraints

- Storage format: `criterios_json["barrio"]` is a comma-separated string (e.g. `"crevillet, pinar alto, menesteo"`), matching the existing `amenidades` convention (`app/pages/3_alertas.py` `build_criteria`).
- Match semantics for `barrio` are **OR** (any zone matching is enough) — this is the opposite of `amenidades`'s AND semantics; do not copy the AND logic.
- Backward compatible by construction: a legacy single-value string with no commas must keep matching exactly as before (as a one-element list after split).
- `FilterMatcher._match_criterion`'s existing str-or-list handling pattern (see the `amenidades` branch) is the template to follow for `barrio`.
- No SQLite-backed test may instantiate the real `Propiedad` table — it has two `ARRAY(String)` columns (`fotos`, `amenidades`) that SQLite cannot compile. Use a mocked `Session` for anything touching `PropiedadCRUD`, per this codebase's existing pattern in `tests/test_propiedades_url_dialog.py` (raw table creation only for ARRAY-free tables like `Fuente`).

---

### Task 1: `PropiedadCRUD.get_distinct_barrios`

**Files:**
- Modify: `app/db/database.py` (add method to `PropiedadCRUD`, after `toggle_favorite` at line 186)
- Test: `tests/test_database_barrios.py` (new file)

**Interfaces:**
- Produces: `PropiedadCRUD.get_distinct_barrios(session: Session) -> List[str]` — used by Task 4 (UI)

- [ ] **Step 1: Write the failing test**

Create `tests/test_database_barrios.py`:

```python
"""Tests for PropiedadCRUD.get_distinct_barrios."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.database import PropiedadCRUD


def _mock_session(barrio_rows):
    session = MagicMock()
    session.exec.return_value.all.return_value = barrio_rows
    return session


def test_get_distinct_barrios_dedupes_and_sorts_case_insensitive():
    session = _mock_session(["Valdelagrana", "crevillet", "Valdelagrana", "Vistahermosa"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["crevillet", "Valdelagrana", "Vistahermosa"]


def test_get_distinct_barrios_filters_none_and_blank():
    session = _mock_session(["Valdelagrana", None, "  ", "", "Crevillet"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["Crevillet", "Valdelagrana"]


def test_get_distinct_barrios_strips_whitespace():
    session = _mock_session(["  Valdelagrana  ", "Crevillet"])
    result = PropiedadCRUD.get_distinct_barrios(session)
    assert result == ["Crevillet", "Valdelagrana"]


def test_get_distinct_barrios_empty_when_no_properties():
    session = _mock_session([])
    assert PropiedadCRUD.get_distinct_barrios(session) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_database_barrios.py -v`
Expected: FAIL with `AttributeError: type object 'PropiedadCRUD' has no attribute 'get_distinct_barrios'`

- [ ] **Step 3: Implement `get_distinct_barrios`**

In `app/db/database.py`, add after `toggle_favorite` (currently ends at line 186, just before the `# CRUD Helpers for FiltroAlerta` comment):

```python
    @staticmethod
    def get_distinct_barrios(session: Session) -> List[str]:
        """Get all distinct non-empty barrio values, sorted alphabetically (case-insensitive)."""
        rows = session.exec(
            select(Propiedad.barrio).where(Propiedad.barrio.is_not(None)).distinct()
        ).all()
        return sorted({b.strip() for b in rows if b and b.strip()}, key=str.lower)
```

(`select`, `Session`, `List`, and `Propiedad` are already imported at the top of `app/db/database.py` — confirm before adding; if `List` isn't imported from `typing`, add it to the existing `typing` import line.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_database_barrios.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/db/database.py tests/test_database_barrios.py
git commit -m "feat: add PropiedadCRUD.get_distinct_barrios for alert zona suggestions"
```

---

### Task 2: `FilterMatcher` — OR-across-zones matching for `barrio`

**Files:**
- Modify: `app/notifications/filter_matcher.py:93-98`
- Test: `tests/test_filter_matcher_barrio.py` (new file)

**Interfaces:**
- Consumes: nothing new
- Produces: unchanged signature `FilterMatcher._match_criterion(propiedad, "barrio", value)` — `value` may now be a comma-separated string (or a real list) instead of only a single-zone string

- [ ] **Step 1: Write the failing tests**

Create `tests/test_filter_matcher_barrio.py`:

```python
"""Tests for FilterMatcher's barrio (zona) OR-matching."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from notifications.filter_matcher import FilterMatcher
from db.models import Propiedad


def _propiedad(barrio):
    return Propiedad(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="test",
        titulo="t", barrio=barrio,
    )


def test_barrio_single_legacy_value_still_matches():
    """Backward compat: old alerts stored a single value with no commas."""
    prop = _propiedad("Valdelagrana")
    assert FilterMatcher._match_criterion(prop, "barrio", "valdelagrana") is True


def test_barrio_matches_any_of_several_zones():
    prop = _propiedad("Crevillet-Pinar Alto")
    value = "vistahermosa, crevillet, menesteo"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True


def test_barrio_no_match_when_none_of_the_zones_present():
    prop = _propiedad("Vistahermosa")
    value = "crevillet, pinar alto, menesteo"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is False


def test_barrio_accepts_real_list_not_just_string():
    prop = _propiedad("Pago de la Alhaja")
    value = ["crevillet", "pago de la alhaja"]
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True


def test_barrio_none_when_property_has_no_barrio():
    prop = _propiedad(None)
    assert FilterMatcher._match_criterion(prop, "barrio", "crevillet") is False


def test_barrio_ignores_blank_entries_in_list():
    prop = _propiedad("Crevillet")
    value = "crevillet, , pinar alto"
    assert FilterMatcher._match_criterion(prop, "barrio", value) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_filter_matcher_barrio.py -v`
Expected: FAIL — `test_barrio_matches_any_of_several_zones` and `test_barrio_accepts_real_list_not_just_string` fail (current code does `value.lower() in propiedad.barrio.lower()`, so a multi-zone string or a real list either never matches or raises `AttributeError` on `.lower()` for a list). `test_barrio_single_legacy_value_still_matches` and the no-match/None cases pass already (they only exercise pre-existing single-value behavior).

- [ ] **Step 3: Rewrite the `barrio` branch**

In `app/notifications/filter_matcher.py`, replace lines 93-98:

```python
        # Zone/Neighborhood (partial match)
        if key == "barrio":
            if propiedad.barrio is None:
                return False
            # Case-insensitive partial match
            return value.lower() in propiedad.barrio.lower()
```

with:

```python
        # Zone/Neighborhood — matches if ANY of the given zones is a
        # substring of the property's barrio (OR logic, unlike amenidades'
        # AND logic below). value may be a comma-separated string (legacy
        # single value or new multi-value) or a real list.
        if key == "barrio":
            if propiedad.barrio is None:
                return False
            if isinstance(value, str):
                zonas = [z.strip().lower() for z in value.split(",") if z.strip()]
            else:
                zonas = [str(z).strip().lower() for z in value if str(z).strip()]
            prop_barrio = propiedad.barrio.lower()
            return any(z in prop_barrio for z in zonas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_filter_matcher_barrio.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full existing suite to confirm nothing else broke**

Run: `python -m pytest tests/ -v -k "not test_scraper_config"`

(`test_scraper_config`'s 5 `timeout` failures are pre-existing and unrelated — see project history; excluding them here keeps the signal clean. Every other test must still pass.)

- [ ] **Step 6: Commit**

```bash
git add app/notifications/filter_matcher.py tests/test_filter_matcher_barrio.py
git commit -m "feat: match alert zona against multiple comma-separated values (OR)"
```

---

### Task 3: `build_criteria()` — accept a list of zones

**Files:**
- Modify: `app/pages/3_alertas.py:23-38`
- Test: `tests/test_alertas_criteria.py` (new file)

**Interfaces:**
- Consumes: nothing new
- Produces: `build_criteria(..., barrio, ...)` — `barrio` parameter changes from a single string to a list of strings; return value's `criteria["barrio"]` is a comma-space-joined string (or `None` if the list is empty)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alertas_criteria.py`:

```python
"""Tests for build_criteria's zona (barrio) list handling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "pages"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "alertas_page", str(Path(__file__).parent.parent / "app" / "pages" / "3_alertas.py")
)
alertas_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alertas_page)

build_criteria = alertas_page.build_criteria


def _call(barrio):
    return build_criteria(
        precio_min=0, precio_max=0, m2_min=0, m2_max=0, habitaciones=0, banos=0,
        barrio=barrio, tipo_propiedad=None, estado=None, amenidades=[],
        ascensor=False, garaje=False, terraza=False, piscina=False,
    )


def test_build_criteria_joins_multiple_zones():
    criteria = _call(["crevillet", "pinar alto", "menesteo"])
    assert criteria["barrio"] == "crevillet, pinar alto, menesteo"


def test_build_criteria_single_zone():
    criteria = _call(["crevillet"])
    assert criteria["barrio"] == "crevillet"


def test_build_criteria_empty_list_is_none():
    criteria = _call([])
    assert criteria.get("barrio") is None
```

Note: `app/pages/3_alertas.py` starts with a numeric-prefixed filename (`3_alertas.py`), which isn't a valid Python module name for a plain `import` — the test loads it via `importlib.util` from its file path instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alertas_criteria.py -v`
Expected: FAIL — `test_build_criteria_joins_multiple_zones` and `test_build_criteria_single_zone` fail with `AttributeError: 'list' object has no attribute 'strip'` (current code calls `barrio.strip()` assuming a string). `test_build_criteria_empty_list_is_none` may also fail for the same reason (an empty list has no `.strip()` either).

- [ ] **Step 3: Update `build_criteria`**

In `app/pages/3_alertas.py`, replace line 34:

```python
        barrio=barrio.strip() if barrio.strip() else None,
```

with:

```python
        barrio=", ".join(z.strip() for z in barrio if z.strip()) if barrio else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alertas_criteria.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/pages/3_alertas.py tests/test_alertas_criteria.py
git commit -m "feat: build_criteria accepts a list of zonas, stored comma-joined"
```

---

### Task 4: Replace the zona text input with a multi-select in `criteria_form()`

**Files:**
- Modify: `app/pages/3_alertas.py:1-20` (imports), `app/pages/3_alertas.py:82-83` (the widget itself)

**Interfaces:**
- Consumes: `PropiedadCRUD.get_distinct_barrios` (Task 1), `build_criteria`'s new list-based `barrio` param (Task 3)
- Produces: `criteria_form()`'s returned dict now has `barrio` as a `List[str]` instead of `str` — this flows straight into `build_criteria(**vals)`, already updated in Task 3

This task has no dedicated automated test (it's Streamlit widget wiring — this codebase doesn't unit-test widget rendering, see `tests/test_fotos_dialog.py`'s pattern of only testing extracted pure logic). Verification is manual: run the app and exercise the form.

- [ ] **Step 1: Add a cached helper and import `PropiedadCRUD`**

In `app/pages/3_alertas.py`, change line 11:

```python
from db.database import engine
```

to:

```python
from db.database import engine, PropiedadCRUD
```

Then add this function right after the `AMENIDADES_OPTS` constant (currently lines 19-20):

```python
@st.cache_data(ttl=300)
def get_distinct_barrios_cached() -> list[str]:
    """Cached list of existing barrio values, used as multiselect suggestions."""
    with Session(engine) as session:
        return PropiedadCRUD.get_distinct_barrios(session)
```

- [ ] **Step 2: Replace the zona `st.text_input` with `st.multiselect`**

Replace lines 82-83:

```python
    barrio = st.text_input("Zona/Barrio (búsqueda parcial)", value=d.get("barrio", ""),
                           key=f"{prefix}_barrio")
```

with:

```python
    barrios_existentes = get_distinct_barrios_cached()
    barrio_val = d.get("barrio", "")
    barrio_default = [b.strip() for b in barrio_val.split(",") if b.strip()] if barrio_val else []
    barrio = st.multiselect(
        "Zona/Barrio (una o varias — coincide con cualquiera)",
        options=sorted(set(barrios_existentes) | set(barrio_default)),
        default=barrio_default,
        accept_new_options=True,
        key=f"{prefix}_barrio",
    )
```

- [ ] **Step 3: Manual verification**

Run: `streamlit run app/main.py`

Go to the "Alertas" page:
1. Open "Nueva alerta" — confirm the "Zona/Barrio" field is now a multiselect. Type a zone name that doesn't exist yet (e.g. "menesteo") and press Enter — confirm it gets added as a chip.
2. Add 2-3 more zones (mixing free-typed and, if any exist, suggested ones), save the alert.
3. Re-open the alert for editing — confirm all the zones you entered are pre-selected as chips (not lost, not merged into one string).
4. If any existing property has a `barrio` containing one of the zones you entered, use the "🔍 Propiedades coincidentes" test-alert feature (existing dialog in this page) to confirm it now matches.
5. Confirm an alert created before this change (single-zone, if one exists) still loads and edits correctly (no crash, zone pre-filled as a single chip).

- [ ] **Step 4: Commit**

```bash
git add app/pages/3_alertas.py
git commit -m "feat: multi-select zona input with free-entry and DB suggestions"
```

---

## Self-Review Notes

- **Spec coverage:** Spec section 1 (storage) → Task 3. Section 2 (matcher OR logic) → Task 2. Section 3 (distinct-barrios CRUD) → Task 1. Section 4 (UI multiselect + build_criteria + cache) → Tasks 3 and 4. `format_criteria()` explicitly needs no change per spec — no task touches it, consistent.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command with expected output.
- **Type consistency:** `get_distinct_barrios(session: Session) -> List[str]` (Task 1) is called as `PropiedadCRUD.get_distinct_barrios(session)` in Task 4's cached wrapper — signature matches. `build_criteria`'s `barrio` parameter is a `List[str]` from Task 3 onward, matching what Task 4's `st.multiselect` returns (`list[str]`).
- **Test isolation:** Task 1 and the manual verification in Task 4 are the only places touching anything DB-shaped; Task 1 uses a mocked `Session` (per Global Constraints, ARRAY columns block real SQLite table creation), Task 4 is manual against the real configured database.

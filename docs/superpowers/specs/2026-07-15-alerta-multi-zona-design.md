# Alertas — Múltiples zonas por filtro

**Fecha:** 2026-07-15
**Estado:** Aprobado por usuario

---

## Objetivo

Hoy el campo "Zona/Barrio" de una alerta (`FiltroAlerta`) solo acepta una palabra/frase (`st.text_input`), comparada como substring parcial contra `Propiedad.barrio`. El usuario quiere poder especificar varias zonas o palabras clave en una misma alerta (ej. "Crevillet", "Pinar Alto", "Pago de la Alhaja", "Menesteo") y que la alerta salte si la propiedad coincide con **cualquiera** de ellas.

---

## Contexto (estado actual)

- `FiltroAlerta.criterios_json` (`app/db/models.py:120`) es un blob JSON libre; no hay columna dedicada para zona.
- `FilterMatcher._match_criterion` (`app/notifications/filter_matcher.py:93-98`) compara `criterios["barrio"]` (un string) como substring case-insensitive de `propiedad.barrio` (también un string).
- `app/pages/3_alertas.py:82-83` renderiza el campo con `st.text_input`, un único valor.
- Precedente ya existente para múltiples valores: **`amenidades`** (`app/pages/3_alertas.py:87-88`, `filter_matcher.py:141-152`) — se guarda como string separado por comas dentro de `criterios_json`, seleccionado vía `st.multiselect` sobre una lista fija (`AMENIDADES_OPTS`), y el matcher acepta tanto string como lista real. La semántica de `amenidades` es **AND** (debe tener todas); la de `barrio` será **OR** (basta con una).
- `Propiedad.barrio` se puebla siempre como un único nombre de zona limpio (`zona_utils.py`, `description_enricher.py`), nunca una lista — sigue siendo un string simple en el modelo de propiedad, esto no cambia.
- No existe hoy ningún vocabulario fijo de zonas (a diferencia de `AMENIDADES_OPTS`), así que no hay un `st.multiselect` cerrado aplicable directamente.

---

## Diseño

### 1. Almacenamiento en `criterios_json`

Igual que `amenidades`: `criterios["barrio"]` sigue siendo un **string único**, pero ahora puede contener varias zonas separadas por coma: `"crevillet, pinar alto, pago la alhaja, menesteo"`.

Compatibilidad hacia atrás automática: una alerta antigua con un único valor sin comas (ej. `"Valdelagrana"`) se sigue tratando como lista de un elemento — no requiere migración de datos.

### 2. `FilterMatcher._match_criterion` — lógica OR

`app/notifications/filter_matcher.py:93-98` cambia de:

```python
if key == "barrio":
    if propiedad.barrio is None:
        return False
    return value.lower() in propiedad.barrio.lower()
```

a (mismo patrón str-o-lista que ya usa `amenidades`, línea 145-148):

```python
if key == "barrio":
    if propiedad.barrio is None:
        return False
    if isinstance(value, str):
        zonas = [z.strip().lower() for z in value.split(",") if z.strip()]
    else:
        zonas = [str(z).strip().lower() for z in value]
    prop_barrio = propiedad.barrio.lower()
    return any(z in prop_barrio for z in zonas)
```

### 3. Sugerencias de zonas existentes — nuevo método CRUD

`app/db/database.py`, nuevo método en `PropiedadCRUD` (siguiendo el estilo `@staticmethod` existente):

```python
@staticmethod
def get_distinct_barrios(session: Session) -> List[str]:
    """Get all distinct non-empty barrio values, sorted alphabetically."""
    rows = session.exec(
        select(Propiedad.barrio).where(Propiedad.barrio.is_not(None)).distinct()
    ).all()
    return sorted({b for b in rows if b and b.strip()})
```

### 4. UI — `app/pages/3_alertas.py`

- `criteria_form()` (línea 82-83): el `st.text_input` de zona se sustituye por:

```python
barrios_existentes = get_distinct_barrios_cached()  # ver nota cache abajo
barrio_val = d.get("barrio", "")
barrio_default = [b.strip() for b in barrio_val.split(",") if b.strip()] if barrio_val else []
barrios = st.multiselect(
    "Zona/Barrio (una o varias — coincide con cualquiera)",
    options=sorted(set(barrios_existentes) | set(barrio_default)),
    default=barrio_default,
    accept_new_options=True,
    key=f"{prefix}_barrio",
)
```

  `accept_new_options=True` (Streamlit ≥1.40, confirmado disponible en la versión instalada 1.54) permite escribir zonas que no están en la lista de sugerencias, igual que pide el usuario para "Menesteo" u otras que aún no existan en la base de datos.

- `build_criteria()` (línea 23-38): el parámetro `barrio` pasa de string a lista; línea 34 cambia de
  `barrio=barrio.strip() if barrio.strip() else None`
  a
  `barrio=", ".join(barrio) if barrio else None`
  (mismo patrón que `amenidades`, línea 37).

- Consulta de zonas existentes: se envuelve en `@st.cache_data(ttl=...)` (patrón ya usado en la página para evitar recargar en cada rerun) para no golpear la base de datos en cada interacción del formulario.

- `format_criteria()` (`filter_matcher.py:193-194`) no necesita cambios: `f"Zona: {value}"` ya muestra correctamente el string con varias zonas separadas por comas.

---

## Fuera de alcance

- No se cambia cómo se puebla `Propiedad.barrio` (sigue siendo un único valor por propiedad).
- No se migra el histórico de alertas existentes (compatible sin cambios, ver punto 1).
- No se añade un vocabulario fijo de zonas; las sugerencias son puramente dinámicas desde los datos existentes.

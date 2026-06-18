# Galería de Fotos con Carrusel en Tarjetas de Propiedades

**Fecha:** 2026-06-18  
**Sprint:** 11  
**Estado:** Aprobado por usuario

---

## Objetivo

Añadir un botón 📸 en cada tarjeta de propiedad que abra un dialog con carrusel de fotos. Solo aparece si la propiedad tiene fotos (`prop.fotos` no vacío).

---

## Arquitectura

Único archivo modificado: `app/pages/2_propiedades.py`

- Nueva función `fotos_dialog(prop)` decorada con `@st.dialog`
- Layout de botones expandido de 5 a 6 columnas
- Botón 📸 condicional (solo renderizado si `prop.fotos`)

Sin nuevos archivos. Sin cambios de BD. Sin dependencias extra.

---

## `fotos_dialog(prop)`

```python
@st.dialog("📸 Fotos", width="large")
def fotos_dialog(prop):
    fotos = prop.fotos or []
    if not fotos:
        st.info("Esta propiedad no tiene fotos.")
        return

    key = f"foto_idx_{prop.id}"
    if key not in st.session_state:
        st.session_state[key] = 0

    idx = st.session_state[key]
    total = len(fotos)

    st.caption(f"Foto {idx + 1} de {total}")
    st.image(fotos[idx], use_container_width=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← Anterior", use_container_width=True):
            st.session_state[key] = (idx - 1) % total
            st.rerun()
    with col_next:
        if st.button("Siguiente →", use_container_width=True):
            st.session_state[key] = (idx + 1) % total
            st.rerun()
```

---

## Botón en tarjeta

El layout de botones pasa de `st.columns(5)` a `st.columns(6)`. El nuevo botón ocupa la posición 3 (entre 🧮 y 🔗):

| Col 1 | Col 2 | Col 3 | Col 4 | Col 5 | Col 6 |
|-------|-------|-------|-------|-------|-------|
| 👁 Visto | ✏️ | 🧮 | 📸 | 🔗 | ❌ |

El botón 📸 solo se renderiza si `prop.fotos`:

```python
with col4:
    if prop.fotos:
        if st.button("📸", key=f"fotos_{prop.id}", help="Ver fotos"):
            fotos_dialog(prop)
```

Si no hay fotos, la columna queda vacía.

---

## Comportamiento del carrusel

- Índice guardado en `st.session_state[f"foto_idx_{prop.id}"]`
- Inicializado a 0 la primera vez que se abre el dialog
- Botón ← : `(idx - 1) % total` — wrapping circular
- Botón → : `(idx + 1) % total` — wrapping circular
- `st.rerun()` tras cada cambio de índice para refrescar la imagen

---

## Fuera de alcance

- Descarga de fotos
- Zoom o lightbox
- Miniaturas / thumbnails
- Ordenación de fotos

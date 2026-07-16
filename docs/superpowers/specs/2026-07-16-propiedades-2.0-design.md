# Propiedades 2.0 — Diseño

**Fecha:** 2026-07-16
**Estado:** Aprobado por Sergio (pendiente de plan de implementación)

## Objetivo

Rediseñar la página de Propiedades (`app/pages/2_propiedades.py`) para resolver cuatro problemas de la versión actual: recargas completas en cada interacción, tarjetas poco visuales, filtros engorrosos en el sidebar y un flujo de triaje lento. El flujo principal del usuario es **triar novedades**: entrar, ver lo nuevo y decidir rápido (favorita / descartar).

**Restricciones:** Streamlit puro (sin dependencias nuevas ni componentes custom), compatible con Streamlit Cloud. Volumen pequeño (<500 propiedades, <10 novedades/día).

## 1. Estructura de la página

Desaparece el sidebar de filtros. De arriba a abajo:

1. **Cabecera**: título + botón "➕ Añadir URL".
2. **Pestañas por estado** con contador, implementadas con `st.segmented_control` (no `st.tabs`, que ejecutaría el contenido de todas las pestañas):
   - **🆕 Nuevas** (vista por defecto al entrar): `vista=False AND descartada=False AND activa=True`
   - **📋 Todas**: `activa=True AND descartada=False`
   - **❤️ Favoritas**: `favorita=True`
   - **❌ Descartadas**: `descartada=True`
   - **🚫 Vendidas**: `activa=False`
3. **Expander "🔍 Filtros"** (plegado por defecto).
4. **Barra de resultados**: selector de orden + número de resultados + chips de filtros activos.
5. **Grid de tarjetas** en 3 columnas, 12 por página.
6. **Paginación** con botones ← Anterior / Siguiente →.
7. **Expander "⚙️ Herramientas"** al final: descarte masivo y verificación de vendidas.

Las pestañas sustituyen a los checkboxes actuales "Ver vistas / descartadas / vendidas". Al triar una propiedad, la tarjeta no desaparece del grid inmediatamente (se evita el salto de layout); sale de "Nuevas" en la siguiente carga de la pestaña.

## 2. Tarjeta 2.0

Cada tarjeta se renderiza como un único bloque HTML/CSS vía `st.markdown` (en lugar de ~15 widgets), más una fila de botones de acción:

- **Foto de portada**: primera URL de `fotos`, proporción 16:9 (`object-fit: cover`); placeholder CSS si no hay fotos.
- **Precio** en grande. Si `precio_anterior > precio`, mostrar la bajada destacada en verde (p. ej. "↓ −6.000 €").
- **€/m²** calculado (`precio / superficie_m2`), mostrado siempre que existan ambos valores. Dato nuevo, clave para comparar.
- **Línea resumen**: tipo · m² · habitaciones · baños (omitir los campos NULL).
- **Ubicación**: 📍 barrio, municipio.
- **Chips de características**: solo las que son `True` (ascensor, garaje, trastero, terraza, balcón, patio, piscina, A/C, amueblado, mascotas).
- **Metadatos**: web de origen · antigüedad ("hoy" / "hace Nd") · badge "📌 Manual" si `fuente_id` es la fuente Manual.
- **Fila de acciones**: ❤️ favorita (toggle) · ❌ descartar (toggle) · ✏️ editar · 🧮 calculadora · 📸 fotos (si hay) · 🔗 abrir anuncio · 👁 visto (secundaria).

El expander "📖 Detalles" de la versión actual se elimina: lo esencial queda a la vista y el detalle completo vive en el modal de edición.

Las propiedades inactivas (vendidas) se muestran con título tachado y estado, como ahora.

## 3. Filtros

Un `st.form` dentro del expander "🔍 Filtros". Nada se aplica hasta pulsar **"Aplicar"**:

- Precio mín/máx (€), superficie mín (m²), habitaciones mín, baños mín.
- Tipo de propiedad y distrito: multiselect poblados con `SELECT DISTINCT` (como ahora).
- Características: un único multiselect de chips (Ascensor, Garaje, Terraza, Balcón, Piscina, A/C…) en lugar de checkboxes sueltos. Semántica AND: la propiedad debe tener todas las seleccionadas.
- Búsqueda de texto en título/descripción (`ILIKE`).
- Botón **"Limpiar"** que resetea el formulario y los filtros aplicados.

Semántica de NULL (igual que ahora): los filtros numéricos incluyen propiedades con el campo NULL (dato desconocido ≠ excluido). Los filtros de características booleanas exigen `True`.

Los filtros aplicados se guardan en `st.session_state` y se resumen en chips encima del grid (p. ej. `≤200.000 € · ≥3 hab · Terraza`).

## 4. Rendimiento e interacción

- **`@st.fragment` por tarjeta**: las acciones ❤️/❌/👁 re-ejecutan solo el fragment de esa tarjeta (una escritura a BD + re-render local). Es el cambio que hace el triaje instantáneo. Los modales (editar, calculadora, fotos) se abren desde dentro del fragment.
- **Consultas cacheadas**: una función `@st.cache_data(ttl=60)` devuelve la página de resultados como **dicts planos** (no objetos ORM ligados a una sesión), con clave de caché = (pestaña, filtros, orden, página). Los contadores de las pestañas salen de una única query agregada, también cacheada. Tras una acción de escritura se limpia la caché de esas funciones (`funcion.clear()`) para que resultados y contadores no mientan más de lo que dura el TTL.
- **Visto automático**: descartar o marcar favorita implica `vista=True`. Botón "✓ Visto todo" que marca como vistas las 12 propiedades de la página actual. El botón 👁 individual se mantiene como acción secundaria.
- Se mantiene el límite de 300 resultados por consulta y la ordenación actual (reciente/antiguo, precio asc/desc, m²).

## 5. Se conserva sin cambios funcionales

- Modales de **editar** (con historial de precios), **calculadora** y **fotos**.
- Diálogo **➕ Añadir URL** con extracción automática.
- **Descarte masivo** con confirmación en dos pasos y **verificar vendidas**, reubicados en el expander "⚙️ Herramientas". El descarte masivo opera sobre los filtros aplicados vigentes (misma query que el grid, sin paginación).

## 6. Estructura de código

| Archivo | Responsabilidad |
|---|---|
| `app/pages/2_propiedades.py` | Orquestación: pestañas, filtros, paginación, herramientas |
| `app/ui/property_card.py` | Render de tarjeta: HTML de la tarjeta + fragment de acciones |
| `app/ui/property_dialogs.py` | Modales existentes (editar, calculadora, fotos, añadir URL), movidos sin cambios |
| `app/ui/property_queries.py` | Construcción de queries, contadores y transformación a dicts; sin dependencia de Streamlit salvo el decorador de caché |

`app/ui/` es un paquete nuevo con `__init__.py`.

## 7. Manejo de errores

- Fallo de conexión a BD: mensaje de error como ahora (try/except global de la página).
- Fotos rotas (URL caída): el `<img>` HTML usa `onerror` para caer al placeholder.
- Acciones de escritura: cada handler envuelve la operación y muestra `st.error` en el fragment sin tumbar la página.

## 8. Tests

- Unitarios para `property_queries`: construcción de filtros por pestaña (Nuevas/Todas/Favoritas/…), semántica NULL de filtros numéricos, filtro AND de características, cálculo de €/m², contadores.
- Patrón y ubicación: `tests/test_property_queries.py`, siguiendo la convención existente (`pytest`, `asyncio_mode=auto` no aplica aquí).
- La UI se valida manualmente con `streamlit run app/main.py`.

## Fuera de alcance

- Modo "revisar una a una" (carrusel tipo Tinder) — posible extensión futura.
- Cambios en scrapers, alertas, u otras páginas.
- Mapa con `latitud`/`longitud`.

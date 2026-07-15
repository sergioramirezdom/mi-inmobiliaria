# Scraper Alonsaga — Rediseño (sitio rediseñado)

**Fecha:** 2026-07-15
**Estado:** Aprobado por usuario

---

## Objetivo

`alonsaga.com` fue rediseñado por completo desde que se implementó el scraper original (ver `docs/superpowers/specs/2026-06-20-alonsaga-scraper-design.md`). La fuente lleva devolviendo 0 propiedades nuevas de forma silenciosa porque cada punto de integración del scraper apunta a URLs/selectores que ya no existen.

Este documento diseña la reescritura necesaria para que la fuente vuelva a recopilar datos correctamente contra el HTML actual del sitio.

---

## Causa raíz (diagnóstico)

Verificado contra el sitio en vivo (listado, formulario de búsqueda y dos fichas de detalle reales):

1. **Listado (HTTP 404).** La URL configurada (`/buscador/en_venta/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/`) ya no existe. El buscador ahora es un formulario GET a `/buscar.php` con parámetros (`o`, `po[]`, `check_zona[]`). Como cada ejecución obtiene 0 URLs en la página 1 y 2, `PaginatedScraper` detiene la paginación de inmediato sin guardar nada ni lanzar error visible.
2. **Selector de tarjetas cambiado.** `div.cardAnuncio` ya no existe; el nuevo contenedor es `div.listado5_contendor_inmueble`.
3. **Ya no hace falta el fallback `data-path`.** Los enlaces de cada tarjeta son ahora `<a href="/Venta-...">` normales (dentro de un carrusel de fotos), no `data-path`.
4. **Formato de URL de detalle cambiado.** De `/detalle/en_venta/{tipo}/...` a `/Venta-{Tipo}-{Municipio}-{zona}-{id}`. `_extract_tipo_from_url` (regex `/en_venta/([^/]+)/`) ya no coincide nunca.
5. **Habitaciones/baños ya no son texto.** Antes "Habitaciones 3" / "Baños 1" en texto plano; ahora son iconos (`<i class="fas fa-bed">`, `<i class="fas fa-bath">`) con un `<span>` numérico contiguo, dentro de `div#inmueble2_caracteristicas`.
6. **Descripción movida.** `div.hidden` ya no existe; el texto está en `<p id="inmueble2_datos_adicionales">`.
7. **CDN de fotos cambiado.** De `fotoshs.imghs.net` a `inmoserver.com/fotos/{cliente}/wm/{id}_...`. El filtro actual no encuentra ninguna.

---

## Alcance

- Reescribir `app/scraper/alonsaga_scraper.py` para el nuevo HTML.
- Actualizar la config de la `Fuente` existente (`notas` JSON + `url`) en la app (`1_fuentes.py`), sin cambios de código en esa página.
- Actualizar `tests/test_alonsaga_scraper.py`.
- **Fuera de alcance:** hacer la zona configurable vía `Fuente.notas` (se mantiene zona fija en la URL, como el diseño original). Extracción de plazas de garaje/planta/ascensor desde iconos (se sigue delegando en `description_enricher`, ver más abajo).

---

## 1. Config de la Fuente

`fuente.url`:
```
https://www.alonsaga.com/buscar.php?o=Venta&po%5B%5D=po_El+Puerto+de+Santa+Mar%C3%ADa&check_zona%5B%5D=crevillet-pinar+alto
```

`fuente.notas` (JSON):
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

Notas:
- La zona "Pinar Alto / Crevillet / Menesteo" del diseño original se mapea a la única casilla de zona equivalente en el sitio nuevo: `crevillet-pinar alto` (el sitio fusionó las subzonas; no existe una opción "Menesteo" separada en el buscador actual).
- `pagination_param="pag"`, `pagination_start=1`, `pagination_skip_first=true`: página 1 usa la URL base (sin parámetro `pag`), página 2 añade `&pag=2`, página 3 `&pag=3`, etc. — confirmado contra el JS `cambiar_pagina()` del sitio.
- No se necesita CSS selector para `price`: la extracción de precio usa `patterns.price_pattern` (fallback por regex ya soportado por `GenericScraper._extract_field`) sobre el texto completo de la tarjeta.
- No se necesita CSS selector para `link`: el fallback existente de `GenericScraper` (regex `href=...` sobre el HTML de la tarjeta) ya encuentra el primer `<a href>` dentro del contenedor, que apunta a la ficha de detalle.
- **No se modifica `generic.py`.** El fallback `data-path` añadido para Alonsaga en el diseño original queda sin uso pero inofensivo (nadie más lo usa); no se retira por no ser parte del objetivo de esta tarea.

---

## 2. Reescritura de `AlonsagaScraper.scrape_property_details()`

| Campo | Antes (roto) | Ahora |
|---|---|---|
| `titulo` | `h1` + `re.sub` quitando prefijo `"Alonsaga X - "` | `h1` tal cual — se elimina el `re.sub` (código muerto: el nuevo `h1` no lleva ese prefijo) |
| `precio` | regex `([\d.]+(?:,\d+)?)\s*€` sobre texto de página | Sin cambios — verificado contra 2 fichas reales, el precio de venta siempre aparece antes que los desgloses de gastos de hipoteca en el texto de la página |
| `superficie_m2` | regex `([\d.,]+)\s*m²` sobre texto de página | Sin cambios |
| `habitaciones` | regex `[Hh]abitaciones?\s+(\d+)` (texto ya no existe) | `soup.select_one("#inmueble2_caracteristicas i.fa-bed")` → leer el `<span>` numérico siguiente (`find_next_sibling`) |
| `banos` | regex `[Bb]años?\s+(\d+)` (texto ya no existe) | Igual patrón con `i.fa-bath` |
| `tipo_propiedad` | regex `/en_venta/([^/]+)/` sobre path (formato de URL ya no existe) | regex `^/Venta-([A-Za-z]+)-` sobre el path de la URL de detalle → captura `Casa`, `Piso`, `Vivienda`, `Local`, `Nave`; se normaliza a minúsculas |
| `fotos` | filtro por dominio `fotoshs.imghs.net` (CDN antiguo, ya no aparece) | Filtro por `/wm/{id}_` en el `src`, donde `id` es el número final de la URL de detalle de la propiedad (evita fotos del carrusel de "inmuebles similares" más abajo en la misma página, que reutiliza las mismas clases CSS); se deduplica quitando el query string de compresión (`?auto=compress&cs=tinysrgb&...`) |
| `descripcion` | `soup.select_one("div.hidden")` (ya no existe) | `soup.select_one("p#inmueble2_datos_adicionales")` |
| `garaje` | no se extraía | Se mantiene sin extracción directa desde el detalle: el icono `fa-warehouse` junto al badge de habitaciones/baños no tiene un significado fiable como contador (en una ficha real marcaba "1" mientras el texto decía "garaje para 2 coches"). Se sigue delegando en `description_enricher` sobre `descripcion`, que ahora sí recibe el texto completo gracias al fix de arriba |
| Detección vendido/reservado (keywords) | texto de página en minúsculas | Sin cambios |
| HTTP 404 → `activa=False` | — | Sin cambios |
| Municipio fijo | `"El Puerto de Santa María"` | Sin cambios |

---

## 3. Tests

`tests/test_alonsaga_wiring.py`: sin cambios (el enrutado por `detail_scraper_type="alonsaga"` no se toca).

`tests/test_alonsaga_scraper.py`:
- `test_extract_tipo_*`: se actualizan las URLs de ejemplo al nuevo formato (`/Venta-Piso-El-Puerto-de-Santa-María-zona-123`) y el valor esperado se normaliza a minúsculas.
- `test_extract_fotos_*`: `_extract_fotos` cambia de firma — pasa a recibir el `id` de la propiedad y filtrar por `/wm/{id}_` en vez de por dominio; se añade un caso que verifica que fotos de otra propiedad (simulando el carrusel de "similares") quedan excluidas, y que las variantes con query string de compresión se deduplican.
- Tests nuevos: extracción de habitaciones/baños desde iconos (HTML de ejemplo reproduciendo `div#inmueble2_caracteristicas`) y extracción de descripción desde `p#inmueble2_datos_adicionales`.
- `test_generic_scraper_extracts_data_path_url`: sin cambios (sigue siendo válido, aunque Alonsaga ya no lo necesite).

Todos los tests siguen siendo unitarios sobre HTML fijo (sin llamadas HTTP reales), consistente con el resto del proyecto.

---

## Fuera de alcance

- Soporte de zona configurable vía `Fuente.notas` (se mantiene zona fija en la URL).
- Extracción de plazas de garaje, planta, ascensor, terraza desde iconos del detalle (delegado a `description_enricher`).
- Precio de alquiler (solo venta).

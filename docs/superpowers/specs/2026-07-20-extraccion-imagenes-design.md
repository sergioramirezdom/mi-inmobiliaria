# Extracción genérica de imágenes de propiedades

Fecha: 2026-07-20
Estado: aprobado, pendiente de implementación

## Problema

Solo 3 de los 8 scrapers extraen fotos: `alonsaga_scraper.py:164`,
`jimenezruiz_scraper.py:175` y `puertopiso_scraper.py:169`. Los otros cinco
(`mobilia`, `guadalete`, `punto_hogar`, `puerto_inmobiliaria`, `manual`) dejan
`Propiedad.fotos` vacío, así que sus propiedades no muestran ninguna imagen en
la UI.

Los tres extractores existentes usan heurísticas específicas del portal. El de
`alonsaga` filtra por un marcador `/wm/{property_id}_` precisamente para
excluir las fotos del widget de "propiedades similares" — conocimiento local
que no se puede generalizar.

## Alcance

- Un extractor genérico de imágenes a partir del HTML de una ficha.
- Un botón bajo demanda en la tarjeta de propiedad, con previsualización.
- Respaldo automático en los 5 scrapers que hoy no extraen fotos.

Fuera: backfill masivo del histórico (se resuelve propiedad a propiedad desde
la UI), y descarga o rehospedaje de las imágenes (se guardan las URLs, como
ahora).

## Decisiones de diseño

| Decisión | Elegido | Motivo |
|---|---|---|
| Extracción | Genérica con filtros de calidad | Un módulo cubre los 5 portales y los futuros; los específicos son 5× trabajo y mantenimiento |
| Ejecución | Botón bajo demanda en la ficha | Coincide con la petición original ("obtener de una propiedad las imágenes, si esta no tiene") |
| Scrapers | Sí, como respaldo | El extractor va a existir igualmente; aplicarlo sobre el HTML ya descargado es coste cero |
| Confirmación | Previsualizar y elegir | Única opción en la que el ruido inevitable del algoritmo nunca llega a la BD |

## Arquitectura

Módulo nuevo `app/scraper/foto_extractor.py`, con la misma división que
`url_extractor.py`:

```python
async def obtener_fotos(url: str) -> dict          # {"fotos": [...]} | {"error": "..."}
def extraer_fotos(html: str, url: str) -> list[str]  # PURA: sin HTTP
```

Que `extraer_fotos` sea pura es lo que permite testear el algoritmo con HTML
fijo, en vez de contra portales reales que cambian y volverían los tests
inestables.

### Algoritmo

1. **Recolectar candidatas** de `<img src>`, `<img data-src>` (carga diferida),
   `srcset`, y `<a href>` que apunte a una imagen — `puertopiso_scraper.py:169`
   demuestra que algunos portales cuelgan la foto grande del enlace, no del
   `img`. Resolver relativas a absolutas con `urljoin`.
2. **Descartar por formato**: `.svg`, `.gif`, `.ico`, y `data:` URIs.
3. **Descartar por ruta**: contiene `logo`, `banner`, `icon`, `avatar`,
   `sprite`, `placeholder`, `thumb`, `small`, `blank`. Y si el `<img>` trae
   atributos `width`/`height` explícitos menores de 300, descartar. Solo cuando
   los trae: conocer el tamaño real exigiría descargar cada imagen.
4. **Agrupar por carpeta** (URL sin el nombre de fichero) y quedarse con el
   grupo más numeroso. Las fotos de un anuncio viven juntas en el CDN; los
   adornos de la plantilla están dispersos.
5. **Deduplicar** quitando el query string (`?w=800` y `?w=1200` son la misma
   foto) y preservando el orden de aparición, que suele ser el de la galería.

Si no queda nada, **fallback a `og:image`** del `<head>`: una foto es mejor que
ninguna.

### Limitación conocida

El paso 4 no puede separar las fotos del anuncio de las del widget
"propiedades similares" cuando el portal las sirve desde la misma carpeta.
`alonsaga` lo resuelve con el ID de la propiedad, pero eso es específico suyo.

Esta limitación es la que justifica la previsualización: el ruido que el
algoritmo no puede evitar se filtra a mano en segundos y nunca llega a la BD.

## UI

**Botón.** En `property_card.py:118`, el hueco `b[4]` está libre cuando la
propiedad no tiene fotos:

```python
if p["fotos"]:
    if b[4].button("📸", ...):   # ver fotos     (ya existe)
else:
    if b[4].button("🔍", ...):   # buscar fotos  (nuevo)
```

Sin columnas nuevas. `render_card` ya es `@st.fragment`, así que al pulsar solo
se re-ejecuta esa tarjeta.

**Modal** `buscar_fotos_dialog(prop, on_write)` en `property_dialogs.py`:

1. `asyncio.run(obtener_fotos(prop.url_original))` con `st.spinner` — patrón de
   `property_dialogs.py:64`.
2. `error` → `st.error` y salir.
3. Lista vacía → `st.warning("No se encontraron imágenes")` y salir.
4. Menos de 5 → aviso visible: señal de que la extracción falló en ese portal.
5. Miniaturas en rejilla de 4 columnas, cada una con `st.checkbox` marcado por
   defecto.
6. `💾 Guardar N fotos` → `PropiedadCRUD.update(session, prop.id, fotos=...)`.

## Wiring en scrapers

Los 5 scrapers comparten la firma `scrape_property_details(url) -> dict` y cada
uno construye su `soup` internamente; no hay implementación común en `base.py`.
El respaldo va en cada uno, justo antes del `return`:

```python
if not data.get("fotos"):
    fotos = extraer_fotos(html, url)
    if fotos:
        data["fotos"] = fotos
```

Solo actúa como respaldo: `alonsaga`, `jimenezruiz` y `puertopiso` conservan sus
extractores específicos, más precisos.

`manual_scraper` hay que revisarlo antes: no aparece que construya un `soup`, así
que puede que no descargue HTML y no aplique.

## Testing

- **`test_foto_extractor.py`** — algoritmo con HTML fijo: galería normal;
  descarte de `.svg`/`.gif`; descarte de `logo`/`thumb`; `data-src`; fotos en
  `<a href>`; relativas → absolutas; dedup de `?w=800` vs `?w=1200`; desempate
  por carpeta más numerosa; fallback a `og:image`; HTML vacío.
- **`test_foto_extractor_wiring.py`** — cada scraper modificado rellena `fotos`
  cuando su extractor propio no dio nada, y **no** las pisa cuando sí dio.
  Reutiliza el mocking de `httpx` de `test_zona_wiring.py`.

No hay tests de red para `obtener_fotos`: es un envoltorio fino sobre `httpx`,
igual que `extract_from_url`, que tampoco los tiene.

## Orden de ejecución

1. Extractor puro + tests (no toca nada existente)
2. Modal y botón en la UI
3. Wiring de respaldo en los 5 scrapers

Cada paso deja la app funcionando.

## Fuera de alcance

- Backfill masivo del histórico
- Descargar o rehospedar las imágenes (se guardan URLs)
- Reescribir los 3 extractores específicos existentes
- Las otras funcionalidades pedidas (normalización de zonas — ya tiene spec —,
  y penotariado.com)

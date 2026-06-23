# Extracción de Zona — Diseño

**Fecha:** 2026-06-23
**Sprint:** 13
**Estado:** Aprobado por usuario

---

## Objetivo

Asegurar que el campo `barrio` (zona/barrio de la propiedad) se extrae correctamente en todos los scrapers del sistema, con una cobertura objetivo >85% de propiedades.

---

## Estado actual

| Scraper | Estado | Problema |
|---|---|---|
| puerto_inmobiliaria | A verificar | Label "Zone / City" en ficha HTML |
| mobilia | A verificar | Label "zona" en `div.IDPropiedadBig` |
| jimenezruiz | Frágil | Solo extrae de URL; sin fallback HTML |
| puertopiso | Roto | Regex "Zona:" no existe en la página |
| punto_hogar | No implementado | Sin lógica de zona |
| guadalete | No implementado | Sin lógica de zona |
| alonsaga | No implementado | Sin lógica de zona |
| url_extractor | No implementado | Sin lógica de zona |

---

## Arquitectura

### Nuevo módulo: `app/scraper/zona_utils.py`

Dos funciones públicas reutilizables por todos los scrapers:

#### `extract_from_url(url: str) -> Optional[str]`

Analiza los segmentos del path de la URL buscando una zona después de un slug de municipio conocido. Limpia el resultado reemplazando `_` y `-` por espacios y aplicando title case.

Slugs de municipio a ignorar (no son zonas):
```python
MUNICIPIO_SLUGS = {
    "el_puerto_de_santa_maria", "el-puerto-de-santa-maria",
    "cadiz", "puerto_de_santa_maria", "puerto-de-santa-maria",
    "san_fernando", "jerez_de_la_frontera", "rota", "chipiona",
}
```

Slugs de segmento no-zona a ignorar:
```python
SKIP_SEGMENTS = {
    "en_venta", "en_alquiler", "venta", "alquiler",
    "piso", "chalet", "casa", "local", "garaje", "terreno",
    "apartamento", "duplex", "atico", "finca", "oficina",
    "detalle", "buscador", "inmuebles", "cadiz",
}
```

Ejemplo: `/detalle/en_venta/piso/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/64234783889.265000/`
→ segmento `pinar_alto_crevillet_menesteo` → `"Pinar Alto Crevillet Menesteo"`

Descarta segmentos que son IDs numéricos o alfanuméricos largos (ej. `64234783889.265000`).

#### `extract_from_html(page_text: str, soup=None) -> Optional[str]`

Aplica patrones regex sobre el texto plano de la página por orden de prioridad:

```python
PATTERNS = [
    # Etiqueta explícita
    r"Zona[:\s]+([A-ZÁÉÍÓÚÑ][^\n,<]{2,50})",
    r"Barrio[:\s]+([A-ZÁÉÍÓÚÑ][^\n,<]{2,50})",
    # Título tipo "Piso en {zona} - {municipio}" (puertopiso)
    r"\ben ([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]+?) -\s*(?:El Puerto|Jerez|Cádiz|Rota|San Fernando)",
    # En prosa
    r"zona de ([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,40}?)[\.,]",
    r"barrio (?:de )?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,40}?)[\.,]",
]
```

Si `soup` se proporciona, también busca en `<h1>` y `<title>` con el patrón de título antes de page_text.

Devuelve el primer resultado limpio (strip, max 60 chars), o `None`.

---

## Cambios por scraper

### Scrapers a verificar primero (pueden ya funcionar)

Antes de modificarlos, ejecutar una prueba con una URL real y comprobar si `data["barrio"]` tiene valor:
- `puerto_inmobiliaria.py`
- `mobilia_scraper.py`

Si el campo llega vacío, añadirles el fallback igual que al resto.

### Scrapers a modificar

Todos añaden al final de `scrape_property_details`, justo antes de `return data`:

```python
from .zona_utils import extract_from_url, extract_from_html

if not data.get("barrio"):
    data["barrio"] = extract_from_url(url) or extract_from_html(page_text, soup)
```

Scrapers afectados: `puertopiso_scraper.py`, `punto_hogar_scraper.py`, `guadalete_scraper.py`, `alonsaga_scraper.py`, `jimenezruiz_scraper.py`, `url_extractor.py`.

**Nota sobre alonsaga:** La URL ya contiene la zona (`/pinar_alto_crevillet_menesteo/`), por lo que `extract_from_url` cubrirá ~100% de sus propiedades.

**Nota sobre puertopiso:** La zona aparece en el título de página con el patrón `"en {zona} - {municipio}"`. El patrón de título en `extract_from_html` cubre este caso.

**Nota sobre jimenezruiz:** Ya extrae barrio de URL pero sin fallback HTML. Con el nuevo bloque, si la URL no da resultado (barrio vacío o None), intentará el HTML.

---

## Cambio en `description_enricher.py`

Actualmente el enricher extrae `barrio` de la descripción y lo envía a la cola de revisión manual (página 5_revisión). Cambio: **auto-aplicar** `barrio` directamente a la BD cuando se detecta, sin pasar por revisión.

Esto aplica solo a `barrio`. Los demás campos (ascensor, garaje, terraza, etc.) siguen requiriendo revisión manual.

El campo se aplica solo si `prop.barrio` está vacío en la BD (no sobreescribe extracciones del scraper).

---

## Archivos

| Acción | Archivo |
|---|---|
| Crear | `app/scraper/zona_utils.py` |
| Crear | `tests/test_zona_utils.py` |
| Modificar | `app/scraper/puertopiso_scraper.py` |
| Modificar | `app/scraper/punto_hogar_scraper.py` |
| Modificar | `app/scraper/guadalete_scraper.py` |
| Modificar | `app/scraper/alonsaga_scraper.py` |
| Modificar | `app/scraper/jimenezruiz_scraper.py` |
| Modificar | `app/scraper/url_extractor.py` |
| Modificar | `app/scraper/description_enricher.py` |
| Verificar/modificar | `app/scraper/puerto_inmobiliaria.py` |
| Verificar/modificar | `app/scraper/mobilia_scraper.py` |

---

## Fuera de alcance

- Campo `distrito`: no se aborda en este sprint (está vacío en todos los scrapers; `barrio` es el campo prioritario)
- Filtro por barrio en UI (2_propiedades.py): el campo ya se muestra en tarjetas; añadir filtro es trabajo separado
- Geocoding automático (lat/lng desde zona): fuera de alcance

# Scraper Alonsaga — Diseño

**Fecha:** 2026-06-20  
**Sprint:** 12  
**Estado:** Aprobado por usuario

---

## Objetivo

Añadir `alonsaga.com` como nueva fuente de scraping al sistema inmobiliario. La fuente cubre la zona Pinar Alto / Crevillet / Menesteo de El Puerto de Santa María.

URL de partida: `https://www.alonsaga.com/buscador/en_venta/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/`

---

## Arquitectura

Mismo patrón que el resto de scrapers (GuadaleteScraper, PuntoHogarScraper, etc.):

- `AlonsagaScraper` maneja páginas de detalle individuales
- `GenericScraper` + `PaginatedScraper` manejan el listado y paginación
- La configuración de la fuente se almacena como JSON en `Fuente.notas`

Un cambio menor en `generic.py`: añadir fallback `data-path` en extracción de URLs, ya que alonsaga.com usa el atributo `data-path` en los divs de tarjeta (no `<a href>` estándar).

---

## Archivos

| Acción | Archivo |
|--------|---------|
| Crear | `app/scraper/alonsaga_scraper.py` |
| Modificar | `app/scraper/generic.py` |
| Modificar | `app/pages/1_fuentes.py` |
| Modificar | `app/scraper/sold_checker.py` |
| Modificar | `app/scraper/paginated_scraper.py` |

---

## `AlonsagaScraper`

```python
class AlonsagaScraper:
    def __init__(self, config: ScraperConfig = None): ...
    async def scrape_property_details(self, url: str) -> Dict[str, Any]: ...
```

### Comportamiento de detalle

- GET a la URL con headers de navegador (mismo patrón que GuadaleteScraper)
- HTTP 404 → `{"activa": False, "estado": "No disponible"}`
- Texto de página en minúsculas → buscar keywords: "vendido", "vendida", "reservado", "reservada" → `{"activa": False, "estado": keyword.capitalize()}`
- Campos extraídos:

| Campo | Método |
|-------|--------|
| `titulo` | `soup.find("h1").get_text()` |
| `precio` | regex `([\d.]+)\s*€` sobre texto de página (europeo: `.` = miles) |
| `superficie_m2` | regex `(\d+)\s*m²` |
| `habitaciones` | regex `(\d+)\s*[Hh]abitaciones?` |
| `banos` | regex `(\d+)\s*[Bb]años?` |
| `tipo_propiedad` | extraído del path URL: `/detalle/en_venta/{tipo}/` |
| `municipio` | `"El Puerto de Santa María"` (hardcoded) |
| `fotos` | lista de `img[src]` que contienen `fotoshs.imghs.net` |
| `descripcion` | primer `<div>` o `<p>` con texto > 150 chars sin hijos de bloque |

---

## Cambio en `generic.py`

En `_extract_field(element, "link")`, añadir fallback después de `onclick`:

```python
# Try data-path attribute (used by alonsaga.com and similar JS-navigated sites)
data_path_match = re.search(r'data-path=["\']([^"\']+)["\']', element_html)
if data_path_match:
    return self._resolve_url(data_path_match.group(1))
```

---

## Config JSON para la fuente

El usuario crea la fuente en `1_fuentes.py` con estos valores:

- **Nombre:** `Alonsaga`
- **URL:** `https://www.alonsaga.com/buscador/en_venta/cadiz/el_puerto_de_santa_maria/pinar_alto_crevillet_menesteo/`
- **Notas (JSON):**

```json
{
  "detail_scraper_type": "alonsaga",
  "selectors": {
    "property_container": "div.cardAnuncio",
    "title": "span.titulo",
    "price": "div.precio"
  },
  "pagination_param": "Pagina",
  "pagination_start": 0,
  "pagination_skip_first": true,
  "use_results_per_page": false
}
```

Paginación: página 1 usa URL base sin parámetro, páginas siguientes añaden `?Pagina=N` (N empieza en 1).

---

## Sold checker

En `sold_checker.py`, dentro de `_get_scraper()`:

```python
elif detail_type == "alonsaga":
    from .alonsaga_scraper import AlonsagaScraper
    return AlonsagaScraper(config)
```

---

## Paginated scraper

En `paginated_scraper.py`, dentro de `_init_detail_scraper()`:

```python
elif detail_type == "alonsaga":
    from .alonsaga_scraper import AlonsagaScraper
    self.detail_scraper = AlonsagaScraper(fuente_config)
```

---

## Fuera de alcance

- Soporte multi-zona (la fuente cubre una sola zona, el usuario puede crear varias fuentes si quiere más zonas)
- Extracción de planta, ascensor, garaje, terraza desde detalle (se delega al `description_enricher` existente)
- Precio de alquiler (solo venta)

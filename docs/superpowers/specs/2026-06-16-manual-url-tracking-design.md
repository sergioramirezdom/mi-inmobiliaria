# Seguimiento Manual de URLs Individuales

**Fecha:** 2026-06-16  
**Sprint:** 10  
**Estado:** Aprobado por usuario

---

## Objetivo

Permitir añadir propiedades individuales de cualquier agencia pequeña (mbfinca, etc.) pegando una URL. La app extrae los datos básicos, el usuario completa lo que falta en un formulario, y el scheduler monitoriza la propiedad igual que el resto (bajadas de precio, vendidas).

---

## Arquitectura

```
app/
├── scraper/
│   ├── url_extractor.py      # nuevo — extracción genérica de una URL individual
│   └── manual_scraper.py     # nuevo — monitorización de propiedades manuales
├── pages/
│   └── 2_propiedades.py      # modificar — botón + diálogo "Añadir URL"
└── scraper/
    ├── sold_checker.py       # modificar — añadir rama "manual_auto"
    └── paginated_scraper.py  # modificar — añadir rama "manual_auto" por consistencia
```

Sin cambios de esquema en BD. Sin migraciones.

---

## Fuente "Manual"

Se crea automáticamente la primera vez que el usuario añade una propiedad manual si no existe:

```python
Fuente(
    nombre="Manual",
    url="manual://manual",
    tipo_scraper="generic",
    activa=False,        # excluida del scraping masivo (scheduler filtra activa=True)
    intervalo_horas=24,
    notas='{"detail_scraper_type": "manual_auto"}',
)
```

Todas las propiedades manuales usan `fuente_id` de esta fuente. El scheduler omite fuentes con `activa=False`, por lo que nunca intenta paginar esta fuente. El `sold_checker` sí la encuentra porque consulta todas las fuentes sin filtro por `activa`.

---

## `url_extractor.py`

Función pura `extract_from_url(url: str) -> dict`. Hace una sola petición HTTP con headers de navegador y extrae en orden de prioridad:

### Precio (campo prioritario)
1. Meta tags: `og:price:amount`, `product:price:amount`, `price`
2. Regex en texto de página: `r"([\d.,]+)\s*€"` — primer match que resulte en valor > 10.000

### Título
1. Meta tag `og:title`
2. Primer `<h1>`

### Superficie (m²)
- Regex: `r"(\d[\d.,]*)\s*m[²2]"` — primer match razonable (< 2000)

### Habitaciones
- Regex: `r"(\d+)\s*(?:hab|dormitor|dorm)"` — case insensitive

### Baños
- Regex: `r"(\d+)\s*ba[ñn]"` — case insensitive

### Municipio
- Meta tag `og:locality` o similar
- Fallback: vacío (el usuario lo rellena)

### Manejo de errores
- Timeout: 15s
- Si la petición falla (timeout, conexión rechazada, SSL): devuelve `{}` con mensaje de error
- Si devuelve 404: devuelve `{"error": "URL no encontrada (404)"}`
- No lanza excepciones — siempre devuelve dict

---

## `manual_scraper.py`

Clase `ManualScraper` usada por `sold_checker` para propiedades con `detail_scraper_type="manual_auto"`.

```python
async def scrape_property_details(self, url: str) -> Dict[str, Any]:
    # Devuelve dict con al menos: activa, precio (si extraído)
```

| Resultado | Acción |
|-----------|--------|
| HTTP 404 | `activa=False`, `estado="No disponible"` |
| Excepción con "404" o "Not Found" | `activa=False`, `estado="No disponible"` |
| HTTP 200 + keyword vendido/reservado en primeros 3000 chars | `activa=False`, `estado="Vendida"` |
| HTTP 200 + precio extraído | Devuelve `activa=True`, `precio=<valor>` |
| HTTP 200 + sin precio | Devuelve `activa=True`, sin precio (no marca como vendida) |
| Otros errores HTTP / timeout | Devuelve `activa=True` (duda → no tocar) |

Reutiliza la lógica de extracción de precio de `url_extractor.py`.

---

## UI — Diálogo en `2_propiedades.py`

**Punto de entrada:** botón **"➕ Añadir URL"** en el sidebar, encima de los filtros.

**Diálogo:** `@st.dialog("➕ Añadir propiedad por URL", width="large")`

### Flujo

**Paso 1 — Introducir URL:**
```
URL de la propiedad:
[ https://mbfinca.com/inmueble/magnifico-piso...  ]
                                        [🔍 Extraer datos]
```

Al pulsar "Extraer datos": llama a `extract_from_url(url)`, muestra spinner, pre-rellena el formulario.

**Paso 2 — Formulario pre-rellenado:**

| Campo | Obligatorio | Default |
|-------|-------------|---------|
| Título | No | extraído o vacío |
| Precio (€) | **Sí** | extraído o vacío (resaltado si falta) |
| Superficie m² | No | extraído o vacío |
| Habitaciones | No | extraído o vacío |
| Baños | No | extraído o vacío |
| Municipio | No | extraído o "El Puerto de Santa María" |
| Tipo de propiedad | No | selector: piso/casa/chalet/otro |
| Notas | No | texto libre |

El botón "Guardar" está deshabilitado si `precio` está vacío o es 0.

### Badge en tarjeta

Las propiedades manuales muestran un badge **"📌 Manual"** junto al título en `render_property_card`. Condición: `prop.fuente_id == id_fuente_manual`.

### Guardado

```python
propiedad = Propiedad(
    hash_unico=sha256(url),
    url_original=url,
    fuente_id=<id fuente Manual>,
    origen_web=urlparse(url).netloc,  # e.g. "mbfinca.com"
    titulo=titulo,
    precio=precio,
    # ... resto de campos del formulario
    activa=True,
    fecha_scraping=datetime.utcnow(),
)
# + PrecioHistorico inicial
```

---

## Monitorización

El `sold_checker` existente ya itera todas las propiedades activas. Se añade la rama:

```python
elif detail_type == "manual_auto":
    return ManualScraper(config)
```

Y el `paginated_scraper.py` también recibe la misma rama por consistencia (aunque las propiedades manuales no pasan por el flujo de paginación).

**Notificaciones Telegram:** las propiedades manuales se benefician del sistema existente — bajadas de precio y vendidas se notifican igual que el resto.

**Scheduler:** el cron diario `sold_check.yml` ya cubre todas las propiedades activas sin cambios.

---

## Fuera de alcance

- Scraping masivo de páginas de listado de portales manuales
- Importación por CSV o lote de URLs
- Detección automática del portal para aplicar reglas específicas por dominio
- Portales que bloquean scrapers (Idealista, Fotocasa, Milanuncios)

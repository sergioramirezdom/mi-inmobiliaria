# Normalización de zonas (El Puerto de Santa María)

Fecha: 2026-07-20
Estado: aprobado, pendiente de implementación

## Problema

`Propiedad.barrio` contiene texto crudo tal cual lo publica cada portal. La misma
zona aparece escrita de formas distintas según la fuente y el anuncio:
`"Pinar Alto"`, `"El Pinar Alto"`, `"pinar alto"`, o directamente una vía que
pertenece a la zona (`"Avda. de Sevilla, 12"`).

Consecuencias actuales:

- **Estadísticas.** `market_stats.agregados_por_barrio` agrupa por el valor
  crudo, así que una misma zona se reparte en varias filas y ninguna alcanza
  `MIN_ACTIVAS_BARRIO`; acaban cayendo en `OTROS`.
- **Alertas.** `filter_matcher` compara por substring en minúsculas
  (`filter_matcher.py:97`). Un filtro por `"Crevillet"` no captura una propiedad
  cuyo `barrio` es `"Avda. de Sevilla"`, aunque sea la misma zona.
- **Histórico.** Muchas propiedades del inicio del proyecto tienen `barrio`
  vacío o incorrecto.

Hay además tres caminos independientes que producen `barrio`
(`zona_utils.extract_from_url`, `zona_utils.extract_from_html`,
`description_enricher.extract_barrio_from_text`) y ninguno normaliza.

## Alcance

Todos los barrios de El Puerto de Santa María. Otros municipios quedan fuera:
sus valores conservan `barrio` crudo y `zona_normalizada` a `NULL`.

## Decisiones de diseño

| Decisión | Elegido | Motivo |
|---|---|---|
| Almacenamiento | Columna nueva `zona_normalizada` | `barrio` conserva el crudo; un mapeo erróneo es reversible sin re-scrapear |
| Catálogo | YAML versionado | Revisable en git, testeable sin BD, añadir alias = commit de una línea |
| Backfill | Auto si match exacto, revisión el resto | Equilibra volumen y control |
| Matching | Alias explícitos, sin fuzzy | Con ~30 barrios el fuzzy genera falsos positivos ("Pinar Hondo" → "Pinar Alto") |

## Arquitectura

Módulo nuevo `app/scraper/zona_normalizer.py` como único punto donde se decide
la zona canónica. Los tres extractores actuales no desaparecen: siguen
produciendo el `barrio` crudo y ahora además alimentan al normalizador.

```
url ─┐
html ├─> barrio (crudo, se guarda tal cual)
desc ┘        │
              v
     zona_normalizer.normalizar(barrio, url, titulo, descripcion, direccion)
              │
              v
     ZonaMatch(zona: str|None, confianza: str, evidencia: str)
              │
              ├─ exacta ──> zona_normalizada
              └─ resto ───> sugerencia en Revisión
```

El normalizador no toca BD ni red: entra texto, sale un `ZonaMatch`. Testeable
sin Postgres, igual que `zona_utils` hoy. El catálogo se carga una vez y se
cachea a nivel de módulo.

### Cascada de resolución

En orden, parando en el primer acierto:

1. **Alias exacto** sobre `barrio` limpio → confianza `exacta`
2. **Vía conocida** (`vias:`) buscada en `barrio` y `direccion` → confianza `via`
3. **Alias o vía en `titulo` + `descripcion`** → confianza `debil`
4. Nada → `zona=None`, `confianza=None`

### Limpieza previa al match

Minúsculas, sin acentos, sin puntuación, espacios colapsados, y
`avda.`/`avda`/`avd`/`av.`/`av` → `avenida`.

### Formato del catálogo

`app/scraper/zonas_elpuerto.yaml`:

```yaml
Crevillet:
  alias: [crevillet, el crevillet, crevillet-pinar]
  vias:  [avenida de sevilla, avda sevilla]
Pinar Alto:
  alias: [pinar alto, el pinar alto, pinaralto]
  vias:  [avenida del pinar]
```

La clave es el nombre canónico. `alias` y `vias` van siempre en minúsculas y ya
limpios.

## Modelo de datos

Dos campos nuevos en `Propiedad`:

```python
zona_normalizada: Optional[str] = Field(default=None, index=True)
zona_confianza: Optional[str] = None   # 'exacta' | 'via' | 'debil'
```

`zona_confianza` permite a Revisión distinguir lo que decidió el catálogo de lo
que se adivinó de la descripción, y hace auditable un backfill de cientos de
filas. Sin él, un mapeo malo es indistinguible de uno bueno.

El proyecto no usa Alembic y `create_all` no añade columnas a tablas
existentes → migración explícita en `scripts/migrate_zona_normalizada.py`:
`ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`. Idempotente. Columnas
nullable sin default → Postgres no reescribe la tabla.

## Puntos de integración

| Dónde | Cambio |
|---|---|
| `app/scraper/base.py:226` | tras fijar `barrio`, llamar al normalizador y rellenar los dos campos |
| `app/pages/4_estadisticas.py:37` | `"barrio": p.zona_normalizada or p.barrio` |
| `app/notifications/filter_matcher.py:97` | regla OR (ver abajo) |
| `app/pages/5_revision.py` | sección nueva de sugerencias de zona |

`market_stats.py` **no se toca**: consume un DataFrame, no la BD. Toda la capa de
estadísticas se adapta con la línea de `4_estadisticas.py:37`.

### Alertas: compatibilidad

Cambiar a comparación exacta contra `zona_normalizada` rompería los filtros
guardados en el momento del deploy (un filtro `barrio: "pinar"` casaba por
substring y dejaría de casar), y las propiedades con zona `NULL` dejarían de
notificar del todo.

Regla adoptada — el criterio `barrio` casa si:

- **(a)** alguna zona pedida coincide exactamente con `zona_normalizada`, **o**
- **(b)** alguna zona pedida es substring de `barrio` (comportamiento actual)

Es OR: sólo puede añadir matches, nunca quitarlos. Ningún filtro existente se
rompe.

En la UI de alertas, el selector de zona ofrece el catálogo canónico como
opciones en lugar de texto libre.

## Backfill

El riesgo principal no es el código, es el contenido del YAML. Un catálogo
inventado produce mapeos silenciosamente erróneos, que es el fallo más caro:
contamina las estadísticas sin dar error. El catálogo se construye desde los
datos reales.

**`scripts/dump_zonas.py`** (solo lectura). Vuelca a CSV los valores distintos
de `barrio` con frecuencia, más los segmentos de zona de las URLs. Su salida es
lo que convierte el catálogo en un ejercicio de agrupar lo existente.
**Checkpoint humano**: los agrupamientos se validan con el usuario antes de
seguir.

**`scripts/backfill_zonas.py`**. `--dry-run` por defecto: imprime el reparto
(`exacta / via / debil / sin match`) sin escribir. Con `--apply` escribe, y sólo
los matches `exacta`. `via` y `debil` quedan como sugerencias en Revisión.
Reejecutable sin duplicar; como `barrio` nunca se toca, se puede relanzar tras
ampliar el YAML.

## Testing

Siguiendo el patrón existente (`test_zona_utils.py` + `test_zona_wiring.py`):

- **`test_zona_normalizer.py`** — cascada con catálogo de prueba pequeño (no el
  real): alias exacto, vía, texto libre, sin match, y la limpieza. Incluye el
  caso negativo que justifica no usar fuzzy: `"Pinar Hondo"` no resuelve a
  `"Pinar Alto"`.
- **`test_zona_normalizer_catalogo.py`** — valida el YAML real: sin alias
  duplicado en dos zonas (ambigüedad silenciosa), sin zonas vacías, todo en
  minúsculas. Evita que el catálogo se degrade con el tiempo.
- **`test_zona_wiring.py`** (ampliar) — `base.normalize` rellena los campos nuevos.
- **`test_filter_matcher_barrio.py`** (ampliar) — regla OR: casa por canónica,
  casa por substring legacy, y un filtro antiguo sigue disparando.

## Orden de ejecución

1. Migración de esquema (inocua por sí sola)
2. `zona_normalizer.py` + catálogo de prueba + tests → verde sin tocar nada existente
3. `dump_zonas.py` → **checkpoint humano** para construir el YAML real
4. Wiring: `base.py`, estadísticas, `filter_matcher`, Revisión
5. `backfill_zonas.py` dry-run → revisión del reparto → `--apply`

Los pasos 1-2 y 4-5 son ejecutables sin ambigüedad. El 3 requiere criterio del
usuario.

## Fuera de alcance

- Otros municipios distintos de El Puerto de Santa María
- Fuzzy matching / distancia de edición
- Geocodificación por coordenadas (`latitud`/`longitud` existen pero están casi
  siempre vacías)
- Las otras dos funcionalidades pedidas (obtención de imágenes, datos de
  penotariado.com) — cada una tendrá su propia spec

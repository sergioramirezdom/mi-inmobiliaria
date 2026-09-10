# Añadir una zona a la ingesta de penotariado (price-avg)

Guía para incorporar una nueva zona (barrio / polígono) al proceso semanal
que consulta el precio medio €/m² del endpoint público de penotariado.

Contexto: la feature está en `app/scraper/notariado_zonas.py` (registro +
loader), `scripts/fetch_notariado_zonas.py` (ingesta) y
`.github/workflows/notariado_zonas.yml` (cron semanal, lunes 07:00 UTC).
Añadir una zona **solo toca datos + registro + tests**: no cambia el modelo,
el cliente, el script ni el workflow.

---

## 1. Capturar el polígono

1. Abre el mapa de penotariado y dibuja / selecciona la zona.
2. En las DevTools del navegador, captura el `POST` a
   `https://penotariado.com/inmobiliario/rest/v1/public/price-avg`.
3. Copia el **payload** completo. Tiene esta forma:

   ```json
   {"geometry": {"spatialReference": {...}, "rings": [[[x, y], ...]]}, "where": "..."}
   ```

Solo interesa el objeto `geometry`. El campo `where` es ruido de la sesión
del navegador — la ingesta genera sus propios 4 combos y lo ignora.

## 2. Crear el archivo JSON

Ruta: `app/scraper/notariado_zonas/<slug>.json`

- `<slug>`: minúsculas, `snake_case`, sin acentos ni espacios.
  Ej.: `Soto Vistahermosa - Camaleón` → `soto_vistahermosa_camaleon`.
- Contenido: **solo el objeto `geometry` interno**, sin el envoltorio
  `{"geometry": ...}` y sin `where`:

  ```json
  {"spatialReference": {"latestWkid": 3857, "wkid": 102100}, "rings": [[[x, y], ...]]}
  ```

- JSON en una sola línea, igual que los archivos existentes
  (`crevillet.json`, `pinar_alto.json`, ...).
- Coordenadas verbatim, en **EPSG:3857**. No reproyectar ni simplificar.
- Un polígono con hueco lleva **varios anillos** en `rings` (ej.:
  `pago_alhaja.json` tiene 2). Se conservan todos tal cual.

> El directorio `notariado_zonas/` **no debe tener `__init__.py`**: si se
> convierte en paquete, tapa al módulo hermano `notariado_zonas.py`.

## 3. Registrar el slug

En `app/scraper/notariado_zonas.py`, añade el slug a `ZONA_SLUGS`:

```python
ZONA_SLUGS: list[str] = [
    "crevillet",
    "pinar_alto",
    "pago_alhaja",
    "soto_vistahermosa_camaleon",
    "<nuevo_slug>",
]
```

El registro es una lista explícita a propósito (nunca `glob` del
directorio), para que un archivo suelto no entre en una ejecución.

## 4. Actualizar los tests (TDD estricto)

Runner: `.venv/bin/python -m pytest -q`

En `tests/test_notariado_zonas_loader.py`:

- Añade el slug a la lista de `@pytest.mark.parametrize` de
  `test_every_registered_zona_loads_a_real_geometry`.
- Si la geometría tiene varios anillos, añade un test equivalente a
  `test_pago_alhaja_geometry_keeps_both_rings`.

`tests/test_fetch_notariado_zonas.py` **no se toca**: su fixture
`stub_geometry` fija `ZONA_SLUGS` a `["crevillet"]`, así que los tests de
ingesta son independientes del tamaño del registro.

## 5. Verificar la geometría en vivo (antes de commitear)

```bash
python3 - <<'PY'
import json, httpx
geom = json.load(open("app/scraper/notariado_zonas/<nuevo_slug>.json"))
url = "https://penotariado.com/inmobiliario/rest/v1/public/price-avg"
r = httpx.post(url, json={"geometry": geom, "where": "1=1"}, timeout=40)
print(r.status_code, r.text[:200])
PY
```

Esperado: `200 {"data":{"priceAvg": <int>}}`.
Si `1=1` devuelve `400` con `errorType "PAV002"`, el polígono está mal
(sin datos en toda el área) — revísalo antes de seguir.

Nota: en los 4 combos reales sí es normal ver `PAV002` en algunos
(`piso/casa` × `obra_nueva/segunda_mano`); solo significa "sin datos
suficientes" y la ingesta lo guarda como fila con `sin_datos = true`.

## 6. Suite completa, commit y PR

```bash
.venv/bin/python -m pytest -q
```

Baseline conocido: 5 fallos preexistentes en `tests/test_scraper_config.py`
(timeout 120 vs 30), ajenos a esto. Que no haya **fallos nuevos**.

- Rama desde `master`, ej.: `feat/notariado-zonas-add-<slug>`.
- Commit convencional, ej.:
  `feat(notariado): add <slug> zona`.
- **Sin atribución de IA** en el commit ni en el cuerpo del PR.
- Se pueden meter varias zonas en el mismo PR.

## 7. Primera lectura (opcional)

La nueva zona entra sola en el cron del lunes. Para tener datos hoy:

```bash
gh workflow run notariado_zonas.yml --ref master
gh run watch
```

Corre contra Neon **producción**. La tabla `estadisticazonanotarial` ya
existe. El dedup solo inserta filas cuando cambia `(sin_datos, price_avg)`
respecto a la última fila de esa (zona, combo).

---

## Checklist rápido

- [ ] `app/scraper/notariado_zonas/<slug>.json` — solo `geometry`, una línea, EPSG:3857
- [ ] slug añadido a `ZONA_SLUGS`
- [ ] `notariado_zonas/` sigue sin `__init__.py`
- [ ] `test_every_registered_zona_loads_a_real_geometry` parametrizado con el slug
- [ ] (si multi-anillo) test de anillos añadido
- [ ] geometría verificada en vivo → `200` con `priceAvg`
- [ ] suite completa sin fallos nuevos
- [ ] commit convencional, sin atribución de IA, PR a `master`

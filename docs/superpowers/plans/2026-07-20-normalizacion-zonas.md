# Normalización de Zonas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Asignar a cada propiedad de El Puerto de Santa María una zona canónica (`zona_normalizada`) derivada de un catálogo de alias, para que estadísticas y alertas de Telegram agrupen correctamente.

**Architecture:** Un módulo puro `app/scraper/zona_normalizer.py` (sin BD ni red) resuelve texto → zona canónica mediante una cascada de tres niveles sobre un catálogo YAML versionado. El `barrio` crudo nunca se modifica; el valor canónico vive en una columna nueva. Los consumidores (scrapers, estadísticas, filtros de alerta, página de revisión) se conectan en cuatro puntos pequeños.

**Tech Stack:** Python 3.12, SQLModel + PostgreSQL (Neon), PyYAML, pytest (`asyncio_mode=auto`), Streamlit.

Spec: `docs/superpowers/specs/2026-07-20-normalizacion-zonas-design.md`

## Global Constraints

- **`Propiedad.barrio` NUNCA se modifica.** Es el texto crudo del portal. Todo lo canónico va a `zona_normalizada`.
- **Nada de fuzzy matching** (Levenshtein, difflib, `SequenceMatcher`). Solo alias explícitos del catálogo. `"Pinar Hondo"` no debe resolver nunca a `"Pinar Alto"`.
- **`zona_normalizer` es puro**: no importa `db`, no hace I/O de red, no usa Streamlit. Solo texto → `ZonaMatch`. Esto es lo que lo hace testeable sin Postgres.
- Valores válidos de `zona_confianza`: exactamente `"exacta"`, `"via"`, `"debil"`, o `None`. Nunca otra cadena.
- El catálogo YAML guarda `alias` y `vias` **siempre en minúsculas y ya limpios** (sin acentos ni puntuación). Las claves (nombre canónico) van con su capitalización y acentos reales, porque son lo que se muestra en la UI.
- Alcance: solo El Puerto de Santa María. Otros municipios → `zona_normalizada = NULL`.
- Los comentarios y textos de UI del repo están en español. Mantenerlo.
- No hay Alembic: las migraciones son scripts SQL idempotentes en `scripts/`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `app/scraper/zona_normalizer.py` (crear) | Limpieza de texto, carga de catálogo, cascada de resolución. Núcleo puro. |
| `app/scraper/zonas_elpuerto.yaml` (crear) | Datos: zonas canónicas → alias + vías. |
| `app/db/models.py` (modificar) | Dos campos nuevos en `Propiedad`. |
| `scripts/migrate_zona_normalizada.py` (crear) | ALTER TABLE idempotente. |
| `scripts/dump_zonas.py` (crear) | Volcado read-only de barrios existentes → CSV. |
| `scripts/backfill_zonas.py` (crear) | Rellena `zona_normalizada` en el histórico. |
| `app/scraper/base.py` (modificar) | Wiring en `normalize_property`: rellenar campos al normalizar una propiedad scrapeada. |
| `app/pages/4_estadisticas.py` (modificar) | Alimentar el DataFrame con la zona canónica. |
| `app/notifications/filter_matcher.py` (modificar) | Regla OR canónica + legacy. |
| `app/pages/3_alertas.py` (modificar) | Ofrecer el catálogo canónico en el selector. |
| `app/scraper/description_enricher.py` (modificar) | Emitir sugerencia de `zona_normalizada`. |
| `tests/test_zona_normalizer.py` (crear) | Cascada y limpieza, con catálogo de prueba. |
| `tests/test_zona_normalizer_catalogo.py` (crear) | Integridad del YAML real. |
| `tests/test_zona_wiring.py` (modificar) | `base.normalize` rellena los campos. |
| `tests/test_filter_matcher_barrio.py` (modificar) | Regla OR. |

`app/ui/market_stats.py` **no se toca**: consume un DataFrame, no la BD.

---

### Task 1: Esquema — campos nuevos y migración

**Files:**
- Modify: `app/db/models.py:78-85` (bloque `# Location`)
- Create: `scripts/migrate_zona_normalizada.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nada (primera tarea)
- Produces: `Propiedad.zona_normalizada: Optional[str]`, `Propiedad.zona_confianza: Optional[str]`

Contexto: el proyecto no usa Alembic. `db.database.init_db()` llama a `SQLModel.metadata.create_all(engine)`, que crea tablas que no existen pero **no añade columnas a tablas existentes**. Por eso hace falta el script.

- [ ] **Step 1: Añadir los campos al modelo**

En `app/db/models.py`, en el bloque `# Location`, justo después de la línea `barrio: Optional[str] = Field(default=None, index=True)`, insertar:

```python
    zona_normalizada: Optional[str] = Field(default=None, index=True)  # zona canónica del catálogo
    zona_confianza: Optional[str] = None  # 'exacta' | 'via' | 'debil'
```

No tocar `barrio` ni ningún otro campo.

- [ ] **Step 2: Escribir el script de migración**

Crear `scripts/migrate_zona_normalizada.py`:

```python
#!/usr/bin/env python3
"""Añade las columnas zona_normalizada y zona_confianza a propiedad.

Idempotente: se puede ejecutar varias veces sin efecto adicional.
Las columnas son nullable y sin default, así que Postgres no reescribe
la tabla (no hay downtime en Neon).
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import text
from db.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENTENCIAS = [
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS zona_normalizada VARCHAR",
    "ALTER TABLE propiedad ADD COLUMN IF NOT EXISTS zona_confianza VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_propiedad_zona_normalizada "
    "ON propiedad (zona_normalizada)",
]

if __name__ == "__main__":
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            logger.info(sql)
            conn.execute(text(sql))
    logger.info("✓ Migración completada")
```

- [ ] **Step 3: Declarar PyYAML como dependencia**

`yaml` está instalado en el entorno local pero **no** figura en `requirements.txt`, así que el scheduler de GitHub Actions fallaría. Añadir al final de `requirements.txt`:

```
pyyaml>=6.0
```

- [ ] **Step 4: Verificar que el modelo importa**

Run: `python -c "import sys; sys.path.insert(0,'app'); from db.models import Propiedad; print(Propiedad.model_fields['zona_normalizada'], Propiedad.model_fields['zona_confianza'])"`

Expected: imprime los dos campos sin excepción. (Esto no toca la BD, solo valida la definición del modelo.)

- [ ] **Step 5: Ejecutar la migración**

Run: `python scripts/migrate_zona_normalizada.py`
Expected: tres líneas de log con las sentencias y `✓ Migración completada`.

Si falla con `OperationalError: connection refused`, `DATABASE_URL` no está configurado. No es un fallo del código: parar y avisar al usuario, no inventar una URL de conexión.

- [ ] **Step 6: Verificar que la suite sigue verde**

Run: `pytest -q`
Expected: mismo número de tests pasando que antes del cambio; 0 fallos.

- [ ] **Step 7: Commit**

```bash
git add app/db/models.py scripts/migrate_zona_normalizada.py requirements.txt
git commit -m "feat: campos zona_normalizada y zona_confianza en Propiedad"
```

---

### Task 2: Limpieza de texto

**Files:**
- Create: `app/scraper/zona_normalizer.py`
- Create: `tests/test_zona_normalizer.py`

**Interfaces:**
- Consumes: nada
- Produces: `limpiar(texto: Optional[str]) -> str`

`limpiar` es la base de todo el matching: si dos textos limpian igual, se consideran el mismo. Se hace primero y aislada porque cada regla suya es una fuente de falsos negativos.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_zona_normalizer.py`:

```python
"""Tests del normalizador de zonas — lógica pura, sin BD."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from scraper.zona_normalizer import limpiar


@pytest.mark.parametrize("entrada,esperado", [
    ("Pinar Alto", "pinar alto"),
    ("PINAR ALTO", "pinar alto"),
    ("  Pinar   Alto  ", "pinar alto"),
    ("Crevillét", "crevillet"),
    ("Menestéo", "menesteo"),
    ("Avda. de Sevilla", "avenida de sevilla"),
    ("Avda de Sevilla", "avenida de sevilla"),
    ("Avd. de Sevilla", "avenida de sevilla"),
    ("Av. de Sevilla", "avenida de sevilla"),
    ("Av de Sevilla", "avenida de sevilla"),
    ("C/ Larga, 12", "c larga 12"),
    ("Pinar-Alto", "pinar alto"),
    ("", ""),
    (None, ""),
])
def test_limpiar(entrada, esperado):
    assert limpiar(entrada) == esperado


def test_limpiar_no_parte_palabras_que_empiezan_por_av():
    """'avenida' ya limpio no se re-expande, y 'avila' no es 'avenida'."""
    assert limpiar("Avenida de Sevilla") == "avenida de sevilla"
    assert limpiar("Avila") == "avila"
```

`test_limpiar_no_parte_palabras_que_empiezan_por_av` es el test que importa: sin límites de palabra, la regla `av → avenida` convertiría `"Avila"` en `"avenidaila"`.

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_zona_normalizer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.scraper.zona_normalizer'`

- [ ] **Step 3: Implementar `limpiar`**

Crear `app/scraper/zona_normalizer.py`:

```python
"""Normalización de zonas de El Puerto de Santa María.

Módulo puro: entra texto, sale una zona canónica. No toca BD ni red, para
poder testearse sin Postgres (igual que zona_utils).
"""

import re
import unicodedata
from typing import Optional

# Abreviaturas de vía que hay que expandir antes de comparar. El orden no
# importa porque se aplican con límites de palabra sobre el texto ya limpio.
_ABREVIATURAS = {
    "avda": "avenida",
    "avd": "avenida",
    "av": "avenida",
}

_NO_ALFANUM = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")


def limpiar(texto: Optional[str]) -> str:
    """Devuelve el texto en forma comparable.

    Minúsculas, sin acentos, sin puntuación, espacios colapsados y
    abreviaturas de vía expandidas. Dos textos que limpian igual se
    consideran la misma cosa.
    """
    if not texto:
        return ""

    # Descomponer y quitar marcas diacríticas (á -> a, ñ -> n).
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))

    s = sin_acentos.lower()
    s = _NO_ALFANUM.sub(" ", s)
    s = _ESPACIOS.sub(" ", s).strip()

    if not s:
        return ""

    # Expandir abreviaturas palabra a palabra, nunca por substring: si no,
    # "avila" se convertiría en "avenidaila".
    palabras = [_ABREVIATURAS.get(p, p) for p in s.split(" ")]
    return " ".join(palabras)
```

Nota: `ñ` se pierde (`n`) por el `NFKD`. Es intencionado y simétrico — se aplica igual al catálogo y al texto de entrada, así que `"Peñas"` y `"Penas"` casan entre sí, que es lo que queremos.

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_zona_normalizer.py -v`
Expected: 16 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/scraper/zona_normalizer.py tests/test_zona_normalizer.py
git commit -m "feat: limpieza de texto para normalizacion de zonas"
```

---

### Task 3: Carga del catálogo

**Files:**
- Create: `app/scraper/zonas_elpuerto.yaml`
- Modify: `app/scraper/zona_normalizer.py`
- Modify: `tests/test_zona_normalizer.py`

**Interfaces:**
- Consumes: `limpiar()` de Task 2
- Produces:
  - `cargar_catalogo(ruta: Optional[str] = None) -> dict[str, dict[str, list[str]]]`
  - `RUTA_CATALOGO: Path`
  - `CatalogoInvalidoError(Exception)`

El catálogo de este task es una **semilla** con las tres zonas que el usuario ya conoce. Se amplía en Task 6, tras ver los datos reales.

- [ ] **Step 1: Crear el catálogo semilla**

Crear `app/scraper/zonas_elpuerto.yaml`:

```yaml
# Catálogo de zonas canónicas de El Puerto de Santa María.
#
# La clave es el nombre canónico: se muestra tal cual en la UI, con acentos
# y mayúsculas reales.
#   alias: cómo aparece escrita la zona en los portales.
#   vias:  calles/avenidas que pertenecen a la zona.
#
# alias y vias van SIEMPRE en minúsculas, sin acentos y sin puntuación
# (es decir, ya pasados por limpiar()). Hay un test que lo verifica.

Crevillet:
  alias:
    - crevillet
    - el crevillet
  vias: []

Pinar Alto:
  alias:
    - pinar alto
    - el pinar alto
    - pinaralto
  vias: []

Menesteo:
  alias:
    - menesteo
    - el menesteo
  vias: []
```

Las `vias` van vacías a propósito: las avenidas reales se añaden en Task 6, cuando el volcado diga cómo están escritas de verdad. Inventarlas ahora sería exactamente el error que la spec busca evitar.

- [ ] **Step 2: Escribir los tests que fallan**

Añadir al final de `tests/test_zona_normalizer.py`:

```python
import textwrap

from scraper.zona_normalizer import CatalogoInvalidoError, cargar_catalogo


def escribir_catalogo(tmp_path, contenido: str):
    ruta = tmp_path / "zonas_test.yaml"
    ruta.write_text(textwrap.dedent(contenido), encoding="utf-8")
    return str(ruta)


def test_cargar_catalogo_devuelve_zonas_con_alias_y_vias(tmp_path):
    ruta = escribir_catalogo(tmp_path, """
        Crevillet:
          alias: [crevillet, el crevillet]
          vias:  [avenida de sevilla]
    """)
    catalogo = cargar_catalogo(ruta)
    assert catalogo == {
        "Crevillet": {"alias": ["crevillet", "el crevillet"],
                      "vias": ["avenida de sevilla"]}
    }


def test_cargar_catalogo_rellena_listas_ausentes(tmp_path):
    """Una zona sin 'vias' es válida; se normaliza a lista vacía."""
    ruta = escribir_catalogo(tmp_path, """
        Menesteo:
          alias: [menesteo]
    """)
    assert cargar_catalogo(ruta)["Menesteo"]["vias"] == []


def test_cargar_catalogo_rechaza_zona_sin_alias(tmp_path):
    ruta = escribir_catalogo(tmp_path, """
        Fantasma:
          alias: []
          vias:  []
    """)
    with pytest.raises(CatalogoInvalidoError, match="sin alias"):
        cargar_catalogo(ruta)


def test_cargar_catalogo_rechaza_alias_duplicado_entre_zonas(tmp_path):
    """Un alias en dos zonas es ambigüedad silenciosa: debe explotar."""
    ruta = escribir_catalogo(tmp_path, """
        Pinar Alto:
          alias: [pinar]
        Pinar Hondo:
          alias: [pinar]
    """)
    with pytest.raises(CatalogoInvalidoError, match="duplicado"):
        cargar_catalogo(ruta)


def test_cargar_catalogo_rechaza_alias_sin_limpiar(tmp_path):
    """'Avda. de Sevilla' nunca casaría: limpiar() lo dejaría distinto."""
    ruta = escribir_catalogo(tmp_path, """
        Crevillet:
          alias: [crevillet]
          vias:  ["Avda. de Sevilla"]
    """)
    with pytest.raises(CatalogoInvalidoError, match="sin limpiar"):
        cargar_catalogo(ruta)
```

- [ ] **Step 3: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_zona_normalizer.py -v -k cargar_catalogo`
Expected: FAIL con `ImportError: cannot import name 'CatalogoInvalidoError'`

- [ ] **Step 4: Implementar la carga**

Añadir a `app/scraper/zona_normalizer.py`. En la cabecera del fichero, ampliar los imports:

```python
from functools import lru_cache
from pathlib import Path

import yaml
```

Y al final del fichero:

```python
RUTA_CATALOGO = Path(__file__).parent / "zonas_elpuerto.yaml"


class CatalogoInvalidoError(Exception):
    """El YAML de zonas tiene un error que haría fallar el matching."""


@lru_cache(maxsize=8)
def cargar_catalogo(ruta: Optional[str] = None) -> dict:
    """Carga y valida el catálogo de zonas.

    Cacheado por ruta: el YAML se lee del disco una sola vez por proceso.

    Returns:
        {nombre_canonico: {"alias": [...], "vias": [...]}}

    Raises:
        CatalogoInvalidoError: si el YAML tiene alias duplicados entre zonas,
            zonas sin alias, o términos que no están ya limpios.
    """
    destino = Path(ruta) if ruta else RUTA_CATALOGO
    crudo = yaml.safe_load(destino.read_text(encoding="utf-8")) or {}

    catalogo: dict = {}
    visto: dict = {}  # término -> zona que lo declaró primero

    for zona, datos in crudo.items():
        datos = datos or {}
        alias = list(datos.get("alias") or [])
        vias = list(datos.get("vias") or [])

        if not alias:
            raise CatalogoInvalidoError(f"Zona «{zona}» sin alias")

        for termino in alias + vias:
            if termino != limpiar(termino):
                raise CatalogoInvalidoError(
                    f"Término «{termino}» de «{zona}» está sin limpiar "
                    f"(debería ser «{limpiar(termino)}»)"
                )
            if termino in visto and visto[termino] != zona:
                raise CatalogoInvalidoError(
                    f"Término «{termino}» duplicado entre "
                    f"«{visto[termino]}» y «{zona}»"
                )
            visto[termino] = zona

        catalogo[zona] = {"alias": alias, "vias": vias}

    return catalogo
```

- [ ] **Step 5: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_zona_normalizer.py -v`
Expected: todos PASSED (los 16 de Task 2 + 5 nuevos)

- [ ] **Step 6: Commit**

```bash
git add app/scraper/zona_normalizer.py app/scraper/zonas_elpuerto.yaml tests/test_zona_normalizer.py
git commit -m "feat: carga y validacion del catalogo de zonas"
```

---

### Task 4: Cascada de resolución

**Files:**
- Modify: `app/scraper/zona_normalizer.py`
- Modify: `tests/test_zona_normalizer.py`
- Create: `tests/test_zona_normalizer_catalogo.py`

**Interfaces:**
- Consumes: `limpiar()`, `cargar_catalogo()`
- Produces:
  - `ZonaMatch` (dataclass congelada): `.zona: Optional[str]`, `.confianza: Optional[str]`, `.evidencia: str`
  - `SIN_ZONA_MATCH: ZonaMatch` — el resultado de "no hay match"
  - `normalizar(barrio=None, direccion=None, titulo=None, descripcion=None, url=None, ruta_catalogo=None) -> ZonaMatch`

Reglas de desempate, importantes (y verificadas ejecutando el código antes de escribir el plan):
- **Alias solapados: gana el más largo.** `"pinar alto"` gana a `"pinar"` — son la misma mención del texto vista dos veces.
- **Zonas distintas que casan por separado → ambiguo**, se descarta ese nivel y se pasa al siguiente. `"entre Crevillet y Pinar Hondo"` no devuelve zona. Elegir la más larga aquí sería arbitrario.
- La distinción entre ambos casos es "¿el término perdedor es subcadena del ganador?".
- Todo el matching usa **límites de palabra**, nunca substring crudo: si no, `"pinar"` casaría dentro de `"espinar"` y `"crevillet"` dentro de `"crevilletazo"`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_zona_normalizer.py`:

```python
from scraper.zona_normalizer import SIN_ZONA_MATCH, normalizar


@pytest.fixture
def catalogo(tmp_path):
    """Catálogo de prueba pequeño. NO es el catálogo real."""
    return escribir_catalogo(tmp_path, """
        Pinar Alto:
          alias: [pinar alto, el pinar alto]
          vias:  [avenida del pinar]
        Pinar Hondo:
          alias: [pinar hondo]
          vias:  []
        Crevillet:
          alias: [crevillet]
          vias:  [avenida de sevilla]
        Pinar Viejo:
          alias: [pinar]
          vias:  []
    """)


def test_nivel_1_alias_exacto_en_barrio(catalogo):
    m = normalizar(barrio="El Pinar Alto", ruta_catalogo=catalogo)
    assert m.zona == "Pinar Alto"
    assert m.confianza == "exacta"


def test_nivel_1_ignora_acentos_y_mayusculas(catalogo):
    assert normalizar(barrio="CREVILLÉT", ruta_catalogo=catalogo).zona == "Crevillet"


def test_nivel_2_via_en_barrio(catalogo):
    m = normalizar(barrio="Avda. de Sevilla, 12", ruta_catalogo=catalogo)
    assert m.zona == "Crevillet"
    assert m.confianza == "via"


def test_nivel_2_via_en_direccion(catalogo):
    m = normalizar(barrio=None, direccion="Avenida del Pinar 3, 2ºB",
                   ruta_catalogo=catalogo)
    assert m.zona == "Pinar Alto"
    assert m.confianza == "via"


def test_nivel_3_alias_en_descripcion(catalogo):
    m = normalizar(descripcion="Precioso piso en la zona de Crevillet, muy luminoso.",
                   ruta_catalogo=catalogo)
    assert m.zona == "Crevillet"
    assert m.confianza == "debil"


def test_nivel_3_alias_en_titulo(catalogo):
    m = normalizar(titulo="Ático en Crevillet con vistas", ruta_catalogo=catalogo)
    assert m.zona == "Crevillet"
    assert m.confianza == "debil"


def test_nivel_3_alias_en_url(catalogo):
    m = normalizar(url="https://x.com/venta/piso/el-puerto/pinar-alto/1234",
                   ruta_catalogo=catalogo)
    assert m.zona == "Pinar Alto"
    assert m.confianza == "debil"


def test_barrio_gana_a_descripcion(catalogo):
    """Nivel 1 corta la cascada: no se mira la descripción."""
    m = normalizar(barrio="Crevillet", descripcion="cerca de Pinar Alto",
                   ruta_catalogo=catalogo)
    assert m.zona == "Crevillet"
    assert m.confianza == "exacta"


def test_alias_solapado_gana_el_mas_largo(catalogo):
    """En texto libre, 'pinar alto' gana a 'pinar' (Pinar Viejo).

    Son la misma mención vista dos veces, no dos zonas distintas.
    """
    m = normalizar(titulo="Piso en Pinar Alto", ruta_catalogo=catalogo)
    assert m.zona == "Pinar Alto"
    assert m.confianza == "debil"


def test_sin_match_devuelve_zona_none(catalogo):
    m = normalizar(barrio="Valdelagrana", ruta_catalogo=catalogo)
    assert m == SIN_ZONA_MATCH
    assert m.zona is None
    assert m.confianza is None


def test_todo_vacio_devuelve_sin_match(catalogo):
    assert normalizar(ruta_catalogo=catalogo) == SIN_ZONA_MATCH


def test_no_hay_fuzzy_pinar_hondo_no_es_pinar_alto(catalogo):
    """El caso que justifica no usar distancia de edición."""
    m = normalizar(barrio="Pinar Hondo", ruta_catalogo=catalogo)
    assert m.zona == "Pinar Hondo"


def test_no_casa_dentro_de_otra_palabra(catalogo):
    """'crevillet' no debe casar dentro de 'crevilletazo'."""
    m = normalizar(descripcion="el famoso crevilletazo de la zona",
                   ruta_catalogo=catalogo)
    assert m.zona is None


def test_ambiguedad_en_descripcion_no_elige_al_azar(catalogo):
    """Dos zonas mencionadas con la misma fuerza -> ninguna."""
    m = normalizar(descripcion="entre Crevillet y Pinar Hondo",
                   ruta_catalogo=catalogo)
    assert m.zona is None


def test_evidencia_explica_el_match(catalogo):
    m = normalizar(barrio="Avda. de Sevilla, 12", ruta_catalogo=catalogo)
    assert "avenida de sevilla" in m.evidencia
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_zona_normalizer.py -v -k "nivel or alias or ambig or fuzzy or evidencia"`
Expected: FAIL con `ImportError: cannot import name 'normalizar'`

- [ ] **Step 3: Implementar la cascada**

Añadir a `app/scraper/zona_normalizer.py`. Ampliar los imports de la cabecera con:

```python
from dataclasses import dataclass
```

Y al final del fichero:

```python
CONFIANZA_EXACTA = "exacta"
CONFIANZA_VIA = "via"
CONFIANZA_DEBIL = "debil"


@dataclass(frozen=True)
class ZonaMatch:
    """Resultado de resolver una zona. `zona is None` significa sin match."""

    zona: Optional[str] = None
    confianza: Optional[str] = None
    evidencia: str = ""


SIN_ZONA_MATCH = ZonaMatch()


def _contiene_termino(texto_limpio: str, termino: str) -> bool:
    """True si `termino` aparece en `texto_limpio` como palabra completa.

    Con límites de palabra, nunca substring: si no, 'pinar' casaría dentro
    de 'espinar' y 'crevillet' dentro de 'crevilletazo'.
    """
    if not texto_limpio or not termino:
        return False
    return re.search(rf"\b{re.escape(termino)}\b", texto_limpio) is not None


def _mejor_candidato(texto_limpio: str, catalogo: dict, campo: str) -> Optional[tuple]:
    """Busca los términos de `campo` ('alias' o 'vias') en el texto.

    Gana el término más largo, pero solo cuando los demás términos que han
    casado son *solapamientos* suyos (subcadenas). Distinguir los dos casos
    es la parte delicada:

      - "piso en pinar alto" con alias 'pinar' y 'pinar alto' -> solapan,
        gana 'pinar alto'. Es la misma mención del texto vista dos veces.
      - "entre crevillet y pinar hondo" -> son dos menciones distintas de
        dos zonas distintas. Ambiguo: se devuelve None en lugar de elegir
        la más larga, que sería arbitrario.

    Returns:
        (zona, termino) o None.
    """
    if not texto_limpio:
        return None

    encontrados = [
        (zona, termino)
        for zona, datos in catalogo.items()
        for termino in datos[campo]
        if _contiene_termino(texto_limpio, termino)
    ]
    if not encontrados:
        return None

    zona_ganadora, ganador = max(encontrados, key=lambda par: len(par[1]))

    for zona, termino in encontrados:
        if zona != zona_ganadora and termino not in ganador:
            return None  # otra zona casó por su cuenta: ambiguo

    return (zona_ganadora, ganador)


def normalizar(
    barrio: Optional[str] = None,
    direccion: Optional[str] = None,
    titulo: Optional[str] = None,
    descripcion: Optional[str] = None,
    url: Optional[str] = None,
    ruta_catalogo: Optional[str] = None,
) -> ZonaMatch:
    """Resuelve la zona canónica de una propiedad.

    Cascada, parando en el primer acierto:
      1. alias exacto sobre `barrio`            -> 'exacta'
      2. vía conocida en `barrio` o `direccion` -> 'via'
      3. alias o vía en `titulo`+`descripcion`+`url` -> 'debil'

    Función pura: no consulta BD ni red.
    """
    catalogo = cargar_catalogo(ruta_catalogo)
    if not catalogo:
        return SIN_ZONA_MATCH

    # ── Nivel 1: el barrio limpio ES un alias ─────────────────────────────
    barrio_limpio = limpiar(barrio)
    if barrio_limpio:
        for zona, datos in catalogo.items():
            if barrio_limpio in datos["alias"]:
                return ZonaMatch(zona, CONFIANZA_EXACTA,
                                 f"barrio «{barrio_limpio}» es alias de {zona}")

    # ── Nivel 2: una vía conocida aparece en barrio o dirección ───────────
    texto_ubicacion = " ".join(filter(None, [barrio_limpio, limpiar(direccion)]))
    candidato = _mejor_candidato(texto_ubicacion, catalogo, "vias")
    if candidato:
        zona, termino = candidato
        return ZonaMatch(zona, CONFIANZA_VIA,
                         f"vía «{termino}» pertenece a {zona}")

    # ── Nivel 3: texto libre ──────────────────────────────────────────────
    texto_libre = " ".join(filter(None, [
        limpiar(titulo), limpiar(descripcion), limpiar(url),
    ]))
    for campo in ("alias", "vias"):
        candidato = _mejor_candidato(texto_libre, catalogo, campo)
        if candidato:
            zona, termino = candidato
            return ZonaMatch(zona, CONFIANZA_DEBIL,
                             f"«{termino}» encontrado en el texto de la ficha")

    return SIN_ZONA_MATCH
```

Nota sobre nivel 1: se compara `barrio_limpio in datos["alias"]` (igualdad exacta de la cadena completa), no `_contiene_termino`. Es deliberado — `"Avda. de Sevilla, 12"` no es un alias, es una vía, y debe caer al nivel 2 con menor confianza.

Nota sobre `url`: `limpiar` convierte `pinar-alto` en `pinar alto`, así que los slugs con guiones casan sin tratamiento extra.

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_zona_normalizer.py -v`
Expected: todos PASSED (los de Tasks 2 y 3 más los 15 de la cascada)

- [ ] **Step 5: Escribir el test de integridad del catálogo real**

Este test es distinto de los anteriores: valida el YAML **real** que se usa en producción, no un catálogo de prueba. Es lo que evita que el catálogo se degrade cuando se añadan alias en Task 6.

Crear `tests/test_zona_normalizer_catalogo.py`:

```python
"""Integridad del catálogo real de zonas de El Puerto.

A diferencia de test_zona_normalizer.py, estos tests cargan el YAML que se
usa en producción. Su función es que un alias mal escrito o duplicado se
detecte en CI y no en las estadísticas.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.zona_normalizer import cargar_catalogo, limpiar


def test_el_catalogo_real_carga_sin_errores():
    """cargar_catalogo valida duplicados, zonas vacías y términos sucios."""
    assert cargar_catalogo(), "El catálogo real está vacío"


def test_todos_los_terminos_estan_limpios():
    for zona, datos in cargar_catalogo().items():
        for termino in datos["alias"] + datos["vias"]:
            assert termino == limpiar(termino), (
                f"«{termino}» de «{zona}» no está limpio"
            )


def test_ningun_termino_esta_repetido_entre_zonas():
    visto = {}
    for zona, datos in cargar_catalogo().items():
        for termino in datos["alias"] + datos["vias"]:
            assert termino not in visto, (
                f"«{termino}» está en «{visto.get(termino)}» y en «{zona}»"
            )
            visto[termino] = zona


def test_zonas_de_interes_presentes():
    """Las tres zonas que motivaron el proyecto no pueden desaparecer."""
    zonas = set(cargar_catalogo())
    for esperada in ("Crevillet", "Pinar Alto", "Menesteo"):
        assert esperada in zonas, f"Falta la zona «{esperada}»"


def test_nombres_canonicos_no_tienen_espacios_sobrantes():
    for zona in cargar_catalogo():
        assert zona == zona.strip(), f"«{zona}» tiene espacios sobrantes"
        assert zona, "Hay una zona con nombre vacío"
```

- [ ] **Step 6: Ejecutar el test de catálogo**

Run: `pytest tests/test_zona_normalizer_catalogo.py -v`
Expected: 5 PASSED

- [ ] **Step 7: Verificar la suite completa**

Run: `pytest -q`
Expected: 0 fallos.

- [ ] **Step 8: Commit**

```bash
git add app/scraper/zona_normalizer.py tests/test_zona_normalizer.py tests/test_zona_normalizer_catalogo.py
git commit -m "feat: cascada de resolucion de zonas canonicas"
```

---

### Task 5: Volcado de zonas existentes

**Files:**
- Create: `scripts/dump_zonas.py`

**Interfaces:**
- Consumes: `Propiedad` (Task 1)
- Produces: CSV en `docs/superpowers/zonas_actuales.csv` (input humano de Task 6)

Script **read-only**: no escribe nada en la BD. Su salida es lo que convierte la construcción del catálogo en un ejercicio de agrupar lo que ya existe, en lugar de inventar.

- [ ] **Step 1: Escribir el script**

Crear `scripts/dump_zonas.py`:

```python
#!/usr/bin/env python3
"""Vuelca los valores de barrio existentes, con frecuencia, a un CSV.

SOLO LECTURA: no modifica la base de datos.

El CSV resultante es el material con el que se construye el catálogo
zonas_elpuerto.yaml. Columnas:
  barrio_crudo, veces, zona_actual, confianza_actual, ejemplo_url
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad
from scraper.zona_normalizer import normalizar

SALIDA = Path(__file__).parent.parent / "docs" / "superpowers" / "zonas_actuales.csv"

SIN_BARRIO = "(vacío)"


def main() -> None:
    with Session(engine) as session:
        propiedades = session.exec(select(Propiedad)).all()

    conteo = Counter()
    ejemplo = {}
    for p in propiedades:
        clave = (p.barrio or "").strip() or SIN_BARRIO
        conteo[clave] += 1
        ejemplo.setdefault(clave, p)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        escritor = csv.writer(fh)
        escritor.writerow([
            "barrio_crudo", "veces", "zona_actual", "confianza_actual", "ejemplo_url",
        ])
        for clave, veces in conteo.most_common():
            p = ejemplo[clave]
            m = normalizar(
                barrio=p.barrio, direccion=p.direccion, titulo=p.titulo,
                descripcion=p.descripcion, url=p.url_original,
            )
            escritor.writerow([
                clave, veces, m.zona or "", m.confianza or "", p.url_original,
            ])

    sin_match = sum(v for k, v in conteo.items()
                    if normalizar(barrio=ejemplo[k].barrio).zona is None)
    print(f"Propiedades analizadas : {len(propiedades)}")
    print(f"Valores distintos      : {len(conteo)}")
    print(f"Sin zona por 'barrio'  : {sin_match}")
    print(f"CSV escrito en         : {SALIDA}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar el volcado**

Run: `python scripts/dump_zonas.py`
Expected: las cuatro líneas de resumen y el CSV creado. Con el catálogo semilla, casi todo saldrá con `zona_actual` vacía — es lo esperado.

Si falla por conexión, `DATABASE_URL` no está configurado: parar y avisar al usuario.

- [ ] **Step 3: Commit**

```bash
git add scripts/dump_zonas.py
git commit -m "feat: script de volcado de zonas existentes"
```

El CSV **no** se commitea (contiene el estado de la BD, no es código). Añadirlo a `.gitignore` si molesta en `git status`.

---

### Task 6: 🛑 CHECKPOINT HUMANO — construir el catálogo real

**Files:**
- Modify: `app/scraper/zonas_elpuerto.yaml`

**Este task NO se puede automatizar.** Requiere conocimiento local de El Puerto de Santa María que no está en el código ni en los datos.

**PARAR aquí y hablar con el usuario.** No inventar barrios, alias ni avenidas. Un catálogo inventado produce mapeos silenciosamente erróneos, que es el fallo más caro del proyecto: contamina las estadísticas sin dar ningún error.

- [ ] **Step 1: Presentar el volcado al usuario**

Abrir `docs/superpowers/zonas_actuales.csv`, ordenado por frecuencia, y mostrarle las filas al usuario agrupadas por lo que parezcan ser la misma zona. Para cada grupo propuesto, preguntar explícitamente:

- ¿Estos valores son la misma zona? ¿Cuál es el nombre canónico correcto?
- ¿Alguna de estas vías pertenece a una de tus zonas de interés?
- ¿Hay valores que parezcan de otro municipio y haya que dejar fuera?

- [ ] **Step 2: Ampliar el YAML con lo confirmado**

Editar `app/scraper/zonas_elpuerto.yaml` añadiendo solo lo que el usuario haya confirmado. Recordatorio de formato: `alias` y `vias` en minúsculas, sin acentos, sin puntuación.

Para comprobar cómo debe escribirse un término en el YAML:

```bash
python -c "import sys; sys.path.insert(0,'app'); from scraper.zona_normalizer import limpiar; print(limpiar('Avda. de Sevilla'))"
```

Expected: `avenida de sevilla`

- [ ] **Step 3: Validar el catálogo ampliado**

Run: `pytest tests/test_zona_normalizer_catalogo.py -v`
Expected: 5 PASSED. Si falla por `duplicado`, hay un alias en dos zonas: preguntar al usuario a cuál pertenece, no elegir por cuenta propia.

- [ ] **Step 4: Volver a volcar y revisar la cobertura**

Run: `python scripts/dump_zonas.py`
Expected: `Sin zona por 'barrio'` ahora bastante menor. Revisar el CSV con el usuario: si alguna fila frecuente sigue sin zona, volver al Step 2.

- [ ] **Step 5: Commit**

```bash
git add app/scraper/zonas_elpuerto.yaml
git commit -m "feat: catalogo real de zonas de El Puerto validado con el usuario"
```

---

### Task 7: Wiring en el scraper

**Files:**
- Modify: `app/scraper/base.py:218` (dentro de `normalize_property`)
- Modify: `tests/test_zona_wiring.py`

**Interfaces:**
- Consumes: `normalizar()`, `ZonaMatch` (Task 4)
- Produces: propiedades scrapeadas con `zona_normalizada` y `zona_confianza` ya rellenos

A partir de aquí toda propiedad nueva entra normalizada, sin necesidad de backfill.

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `tests/test_zona_wiring.py`:

```python
from scraper.base import ScraperBase
from scraper.config import ScraperConfig
from db.models import Fuente


class ScraperParaZonas(ScraperBase):
    """Implementación concreta mínima de ScraperBase, solo para test.

    Mismo patrón que ConcreteScraperForTesting en tests/test_scraper_base.py.
    """

    async def scrape(self, fuente: Fuente):
        return []

    def _parse_properties(self, content: str):
        return []

    def _extract_fields(self, element):
        return {}


def _normalizar_raw(raw_data: dict):
    scraper = ScraperParaZonas(ScraperConfig(timeout=30, retries=3,
                                             verify_ssl=True, auto_detect=True))
    fuente = Fuente(id=1, nombre="Test", url="https://ejemplo.com",
                    tipo_scraper="generic", activa=True, intervalo_horas=24)
    return scraper.normalize_property(raw_data, fuente)


def test_normalize_property_rellena_zona_normalizada():
    """Una propiedad scrapeada sale con la zona canónica resuelta."""
    prop = _normalizar_raw({
        "url_original": "https://ejemplo.com/piso/1",
        "titulo": "Piso luminoso",
        "barrio": "El Pinar Alto",
    })
    assert prop.barrio == "El Pinar Alto"  # el crudo NO se toca
    assert prop.zona_normalizada == "Pinar Alto"
    assert prop.zona_confianza == "exacta"


def test_normalize_property_deja_zona_none_si_no_hay_match():
    prop = _normalizar_raw({
        "url_original": "https://ejemplo.com/piso/2",
        "titulo": "Piso en Madrid",
        "barrio": "Chamberí",
    })
    assert prop.barrio == "Chamberí"
    assert prop.zona_normalizada is None
    assert prop.zona_confianza is None
```

Notas importantes sobre este fichero de test:

- El método real se llama **`normalize_property(raw_data, fuente)`**, no `normalize(raw_data)`.
- La clave de URL en `raw_data` es **`url_original`**, no `url`.
- `tests/test_zona_wiring.py` ya hace `sys.path.insert(..., "app")` en su cabecera, así que los imports van como `from scraper.base import ...`. No añadir un segundo `sys.path.insert`.
- No hay `conftest.py` en el repo: cada fichero de test define sus propias fixtures. Por eso los helpers van locales aquí.

Estos tests usan el catálogo **real**, así que dependen de que `Pinar Alto` exista en él — garantizado por `test_zonas_de_interes_presentes` (Task 4).

- [ ] **Step 2: Ejecutar el test para verificar que falla**

Run: `pytest tests/test_zona_wiring.py -v -k zona_normalizada`
Expected: FAIL con `AttributeError` o `assert None == 'Pinar Alto'`

- [ ] **Step 3: Implementar el wiring**

En `app/scraper/base.py`, añadir el import junto a los demás imports del módulo:

```python
from scraper.zona_normalizer import normalizar as normalizar_zona
```

(Comprobar el estilo de import del fichero: si los módulos hermanos se importan como `from .zona_utils import ...`, usar la forma relativa equivalente.)

Después, dentro de **`normalize_property`**, **antes** del bloque `propiedad = Propiedad(...)`, calcular el match. Las claves alternativas (`address`, `description`) son las que ya usa el propio método más abajo, así que se replican para cubrir los scrapers que emiten nombres en inglés:

```python
            zona_match = normalizar_zona(
                barrio=raw_data.get("barrio"),
                direccion=raw_data.get("direccion") or raw_data.get("address"),
                titulo=raw_data.get("titulo") or raw_data.get("title"),
                descripcion=raw_data.get("descripcion") or raw_data.get("description"),
                url=raw_data.get("url_original") or raw_data.get("url"),
            )
```

Y en la construcción de `Propiedad`, justo después de la línea `barrio=raw_data.get("barrio"),` (línea 218), insertar:

```python
                zona_normalizada=zona_match.zona,
                zona_confianza=zona_match.confianza,
```

`normalizar_zona` no lanza excepciones para entradas vacías o `None` (devuelve `SIN_ZONA_MATCH`), así que no hace falta envolverlo en `try`. Sí lanzaría `CatalogoInvalidoError` si el YAML estuviera corrupto — y eso **debe** propagarse: un catálogo roto tiene que romper el scrapeo, no normalizar mal en silencio.

- [ ] **Step 4: Ejecutar el test para verificar que pasa**

Run: `pytest tests/test_zona_wiring.py -v`
Expected: todos PASSED

- [ ] **Step 5: Verificar que ningún scraper se ha roto**

Run: `pytest -q`
Expected: 0 fallos. Todos los scrapers pasan por `normalize`, así que esta suite es la red de seguridad real de este cambio.

- [ ] **Step 6: Commit**

```bash
git add app/scraper/base.py tests/test_zona_wiring.py
git commit -m "feat: los scrapers rellenan zona_normalizada al normalizar"
```

---

### Task 8: Wiring en alertas de Telegram

**Files:**
- Modify: `app/notifications/filter_matcher.py:97-105`
- Modify: `app/pages/3_alertas.py:100-108`
- Modify: `tests/test_filter_matcher_barrio.py`

**Interfaces:**
- Consumes: `Propiedad.zona_normalizada` (Task 1), `cargar_catalogo()` (Task 3)
- Produces: nada que consuman tareas posteriores

La regla es **OR**, y eso es lo crítico: cambiar a comparación exacta rompería todos los filtros guardados en el momento del deploy. Al ser OR, el cambio solo puede añadir coincidencias, nunca quitarlas.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_filter_matcher_barrio.py`:

```python
def test_casa_por_zona_normalizada_aunque_barrio_sea_una_avenida():
    """El caso que motiva el proyecto."""
    prop = Propiedad(
        hash_unico="z1", url_original="https://x.com/1", fuente_id=1,
        origen_web="Test", titulo="Piso",
        barrio="Avda. de Sevilla, 12", zona_normalizada="Crevillet",
    )
    assert FilterMatcher.matches(prop, {"barrio": "Crevillet"})


def test_filtro_legacy_por_substring_sigue_funcionando():
    """Un filtro guardado antes de la normalización no puede dejar de disparar."""
    prop = Propiedad(
        hash_unico="z2", url_original="https://x.com/2", fuente_id=1,
        origen_web="Test", titulo="Piso",
        barrio="Pinar Alto", zona_normalizada=None,
    )
    assert FilterMatcher.matches(prop, {"barrio": "pinar"})


def test_no_casa_si_no_coincide_ni_zona_ni_barrio():
    prop = Propiedad(
        hash_unico="z3", url_original="https://x.com/3", fuente_id=1,
        origen_web="Test", titulo="Piso",
        barrio="Valdelagrana", zona_normalizada="Valdelagrana",
    )
    assert not FilterMatcher.matches(prop, {"barrio": "Crevillet"})


def test_casa_con_lista_de_zonas():
    prop = Propiedad(
        hash_unico="z4", url_original="https://x.com/4", fuente_id=1,
        origen_web="Test", titulo="Piso",
        barrio="calle cualquiera", zona_normalizada="Menesteo",
    )
    assert FilterMatcher.matches(prop, {"barrio": ["Crevillet", "Menesteo"]})


def test_sin_barrio_ni_zona_no_casa():
    prop = Propiedad(
        hash_unico="z5", url_original="https://x.com/5", fuente_id=1,
        origen_web="Test", titulo="Piso",
        barrio=None, zona_normalizada=None,
    )
    assert not FilterMatcher.matches(prop, {"barrio": "Crevillet"})
```

Antes de escribirlos, leer las primeras líneas de `tests/test_filter_matcher_barrio.py` y usar el mismo helper de construcción de `Propiedad` y la misma forma de invocar el matcher que ya use el fichero. Si el fichero tiene una factory, usarla en lugar de construir `Propiedad(...)` a mano.

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_filter_matcher_barrio.py -v -k "zona_normalizada or legacy"`
Expected: FAIL — `test_casa_por_zona_normalizada_aunque_barrio_sea_una_avenida` falla porque hoy solo se mira `barrio`.

- [ ] **Step 3: Implementar la regla OR**

En `app/notifications/filter_matcher.py`, sustituir el bloque de las líneas 93-105 por:

```python
        # Zone/Neighborhood — OR entre dos vías, para no romper filtros
        # guardados antes de la normalización:
        #   (a) coincidencia exacta con la zona canónica, o
        #   (b) substring del barrio crudo (comportamiento histórico).
        # Al ser OR solo puede añadir coincidencias, nunca quitarlas.
        if key == "barrio":
            if isinstance(value, str):
                zonas = [z.strip().lower() for z in value.split(",") if z.strip()]
            else:
                zonas = [str(z).strip().lower() for z in value if str(z).strip()]
            if not zonas:
                return False

            zona_canonica = (propiedad.zona_normalizada or "").lower()
            if zona_canonica and zona_canonica in zonas:
                return True

            if propiedad.barrio:
                prop_barrio = propiedad.barrio.lower()
                if any(z in prop_barrio for z in zonas):
                    return True

            return False
```

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_filter_matcher_barrio.py -v`
Expected: todos PASSED, incluidos los que ya existían.

- [ ] **Step 5: Ofrecer el catálogo canónico en la UI de alertas**

En `app/pages/3_alertas.py`, la función `get_distinct_barrios_cached()` (líneas 27-37) alimenta las opciones del multiselect. Añadir las zonas canónicas a esas opciones, para que un filtro nuevo se cree con el nombre correcto.

En la línea 105, sustituir:

```python
        options=sorted(set(barrios_existentes) | set(barrio_default)),
```

por:

```python
        options=sorted(
            set(cargar_catalogo()) | set(barrios_existentes) | set(barrio_default)
        ),
```

Y añadir el import junto a los demás imports del fichero:

```python
from scraper.zona_normalizer import cargar_catalogo
```

Las zonas canónicas y los barrios crudos conviven en la lista a propósito: los filtros por zonas aún no catalogadas siguen siendo posibles.

- [ ] **Step 6: Verificar la suite completa**

Run: `pytest -q`
Expected: 0 fallos.

- [ ] **Step 7: Commit**

```bash
git add app/notifications/filter_matcher.py app/pages/3_alertas.py tests/test_filter_matcher_barrio.py
git commit -m "feat: alertas casan por zona canonica manteniendo compatibilidad"
```

---

### Task 9: Wiring en estadísticas y revisión

**Files:**
- Modify: `app/pages/4_estadisticas.py:37`
- Modify: `app/scraper/description_enricher.py:133-152`
- Modify: `app/pages/5_revision.py:20-33` y `:54-66`

**Interfaces:**
- Consumes: `Propiedad.zona_normalizada`, `normalizar()`
- Produces: nada que consuman tareas posteriores

Dos integraciones muy pequeñas gracias a cómo está montado el código: `market_stats.py` consume un DataFrame (no la BD) y `5_revision.py` es genérico sobre el dict que devuelve `extract_suggestions`.

- [ ] **Step 1: Alimentar las estadísticas con la zona canónica**

En `app/pages/4_estadisticas.py`, dentro de `fetch_props()`, sustituir en la línea 37:

```python
            "barrio": p.barrio, "municipio": p.municipio, "origen_web": p.origen_web,
```

por:

```python
            "barrio": p.zona_normalizada or p.barrio,
            "municipio": p.municipio, "origen_web": p.origen_web,
```

La clave del dict sigue llamándose `"barrio"` a propósito: `market_stats.py` y sus tests dependen de ese nombre, y no hay razón para tocarlos.

El fallback `or p.barrio` es intencionado: una propiedad sin catalogar sigue apareciendo con su valor crudo en vez de caer toda en `SIN_ZONA`.

- [ ] **Step 2: Verificar los tests de estadísticas**

Run: `pytest tests/test_market_stats.py tests/test_offer_advisor.py -q`
Expected: 0 fallos (no deberían verse afectados; construyen sus propios DataFrames).

- [ ] **Step 3: Emitir sugerencia de zona en el enricher**

En `app/scraper/description_enricher.py`, dentro de `extract_suggestions`, **después** del bloque `# ── Barrio / zona ──` que termina en la línea 152 (justo antes del `return suggestions`), añadir:

```python
    # ── Zona canónica ─────────────────────────────────────────────────────
    # Solo se sugiere cuando la cascada NO dio confianza 'exacta': los match
    # exactos los escribe el backfill sin intervención humana, así que
    # pedir que se aprueben sería ruido.
    if not prop.zona_normalizada:
        match = normalizar_zona(
            barrio=prop.barrio,
            direccion=prop.direccion,
            titulo=prop.titulo,
            descripcion=prop.descripcion,
            url=prop.url_original,
        )
        if match.zona:
            suggestions["zona_normalizada"] = (match.zona, match.evidencia)

    return suggestions
```

Y añadir el import en la cabecera del fichero, siguiendo el estilo de imports que ya use:

```python
from scraper.zona_normalizer import normalizar as normalizar_zona
```

- [ ] **Step 4: Mostrar la zona en la página de Revisión**

En `app/pages/5_revision.py`:

En `FIELD_LABELS` (líneas 20-33), añadir tras la entrada `"barrio"`:

```python
    "zona_normalizada": "Zona canónica",
```

Y en el `or_(...)` de la consulta (líneas 54-66), añadir tras `Propiedad.barrio == None,`:

```python
                    Propiedad.zona_normalizada == None,
```

Nada más: la página ya itera genéricamente sobre las sugerencias y guarda con `PropiedadCRUD.update(**updates)`.

- [ ] **Step 5: Verificar que el enricher sigue verde**

Run: `pytest tests/test_enricher_barrio.py -q`
Expected: 0 fallos.

- [ ] **Step 6: Verificar la suite completa y arrancar la app**

Run: `pytest -q`
Expected: 0 fallos.

Run: `streamlit run app/main.py`
Comprobar a mano, y luego cerrar: la página **Estadísticas** carga sin error y el desplegable de barrios muestra nombres canónicos; la página **Revisión** carga y muestra "Zona canónica" entre las sugerencias.

- [ ] **Step 7: Commit**

```bash
git add app/pages/4_estadisticas.py app/pages/5_revision.py app/scraper/description_enricher.py
git commit -m "feat: estadisticas y revision usan la zona canonica"
```

---

### Task 10: Backfill del histórico

**Files:**
- Create: `scripts/backfill_zonas.py`

**Interfaces:**
- Consumes: `normalizar()`, `Propiedad.zona_normalizada`
- Produces: el histórico normalizado

Solo se escriben los match de confianza `exacta`. Los `via` y `debil` se dejan sin escribir y aparecen como sugerencias en la página de Revisión (Task 9), donde el usuario los aprueba uno a uno.

- [ ] **Step 1: Escribir el script**

Crear `scripts/backfill_zonas.py`:

```python
#!/usr/bin/env python3
"""Rellena zona_normalizada en las propiedades ya existentes.

Por defecto es dry-run: informa sin escribir. Con --apply escribe, y SOLO
los match de confianza 'exacta'. Los 'via' y 'debil' se dejan vacíos a
propósito: aparecen como sugerencias en la página de Revisión.

Reejecutable sin efectos secundarios: como Propiedad.barrio nunca se
modifica, se puede relanzar tantas veces como se amplíe el catálogo.

  python scripts/backfill_zonas.py            # dry-run
  python scripts/backfill_zonas.py --apply    # escribe
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, select

from db.database import engine
from db.models import Propiedad
from scraper.zona_normalizer import CONFIANZA_EXACTA, normalizar


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Escribe en la BD. Sin este flag solo informa.",
    )
    args = parser.parse_args()

    reparto = Counter()
    escritas = 0

    with Session(engine) as session:
        propiedades = session.exec(
            select(Propiedad).where(Propiedad.zona_normalizada == None)  # noqa: E711
        ).all()

        for p in propiedades:
            m = normalizar(
                barrio=p.barrio, direccion=p.direccion, titulo=p.titulo,
                descripcion=p.descripcion, url=p.url_original,
            )
            reparto[m.confianza or "sin match"] += 1

            if args.apply and m.confianza == CONFIANZA_EXACTA:
                p.zona_normalizada = m.zona
                p.zona_confianza = m.confianza
                session.add(p)
                escritas += 1

        if args.apply:
            session.commit()

    print(f"Propiedades sin zona     : {len(propiedades)}")
    for confianza in ("exacta", "via", "debil", "sin match"):
        print(f"  {confianza:<10}: {reparto[confianza]}")

    if args.apply:
        print(f"\n✓ Escritas {escritas} propiedades (solo confianza 'exacta')")
        print("  Las de confianza 'via' y 'debil' esperan en la página Revisión.")
    else:
        print("\nDRY-RUN: no se ha escrito nada. Usa --apply para confirmar.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar en dry-run**

Run: `python scripts/backfill_zonas.py`
Expected: el reparto y `DRY-RUN: no se ha escrito nada.`

**Revisar el reparto con el usuario antes de seguir.** Si `sin match` sigue siendo la mayoría de las propiedades de El Puerto, el catálogo está incompleto: volver a Task 6 en lugar de aplicar.

- [ ] **Step 3: Aplicar**

Run: `python scripts/backfill_zonas.py --apply`
Expected: `✓ Escritas N propiedades (solo confianza 'exacta')`

- [ ] **Step 4: Verificar el resultado en la app**

Run: `streamlit run app/main.py`

Comprobar en **Estadísticas** que el desplegable "Barrios" ahora muestra zonas canónicas agrupadas, y que las zonas de interés del usuario aparecen con un número de activas plausible en lugar de estar repartidas o caídas en `OTROS`. Cerrar la app después.

- [ ] **Step 5: Confirmar que el dry-run es idempotente**

Run: `python scripts/backfill_zonas.py`
Expected: `exacta: 0` — ya no queda nada por escribir. Confirma que el script es reejecutable sin duplicar trabajo.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_zonas.py
git commit -m "feat: backfill de zona_normalizada en el historico"
```

---

## Verificación final

- [ ] `pytest -q` → 0 fallos
- [ ] `python scripts/backfill_zonas.py` → `exacta: 0` (nada pendiente)
- [ ] La app arranca y Estadísticas agrupa por zonas canónicas
- [ ] Las tres zonas de interés (Crevillet, Pinar Alto, Menesteo) aparecen en Estadísticas
- [ ] Un filtro de alerta guardado antes del cambio sigue disparando
- [ ] `git log --oneline` muestra un commit por task

## Fuera de alcance

- Municipios distintos de El Puerto de Santa María
- Fuzzy matching
- Geocodificación por `latitud`/`longitud`
- Mostrar la zona canónica en la ficha de propiedad (`property_queries.py`)
- Las otras dos funcionalidades pedidas (imágenes, penotariado.com), cada una con su propia spec

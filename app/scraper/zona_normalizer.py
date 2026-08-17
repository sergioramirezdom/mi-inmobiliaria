"""Normalización de zonas de El Puerto de Santa María.

Módulo puro: entra texto, sale una zona canónica. No toca BD ni red, para
poder testearse sin Postgres (igual que zona_utils).
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

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

    # ── Nivel 1.5: el barrio contiene un alias como palabra completa ─────
    # Cubre barrios con formato "ZONA / Municipio" (ej. "CENTRO / El Puerto
    # de Santa Maria") donde el alias está contenido pero no es igual.
    if barrio_limpio:
        candidato = _mejor_candidato(barrio_limpio, catalogo, "alias")
        if candidato:
            zona, termino = candidato
            return ZonaMatch(zona, CONFIANZA_EXACTA,
                             f"barrio «{barrio_limpio}» contiene alias «{termino}» de {zona}")

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

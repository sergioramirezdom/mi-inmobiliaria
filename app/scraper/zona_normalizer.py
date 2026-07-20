"""Normalización de zonas de El Puerto de Santa María.

Módulo puro: entra texto, sale una zona canónica. No toca BD ni red, para
poder testearse sin Postgres (igual que zona_utils).
"""

import re
import unicodedata
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

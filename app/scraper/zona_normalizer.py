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

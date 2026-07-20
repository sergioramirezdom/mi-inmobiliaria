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

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


def test_nivel_1_5_alias_contenido_en_barrio():
    """Barrio con formato 'ZONA / Municipio' matchea por containment."""
    m = normalizar(barrio="CENTRO / El Puerto de Santa Maria")
    assert m.zona == "Centro"
    assert m.confianza == "exacta"


def test_nivel_1_5_alias_contenido_con_acentos():
    m = normalizar(barrio="CREVILLET / El Puerto de Santa Maria")
    assert m.zona == "Crevillet"
    assert m.confianza == "exacta"


def test_nivel_1_5_ambiguedad_devuelve_none():
    """Barrio con multiples aliases de zonas distintas -> ambiguo."""
    m = normalizar(barrio="Pinar Alto Crevillet Menesteo")
    assert m.zona is None

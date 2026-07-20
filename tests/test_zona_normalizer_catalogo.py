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

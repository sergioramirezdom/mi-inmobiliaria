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

"""Tests for extract_barrio_from_text in description_enricher."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.description_enricher import extract_barrio_from_text


def test_extracts_urbanizacion():
    titulo = "Piso en urbanización Las Redes"
    descripcion = "Bonito piso en urbanización Las Redes, cerca de la playa."
    assert extract_barrio_from_text(titulo, descripcion) == "Las Redes"


def test_extracts_zona_keyword():
    titulo = "Piso en venta"
    descripcion = "Situado en zona Pinar Alto, con vistas al mar."
    result = extract_barrio_from_text(titulo, descripcion)
    assert result is not None
    assert "Pinar" in result


def test_returns_none_when_no_zona():
    titulo = "Piso en venta"
    descripcion = "3 habitaciones, 2 baños, 90m². Muy luminoso."
    assert extract_barrio_from_text(titulo, descripcion) is None


def test_returns_none_for_empty_input():
    assert extract_barrio_from_text("", "") is None
    assert extract_barrio_from_text(None, None) is None


# ── Generic phrases must not become a barrio (#49) ───────────────────────────

import pytest


@pytest.mark.parametrize("titulo,descripcion", [
    ("Piso reformado", "Piso reformado en zona residencial tranquila, cerca de todo"),
    ("Piso con terraza", "Zona comun con piscina."),
    ("Piso 3 dorm", "urbanizacion cerrada con piscina, 3 dorm"),
    ("Casa", "Barrio con mucho ambiente y todos los servicios."),
])
def test_generic_phrases_are_not_barrio(titulo, descripcion):
    assert extract_barrio_from_text(titulo, descripcion) is None


def test_returns_canonical_catalogue_name():
    result = extract_barrio_from_text("Piso", "Piso en zona el pinar alto, con vistas.")
    assert result == "Pinar Alto"


def test_catalogue_alias_with_trailing_words():
    result = extract_barrio_from_text("Piso", "Vivienda en urbanización Las Redes con piscina comunitaria")
    assert result == "Las Redes"

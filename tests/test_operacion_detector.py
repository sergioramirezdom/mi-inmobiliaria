"""Table-driven tests for detectar_operacion / es_garaje (issue #41).

The detector decides whether a listing is silently DROPPED, so the costly
errors are a false "alquiler" (a sale lost) and a false garage. Every case
below is a reproduced misclassification from the audit.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from scraper.operacion_detector import detectar_operacion, es_garaje


# ── detectar_operacion: substrings must not match ────────────────────────────


@pytest.mark.parametrize(
    "titulo",
    [
        "Piso con distribución diferente en Centro",
        "Piso con vistas al frente del parque",
        "Casa con jardin transparente",
        "Piso diferente con reforma",
        "Apartamento aparente en Rentería",
    ],
)
def test_title_substrings_of_rent_are_not_alquiler(titulo):
    assert detectar_operacion(titulo=titulo, precio=200000) != "alquiler"


def test_diferente_title_with_venta_url_is_venta():
    got = detectar_operacion(
        "Piso con distribución diferente en Centro", 200000, "https://x/Venta-Piso-1"
    )
    assert got == "venta"


# ── detectar_operacion: alquilado is an attribute, not an operation ──────────


def test_vendo_piso_alquilado_is_not_alquiler():
    assert detectar_operacion(titulo="Vendo piso alquilado con inquilino") == "venta"


def test_description_alquilada_is_not_alquiler():
    got = detectar_operacion(
        titulo="Chalet en El Puerto",
        precio=350000,
        descripcion="Vivienda alquilada con inquilino, ideal inversión, rentabilidad 5%.",
    )
    assert got != "alquiler"


def test_description_posibilidad_de_alquiler_is_not_alquiler():
    got = detectar_operacion(
        titulo="Piso en Centro",
        precio=200000,
        descripcion="Posibilidad de alquiler a turistas. Muy luminoso.",
    )
    assert got != "alquiler"


def test_description_monthly_community_fee_is_not_alquiler():
    got = detectar_operacion(
        titulo="Piso en Centro",
        precio=200000,
        descripcion="Gastos de comunidad 30 €/mes. Muy luminoso.",
    )
    assert got != "alquiler"


# ── detectar_operacion: real rentals are still detected ──────────────────────


@pytest.mark.parametrize(
    "titulo",
    [
        "Piso en alquiler en El Puerto",
        "Alquiler de piso en el centro",
        "Se alquila apartamento",
        "Local en arrendamiento",
        "Piso 90 m2 650 €/mes",
        "Flat for rent in El Puerto",
    ],
)
def test_title_rental_phrases_are_alquiler(titulo):
    assert detectar_operacion(titulo=titulo, precio=650) == "alquiler"


def test_description_se_alquila_without_other_signal_is_alquiler():
    got = detectar_operacion(
        titulo="Piso en Centro", descripcion="Se alquila piso reformado."
    )
    assert got == "alquiler"


def test_description_en_alquiler_without_other_signal_is_alquiler():
    got = detectar_operacion(
        titulo="Piso en Centro", descripcion="Precioso piso en alquiler."
    )
    assert got == "alquiler"


def test_description_rental_phrase_loses_to_venta_phrase():
    got = detectar_operacion(
        titulo="Piso en Centro",
        descripcion="Se vende piso, antes en alquiler.",
    )
    assert got != "alquiler"


def test_alquiler_url_is_alquiler():
    assert detectar_operacion(url="https://x/Alquiler-Piso-El-Puerto-12") == "alquiler"


# ── detectar_operacion: explicit site signal wins ────────────────────────────


def test_venta_url_beats_alquiler_word_in_title():
    got = detectar_operacion(
        titulo="Piso ideal para alquiler vacacional",
        url="https://x/Venta-Piso-El-Puerto-1",
    )
    assert got == "venta"


def test_alquiler_url_beats_venta_title():
    got = detectar_operacion(
        titulo="Piso en venta", url="https://x/Alquiler-Piso-El-Puerto-1"
    )
    assert got == "alquiler"


def test_title_with_both_signals_is_uncertain():
    assert detectar_operacion(titulo="Alquiler con opción a venta") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://x/inventario-de-pisos/1",
        "https://x/aventura/2",
        "https://x/Calle-Ventura/3",
    ],
)
def test_venta_substring_in_url_is_not_a_signal(url):
    assert detectar_operacion(url=url) is None


def test_venta_url_word_is_venta():
    assert detectar_operacion(url="https://x/venta/piso-1") == "venta"


def test_domain_words_do_not_count_as_url_signal():
    assert detectar_operacion(url="https://alquileres-puerto.com/piso/1") is None


# ── detectar_operacion: price is not a signal on its own ─────────────────────


@pytest.mark.parametrize("precio", [3500, 1200, 650.0])
def test_low_price_alone_is_not_alquiler(precio):
    assert detectar_operacion(titulo="Trastero en El Puerto", precio=precio) is None


def test_low_price_with_venta_url_is_venta():
    got = detectar_operacion(titulo="Parcela", precio=3500, url="https://x/Venta-Terreno-9")
    assert got == "venta"


# ── detectar_operacion: None-safety ──────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [
        {"titulo": None, "precio": 1200},
        {"titulo": None, "descripcion": "Alquiler"},
        {"titulo": None, "url": None, "descripcion": None},
        {},
    ],
)
def test_none_title_does_not_raise(kwargs):
    detectar_operacion(**kwargs)


def test_nothing_known_is_uncertain():
    assert detectar_operacion() is None


# ── es_garaje ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "titulo",
    [
        "Piso con parking privado",
        "Atico con plaza de garaje",
        "Piso + garaje y trastero",
        "Piso, garaje incluido",
        "Casa con garaje",
        "Chalet incluye garaje",
    ],
)
def test_garage_as_complement_is_not_garaje(titulo):
    assert es_garaje(titulo=titulo) is False


@pytest.mark.parametrize(
    "titulo",
    [
        "Plaza de garaje en centro",
        "Garaje en El Puerto de Santa María",
        "Parking en Centro",
        "Venta de garaje en Valdelagrana",
        "Se vende plaza de garaje",
        "Plazas de garaje en edificio nuevo",
    ],
)
def test_garage_as_head_noun_is_garaje(titulo):
    assert es_garaje(titulo=titulo) is True


def test_tipo_propiedad_garaje_wins():
    assert es_garaje(titulo="Inmueble en venta", tipo_propiedad="garaje") is True


def test_specific_non_garage_tipo_wins_over_title():
    assert es_garaje(titulo="Plaza de garaje en centro", tipo_propiedad="piso") is False


def test_garaje_url_is_garaje():
    assert es_garaje(titulo="Inmueble", url="https://x/inmuebles/garajes/12") is True


def test_es_garaje_none_safe():
    assert es_garaje() is False

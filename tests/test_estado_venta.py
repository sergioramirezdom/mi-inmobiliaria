"""Tests for the shared sold/reserved detector (issue #40).

A false "vendido" deactivates a live listing with no confirmation, so the
helper only trusts a bounded, contextual signal (status badge, exact status
text, title segment) and ignores footer, menu, "similares" and description text.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from bs4 import BeautifulSoup

from scraper.estado_venta import detect_estado_en_texto, detect_estado_venta


def _soup(body: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body>{body}</body></html>", "html.parser")


# ── Live pages: text that merely contains the words ──────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        "<footer><p>© 2026 Todos los derechos reservados</p></footer>",
        "<div class='pie'><p>Todos los derechos reservados</p></div>",
        "<p>Plaza de garaje reservada incluida en el precio.</p>",
        "<p>Zona reservada para vecinos. Vendido con mobiliario.</p>",
        "<div id='descripcion'>Vivienda actualmente alquilada, ideal inversión.</div>",
        "<h1>Piso en zona reservada del centro</h1>",
        "<nav><a href='/v'>Vendido</a><a href='/r'>Reservado</a></nav>",
        "<select><option>Vendido</option><option>Reservado</option></select>",
        "<div class='inmuebles_similares'><span class='estado'>Vendido</span></div>",
        "<div class='relacionados'><div>Reservado</div></div>",
        "<script>var estado = 'Vendido';</script><style>.x{}</style>",
        "<p>La vivienda está reservada para el comprador que presente oferta antes del lunes.</p>",
        "<p>Descubre todos los pisos vendidos y reservados por nosotros.</p>",
    ],
)
def test_live_page_is_not_sold(body):
    assert detect_estado_venta(_soup(body), include_rented=True) is None


# ── Real status signals ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body, expected",
    [
        ("<div class='ribbon'>Vendido</div>", "Vendido"),
        ("<span class='estado-inmueble'>Reservada</span>", "Reservada"),
        ("<div class='cinta'>¡VENDIDO!</div>", "Vendido"),
        ("<span>Reservado</span>", "Reservado"),
        ("<p>Este inmueble está VENDIDO</p>", "Vendido"),
        ("<div class='status'>Reservado - señal pagada</div>", "Reservado"),
        ("<h1>Vendido - Piso en el centro</h1>", "Vendido"),
        ("<h1>Piso en el centro (Reservado)</h1>", "Reservado"),
        ("<h1>Piso en el centro | vendido</h1>", "Vendido"),
    ],
)
def test_real_status_signal_is_detected(body, expected):
    assert detect_estado_venta(_soup(body)) == expected


@pytest.mark.parametrize(
    "body, expected",
    [
        ("<div class='ribbon'>Sold</div>", "Vendido"),
        ("<div class='ribbon'>Reserved</div>", "Reservado"),
        ("<h1>Sold - Flat in El Puerto</h1>", "Vendido"),
    ],
)
def test_english_status_is_detected(body, expected):
    assert detect_estado_venta(_soup(body)) == expected


def test_alquilado_only_when_requested():
    soup = _soup("<div class='ribbon'>Alquilado</div>")
    assert detect_estado_venta(soup) is None
    assert detect_estado_venta(soup, include_rented=True) == "Alquilado"


def test_reservado_stays_distinguishable_from_vendido():
    reservado = detect_estado_venta(_soup("<div class='ribbon'>Reservado</div>"))
    vendido = detect_estado_venta(_soup("<div class='ribbon'>Vendido</div>"))
    assert reservado != vendido


def test_signal_outside_excluded_region_still_wins():
    soup = _soup(
        "<footer>Todos los derechos reservados</footer>"
        "<div class='ribbon'>Vendido</div>"
    )
    assert detect_estado_venta(soup) == "Vendido"


def test_match_evidence_is_logged(caplog):
    with caplog.at_level(logging.INFO, logger="scraper.estado_venta"):
        detect_estado_venta(_soup("<div class='ribbon'>Vendido</div>"))
    assert "Vendido" in caplog.text and "ribbon" in caplog.text


# ── Free-text fallback (manual URLs on unknown sites) ────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Esta propiedad está vendida.", "Vendida"),
        ("RESERVADO. Contacte para más info.", "Reservado"),
        ("Inmueble reservado por el cliente", "Reservado"),
    ],
)
def test_text_status_phrase_is_detected(text, expected):
    assert detect_estado_en_texto(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Todos los derechos reservados",
        "Plaza de garaje reservada incluida en el precio",
        "Zona reservada para vecinos",
        "Vivienda con inquilino, actualmente alquilada",
        "",
    ],
)
def test_text_without_status_phrase_is_not_sold(text):
    assert detect_estado_en_texto(text) is None

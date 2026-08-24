"""Unit tests for NeopolisScraper — parses real captured NEOPOLIS HTML fixtures.

No live network calls: `fetch_content` is monkeypatched to return fixture HTML.
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.neopolis_scraper import NeopolisScraper

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DETAIL_URL = (
    "https://www.neopolis.es/ficha/piso/el-puerto-de-santa-maria/"
    "crevillet/4131/29204678/es/"
)
ALQUILER_URL = (
    "https://www.neopolis.es/ficha/piso/el-puerto-de-santa-maria/"
    "centro-alto/4131/29999999/es/"
)
MISSING_FIELDS_URL = "https://www.neopolis.es/ficha/estudio/29900000/es/"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


async def _scrape_with_fixture(scraper: NeopolisScraper, fixture_name: str, url: str) -> dict:
    html = _load_fixture(fixture_name)
    scraper.fetch_content = AsyncMock(return_value=html)
    return await scraper.scrape_property_details(url)


# ── Full field extraction ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_full_fields():
    scraper = NeopolisScraper()
    data = await _scrape_with_fixture(scraper, "neopolis_detail.html", DETAIL_URL)

    assert data["titulo"] == "PISO EN LA ZONA DE RONDA DE LAS DUNAS."
    assert data["precio"] == 139000.0
    assert data["superficie_m2"] == 74.0
    assert data["superficie_util_m2"] == 61.79
    assert data["habitaciones"] == 3
    assert data["banos"] == 1
    assert data["planta"] == 3
    assert data["tipo_propiedad"] == "piso"
    assert data["estado"] == "Reformar Parcialmente"
    assert data["precio_comunidad"] == 40.0
    assert data["precio_ibi"] == 235.0
    assert data["certificado_energetico"] == "E"
    assert "trastero" in data
    assert data["trastero"] is True
    assert "terraza" in data
    assert data["terraza"] is True
    assert data["aire_acondicionado"] is True
    assert data["calefaccion"] == "Split en pared"
    assert "Trastero" in data["amenidades"]
    assert data["descripcion"].startswith("PISO EN LA ZONA DE RONDA DE LAS DUNAS.")
    assert data["direccion"] == "Crevillet / El Puerto de Santa Maria"
    assert data["barrio"] == "Crevillet"
    assert data["fotos"]
    assert all(f.startswith("https://fotos15.apinmo.com") for f in data["fotos"])
    assert "fecha_publicacion" in data
    assert data["tipo_operacion"] == "venta"


# ── year_built guard (mobilia_scraper.py bug must not be repeated) ────────


@pytest.mark.asyncio
async def test_no_year_built_field():
    """`Propiedad` has no `year_built` column. NEOPOLIS's 'Antigüedad' field
    must never be mapped there, unlike the dead mapping in mobilia_scraper.py."""
    scraper = NeopolisScraper()
    data = await _scrape_with_fixture(scraper, "neopolis_detail.html", DETAIL_URL)
    assert "year_built" not in data

    data_missing = await _scrape_with_fixture(
        scraper, "neopolis_detail_missing_fields.html", MISSING_FIELDS_URL
    )
    assert "year_built" not in data_missing


# ── Missing-field resilience ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_field_resilience():
    scraper = NeopolisScraper()
    data = await _scrape_with_fixture(
        scraper, "neopolis_detail_missing_fields.html", MISSING_FIELDS_URL
    )

    assert data["titulo"] == "ESTUDIO EN VENTA."
    assert data["precio"] == 85000.0
    assert data["tipo_propiedad"] == "estudio"

    for absent_key in (
        "superficie_m2",
        "superficie_util_m2",
        "habitaciones",
        "banos",
        "precio_comunidad",
        "precio_ibi",
        "certificado_energetico",
        "amenidades",
    ):
        assert absent_key not in data


# ── barrio from URL ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_barrio_from_url():
    scraper = NeopolisScraper()
    data = await _scrape_with_fixture(scraper, "neopolis_detail.html", DETAIL_URL)
    assert data["barrio"] == "Crevillet"


@pytest.mark.asyncio
async def test_barrio_falls_back_to_html_without_zona_segment_in_url():
    """A URL without a recognizable zona segment falls through to the HTML
    'Zona / Ciudad' characteristic instead."""
    scraper = NeopolisScraper()
    url_no_zona = "https://www.neopolis.es/ficha/piso/29204678/es/"
    data = await _scrape_with_fixture(scraper, "neopolis_detail.html", url_no_zona)
    assert data["barrio"] == "Crevillet"


# ── alquiler early return ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alquiler_early_return():
    scraper = NeopolisScraper()
    data = await _scrape_with_fixture(
        scraper, "neopolis_detail_alquiler.html", ALQUILER_URL
    )

    assert data["activa"] is False
    assert data["estado"] == "Alquiler"
    assert data["tipo_operacion"] == "alquiler"

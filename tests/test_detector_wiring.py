"""Scraper wiring of the operation detector (issue #41).

Alonsaga and Guadalete used to call the detector BEFORE extracting the
description (so the description argument was always None); Neopolis ranked the
site's explicit "Tipo operación" label below the heuristics.
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper import alonsaga_scraper, guadalete_scraper
from scraper.neopolis_scraper import NeopolisScraper

ALONSAGA_URL = "https://www.alonsaga.com/inmueble/piso/el-puerto/12345/"
GUADALETE_URL = "https://www.inmobiliariaguadalete.com/inmuebles/pisos/piso-centro-ig1234"
DESCRIPCION = "Piso reformado en el centro, muy luminoso y con todo tipo de servicios cerca. " * 3

ALONSAGA_HTML = (
    "<html><body><h1>Piso en El Puerto</h1><p>150.000 €</p>"
    f"<p id='inmueble2_datos_adicionales'>{DESCRIPCION}</p></body></html>"
)
GUADALETE_HTML = (
    "<html><body><h1>IG1234 - Piso en El Puerto</h1><p>€ 150.000</p>"
    f"<p>{DESCRIPCION}</p></body></html>"
)


def _spy(monkeypatch, module):
    seen = {}

    def fake(titulo=None, precio=None, url=None, descripcion=None):
        seen["descripcion"] = descripcion
        return None

    monkeypatch.setattr(module, "detectar_operacion", fake)
    return seen


@respx.mock
@pytest.mark.asyncio
async def test_alonsaga_passes_description_to_detector(monkeypatch):
    seen = _spy(monkeypatch, alonsaga_scraper)
    respx.get(ALONSAGA_URL).mock(return_value=httpx.Response(200, text=ALONSAGA_HTML))

    await alonsaga_scraper.AlonsagaScraper().scrape_property_details(ALONSAGA_URL)

    assert seen["descripcion"] and seen["descripcion"].startswith("Piso reformado")


@respx.mock
@pytest.mark.asyncio
async def test_guadalete_passes_description_to_detector(monkeypatch):
    seen = _spy(monkeypatch, guadalete_scraper)
    respx.get(GUADALETE_URL).mock(return_value=httpx.Response(200, text=GUADALETE_HTML))

    await guadalete_scraper.GuadaleteScraper().scrape_property_details(GUADALETE_URL)

    assert seen["descripcion"] and seen["descripcion"].startswith("Piso reformado")


@pytest.mark.asyncio
async def test_neopolis_vender_label_wins_over_rental_description():
    """Label 'Vender' -> venta even when the description reads like a rental."""
    scraper = NeopolisScraper()
    html = (Path(__file__).parent / "fixtures" / "neopolis_detail.html").read_text(encoding="utf-8")
    scraper.fetch_content = AsyncMock(return_value=html)

    def rental_description(soup, data):
        data["descripcion"] = "Se alquila piso en el centro. Precioso piso en alquiler."

    scraper._extract_descripcion = rental_description

    data = await scraper.scrape_property_details(
        "https://www.neopolis.es/ficha/piso/el-puerto-de-santa-maria/crevillet/4131/29204678/es/"
    )

    assert data["tipo_operacion"] == "venta"
    assert data.get("activa") is not False

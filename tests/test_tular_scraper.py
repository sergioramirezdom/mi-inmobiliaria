"""Unit tests for TularScraper — pure logic (inline HTML) + fixture parse.

tular.es runs the same InmoServer CMS as SAMPER but serves the ``#inmueble1_*``
skin (SAMPER serves ``#inmueble2_*``). Selectors were confirmed against the
committed ``tests/fixtures/tular_detalle.html`` bytes captured by a raw httpx
GET during the T0 discovery task.
"""
import sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from bs4 import BeautifulSoup

from scraper.tular_scraper import (
    TularScraper,
    _parse_price_eu,
    _extract_superficie_m2,
    _extract_habitaciones,
    _extract_banos,
    _extract_planta,
    _extract_tipo,
    _extract_direccion,
    _extract_municipio,
    _extract_barrio,
    _extract_descripcion,
    _extract_fotos_detail,
    _extract_referencia,
    _extract_caracteristicas_li_items,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── _parse_price_eu ──────────────────────────────────────────────────────────


def test_parse_price_eu_dot_thousands():
    assert _parse_price_eu("171.000 €") == 171000.0


def test_parse_price_eu_strips_disclaimer():
    assert _parse_price_eu("171.000 € (impuestos y gastos no incluídos)") == 171000.0


def test_parse_price_eu_with_comma_decimal():
    assert _parse_price_eu("250.000,50 €") == 250000.5


def test_parse_price_eu_invalid():
    assert _parse_price_eu("no price") is None


# ── _extract_superficie_m2 (free-text <li> parsing, Gate B) ──────────────────


def test_extract_superficie_m2_literal_m2():
    assert _extract_superficie_m2("72 M2 Construidos") == 72.0


def test_extract_superficie_m2_collapsed_superscript():
    # BeautifulSoup get_text(strip=True) collapses "96 M<sup>2</sup>Construidos"
    assert _extract_superficie_m2("96 M2Construidos") == 96.0


def test_extract_superficie_m2_lowercase_superscript_glyph():
    assert _extract_superficie_m2("96 m² construidos") == 96.0


def test_extract_superficie_m2_none_when_not_matching():
    assert _extract_superficie_m2("Buen estado") is None


def test_extract_superficie_m2_handles_thousands():
    assert _extract_superficie_m2("1.234,5 M2 Construidos") == 1234.5


# ── _extract_habitaciones / _extract_banos ───────────────────────────────────


def test_extract_habitaciones_from_li_text():
    assert _extract_habitaciones("4 Dormitorios") == 4


def test_extract_habitaciones_none_when_not_matching():
    assert _extract_habitaciones("Exterior") is None


def test_extract_banos_from_li_text():
    assert _extract_banos("1 Baños") == 1


def test_extract_banos_none_when_not_matching():
    assert _extract_banos("Planta 3") is None


# ── _extract_planta ───────────────────────────────────────────────────────────


def test_extract_planta_numeric():
    assert _extract_planta("Planta 3") == "3"


def test_extract_planta_baja():
    assert _extract_planta("Planta baja") == "baja"


def test_extract_planta_none_when_not_matching():
    assert _extract_planta("Buen estado") is None


# ── _extract_caracteristicas_li_items ────────────────────────────────────────


def test_extract_caracteristicas_li_items_inmueble1_skin():
    html = """
    <div id="inmueble1_caracteristicas_inmueble_container">
      <ul>
        <li class="mb-2">96 M<sup>2</sup> Construidos</li>
        <li class="mb-2">74 M<sup>2</sup> Útiles</li>
        <li class="mb-2">4 Dormitorios</li>
        <li class="mb-2">1 Baños</li>
        <li class="mb-2">Planta 3</li>
      </ul>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_caracteristicas_li_items(soup)
    assert items == [
        "96 M2Construidos",
        "74 M2Útiles",
        "4 Dormitorios",
        "1 Baños",
        "Planta 3",
    ]


def test_extract_caracteristicas_li_items_empty_when_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_caracteristicas_li_items(soup) == []


# ── _extract_tipo ─────────────────────────────────────────────────────────────


def test_extract_tipo_piso():
    assert _extract_tipo("Piso en venta") == "piso"


def test_extract_tipo_duplex():
    assert _extract_tipo("Dúplex en venta") == "dúplex"


def test_extract_tipo_none():
    assert _extract_tipo("") is None


# ── _extract_direccion / municipio / barrio ──────────────────────────────────


def test_extract_direccion_inmueble1_skin():
    html = '<p id="inmueble1_titulo2_subtitulo">El Puerto de Santa María, CREVILLET</p>'
    soup = BeautifulSoup(html, "lxml")
    assert _extract_direccion(soup) == "El Puerto de Santa María, CREVILLET"


def test_extract_direccion_excludes_mapa_button():
    html = """
    <p id="inmueble1_titulo2_subtitulo">
        El Puerto de Santa María, CREVILLET
        <span id="boton_modal_mapa"><i class="fas fa-map-marker-alt"></i> mapa</span>
    </p>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_direccion(soup) == "El Puerto de Santa María, CREVILLET"


def test_extract_municipio():
    assert (
        _extract_municipio("El Puerto de Santa María, CREVILLET")
        == "El Puerto de Santa María"
    )


def test_extract_barrio():
    assert _extract_barrio("El Puerto de Santa María, CREVILLET") == "Crevillet"


def test_extract_barrio_none_without_comma():
    assert _extract_barrio("El Puerto de Santa María") is None


# ── _extract_descripcion ─────────────────────────────────────────────────────


def test_extract_descripcion_from_datos_adicionales():
    html = """
    <p id="inmueble1_datos_adicionales">Piso de 4 dormitorios con terraza cerca de la playa de La Puntilla.</p>
    """
    soup = BeautifulSoup(html, "lxml")
    desc = _extract_descripcion(soup)
    assert "playa de La Puntilla" in desc


def test_extract_descripcion_none_when_missing():
    soup = BeautifulSoup("<html><body><p>nada</p></body></html>", "lxml")
    assert _extract_descripcion(soup) is None


# ── _extract_fotos_detail ─────────────────────────────────────────────────────


def test_extract_fotos_detail_inmoserver_urls():
    html = """
    <div id="carousel-img-principal">
      <div class="carousel-item"><img src="https://www.inmoserver.com/fotos/0394/nwm/811_a.jpg?v=2"></div>
      <div class="carousel-item"><img src="https://www.inmoserver.com/fotos/0394/nwm/811_b.jpg"></div>
      <div class="carousel-item"><img src="https://www.inmoserver.com/fotos/0394/nwm/811_a.jpg"></div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos_detail(soup)
    assert fotos == [
        "https://www.inmoserver.com/fotos/0394/nwm/811_a.jpg",
        "https://www.inmoserver.com/fotos/0394/nwm/811_b.jpg",
    ]


def test_extract_fotos_detail_empty():
    soup = BeautifulSoup("<html><body><p>no carousel</p></body></html>", "lxml")
    assert _extract_fotos_detail(soup) == []


# ── _extract_referencia ───────────────────────────────────────────────────────


def test_extract_referencia():
    html = '<div id="referenceTop"><p>Referencia:</p><h4 class="ml-2">811-202614</h4></div>'
    soup = BeautifulSoup(html, "lxml")
    assert _extract_referencia(soup) == "811-202614"


def test_extract_referencia_none_when_missing():
    soup = BeautifulSoup("<html><body><p>no ref</p></body></html>", "lxml")
    assert _extract_referencia(soup) is None


# ── Fixture-based full detail parse ──────────────────────────────────────────


def _fake_client_returning(html, status=200):
    class FakeResponse:
        status_code = status
        text = html

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return FakeResponse()

    return FakeClient


@pytest.mark.asyncio
async def test_scrape_property_details_full_fixture(monkeypatch):
    html = (FIXTURES_DIR / "tular_detalle.html").read_text(encoding="utf-8")
    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", _fake_client_returning(html))

    scraper = TularScraper()
    data = await scraper.scrape_property_details(
        "https://www.tular.es/Venta-Piso-El-Puerto-de-Santa-María-CREVILLET-811"
    )

    for key in (
        "url_original",
        "activa",
        "titulo",
        "precio",
        "superficie_m2",
        "habitaciones",
        "banos",
        "tipo_propiedad",
        "tipo_operacion",
        "direccion",
        "municipio",
        "barrio",
        "descripcion",
        "referencia",
        "fotos",
    ):
        assert data.get(key) is not None, f"{key} should not be None"

    assert data["municipio"] == "El Puerto de Santa María"
    assert data["precio"] == 171000.0
    assert data["superficie_m2"] == 96.0
    assert data["habitaciones"] == 4
    assert data["banos"] == 1
    assert data["tipo_propiedad"] == "piso"
    assert data["tipo_operacion"] == "venta"
    assert data["referencia"] == "811-202614"
    assert data["activa"] is True
    assert len(data["fotos"]) >= 1
    assert all("inmoserver.com" in f for f in data["fotos"])
    assert "impuestos" not in str(data["precio"])


# ── Sold / 404 handling ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_404_marks_inactive(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(
        httpx_module, "AsyncClient", _fake_client_returning("", status=404)
    )
    scraper = TularScraper()
    data = await scraper.scrape_property_details("https://www.tular.es/Venta-Piso-1")
    assert data["activa"] is False
    assert data.get("estado") == "No disponible"


@pytest.mark.asyncio
async def test_scrape_property_details_sold_text_marks_inactive(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(
        httpx_module,
        "AsyncClient",
        _fake_client_returning(
            "<html><body><h1>Piso</h1><p>Este inmueble está RESERVADO</p></body></html>"
        ),
    )
    scraper = TularScraper()
    data = await scraper.scrape_property_details("https://www.tular.es/Venta-Piso-1")
    assert data["activa"] is False
    assert data.get("estado")


# ── Fetch failure is non-fatal ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_network_error_does_not_raise(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise ConnectionError("boom")

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)

    scraper = TularScraper()
    data = await scraper.scrape_property_details("https://www.tular.es/Venta-Piso-1")
    assert "url_original" in data
    assert "activa" in data


@pytest.mark.asyncio
async def test_scrape_property_details_non_200_non_404_returns_partial(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(
        httpx_module, "AsyncClient", _fake_client_returning("", status=503)
    )
    scraper = TularScraper()
    data = await scraper.scrape_property_details("https://www.tular.es/Venta-Piso-1")
    assert data["url_original"].endswith("/Venta-Piso-1")
    assert data["activa"] is True


# ── Missing individual field ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_missing_caracteristicas_block(monkeypatch):
    html = """
    <html><body>
    <h4 id="inmueble1_titulo2">Piso en venta</h4>
    <p id="inmueble1_titulo2_subtitulo">El Puerto de Santa María, CREVILLET</p>
    <h5 id="inmueble1_precio">150.000 € (impuestos y gastos no incluídos)</h5>
    <p id="inmueble1_datos_adicionales">Piso reformado en el centro con muy buenas vistas al mar cercano de El Puerto.</p>
    </body></html>
    """

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", _fake_client_returning(html))

    scraper = TularScraper()
    data = await scraper.scrape_property_details("https://www.tular.es/Venta-Piso-1")

    assert data.get("habitaciones") is None
    assert data.get("superficie_m2") is None
    assert data.get("precio") == 150000.0
    assert data.get("municipio") == "El Puerto de Santa María"
    assert data.get("descripcion") is not None

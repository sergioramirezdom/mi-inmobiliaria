"""Unit tests for SamperScraper — pure logic (inline HTML) + fixture parse."""
import sys, os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from bs4 import BeautifulSoup

from scraper.samper_scraper import (
    SamperScraper,
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
    assert _parse_price_eu("240.000 €") == 240000.0


def test_parse_price_eu_with_comma_decimal():
    assert _parse_price_eu("250.000,50 €") == 250000.5


def test_parse_price_eu_invalid():
    assert _parse_price_eu("no price") is None


# ── _extract_superficie_m2 (free-text <li> parsing) ──────────────────────────


def test_extract_superficie_m2_from_li_text():
    assert _extract_superficie_m2("72 M2 Construidos") == 72.0


def test_extract_superficie_m2_none_when_not_matching():
    assert _extract_superficie_m2("Buen estado") is None


def test_extract_superficie_m2_handles_thousands():
    assert _extract_superficie_m2("1.234,5 M2 Construidos") == 1234.5


# ── _extract_habitaciones / _extract_banos ───────────────────────────────────


def test_extract_habitaciones_from_li_text():
    assert _extract_habitaciones("3 Dormitorios") == 3


def test_extract_habitaciones_none_when_not_matching():
    assert _extract_habitaciones("Exterior") is None


def test_extract_banos_from_li_text():
    assert _extract_banos("1 Baños") == 1


def test_extract_banos_none_when_not_matching():
    assert _extract_banos("Planta baja") is None


# ── _extract_planta ───────────────────────────────────────────────────────────


def test_extract_planta_baja():
    assert _extract_planta("Planta baja") == "baja"


def test_extract_planta_numeric():
    assert _extract_planta("Planta 3") == "3"


def test_extract_planta_none_when_not_matching():
    assert _extract_planta("Buen estado") is None


# ── _extract_caracteristicas_li_items ────────────────────────────────────────


def test_extract_caracteristicas_li_items():
    html = """
    <div id="inmueble2_caracteristicas_inmueble_container">
      <ul>
        <li>72 M2 Construidos</li>
        <li>3 Dormitorios</li>
        <li>1 Baños</li>
        <li>Buen estado</li>
        <li>Exterior</li>
        <li>Planta baja</li>
      </ul>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_caracteristicas_li_items(soup)
    assert items == [
        "72 M2 Construidos",
        "3 Dormitorios",
        "1 Baños",
        "Buen estado",
        "Exterior",
        "Planta baja",
    ]


def test_extract_caracteristicas_li_items_empty_when_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_caracteristicas_li_items(soup) == []


# ── _extract_tipo ─────────────────────────────────────────────────────────────


def test_extract_tipo_piso():
    assert _extract_tipo("Piso en venta") == "piso"


def test_extract_tipo_chalet():
    assert _extract_tipo("Chalet en venta") == "chalet"


def test_extract_tipo_none():
    assert _extract_tipo("") is None


# ── _extract_direccion / municipio / barrio ──────────────────────────────────


def test_extract_direccion():
    html = '<p id="inmueble2_titulo2_subtitulo">El Puerto de Santa María, PINAR ALTO</p>'
    soup = BeautifulSoup(html, "lxml")
    assert _extract_direccion(soup) == "El Puerto de Santa María, PINAR ALTO"


def test_extract_direccion_excludes_mapa():
    html = """
    <p id="inmueble2_titulo2_subtitulo">
        El Puerto de Santa María, PINAR ALTO
        <span id="boton_modal_mapa"><i class="fas fa-map-marker-alt"></i> mapa</span>
    </p>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_direccion(soup) == "El Puerto de Santa María, PINAR ALTO"


def test_extract_municipio():
    assert _extract_municipio("El Puerto de Santa María, PINAR ALTO") == "El Puerto de Santa María"


def test_extract_barrio():
    assert _extract_barrio("El Puerto de Santa María, PINAR ALTO") == "Pinar Alto"


def test_extract_barrio_none_without_comma():
    assert _extract_barrio("El Puerto de Santa María") is None


# ── _extract_descripcion ─────────────────────────────────────────────────────


def test_extract_descripcion_concatenates_aut_and_adicionales():
    html = """
    <p id="inmueble2_descripcion_aut">Piso en PINAR ALTO, con 72 m2 construidos.</p>
    <p id="inmueble2_datos_adicionales">Samper Gestiones Inmobiliarias os presenta esta magnifica vivienda.</p>
    """
    soup = BeautifulSoup(html, "lxml")
    desc = _extract_descripcion(soup)
    assert "Piso en PINAR ALTO" in desc
    assert "Samper Gestiones Inmobiliarias" in desc


def test_extract_descripcion_none_when_missing():
    soup = BeautifulSoup("<html><body><p>nada</p></body></html>", "lxml")
    assert _extract_descripcion(soup) is None


# ── _extract_fotos_detail ─────────────────────────────────────────────────────


def test_extract_fotos_detail():
    html = """
    <div id="carousel-img-principal">
      <div class="carousel-item"><img src="https://www.inmoserver.com/fotos/1223/wm/61_a.jpg"></div>
      <div class="carousel-item"><img src="https://www.inmoserver.com/fotos/1223/wm/61_b.jpg"></div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos_detail(soup)
    assert fotos == [
        "https://www.inmoserver.com/fotos/1223/wm/61_a.jpg",
        "https://www.inmoserver.com/fotos/1223/wm/61_b.jpg",
    ]


def test_extract_fotos_detail_empty():
    soup = BeautifulSoup("<html><body><p>no carousel</p></body></html>", "lxml")
    assert _extract_fotos_detail(soup) == []


# ── _extract_referencia ───────────────────────────────────────────────────────


def test_extract_referencia():
    html = '<div id="referenceTop"><p>Referencia:</p><h4>61-550</h4></div>'
    soup = BeautifulSoup(html, "lxml")
    assert _extract_referencia(soup) == "61-550"


def test_extract_referencia_none_when_missing():
    soup = BeautifulSoup("<html><body><p>no ref</p></body></html>", "lxml")
    assert _extract_referencia(soup) is None


# ── Fixture-based full detail parse ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_full_fixture(monkeypatch):
    html = (FIXTURES_DIR / "samper_detalle.html").read_text(encoding="utf-8")

    class FakeResponse:
        status_code = 200
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

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)

    scraper = SamperScraper()
    data = await scraper.scrape_property_details(
        "https://www.sampergestionesinmobiliarias.es/Venta-Piso-El-Puerto-de-Santa-María-PINAR-ALTO-61"
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
        "direccion",
        "municipio",
        "barrio",
        "descripcion",
        "fotos",
    ):
        assert data.get(key) is not None, f"{key} should not be None"

    assert data["municipio"] == "El Puerto de Santa María"
    assert data["precio"] == 240000.0
    assert data["superficie_m2"] == 72.0
    assert data["habitaciones"] == 3
    assert data["banos"] == 1
    assert len(data["fotos"]) == 3
    assert data["activa"] is True


# ── Sold / 404 handling ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_404_marks_inactive(monkeypatch):
    class FakeResponse:
        status_code = 404
        text = ""

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return FakeResponse()

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)

    scraper = SamperScraper()
    data = await scraper.scrape_property_details("https://example.com/Venta-Piso-1")
    assert data["activa"] is False
    assert data.get("estado")


@pytest.mark.asyncio
async def test_scrape_property_details_sold_text_marks_inactive(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "<html><body><h1>Piso</h1><p>Este inmueble está VENDIDO</p></body></html>"

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            return FakeResponse()

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)

    scraper = SamperScraper()
    data = await scraper.scrape_property_details("https://example.com/Venta-Piso-1")
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

    scraper = SamperScraper()
    data = await scraper.scrape_property_details("https://example.com/Venta-Piso-1")
    assert "url_original" in data
    assert "activa" in data


# ── Missing individual field ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scrape_property_details_missing_room_count_omits_field(monkeypatch):
    html = """
    <html><body>
    <h4 id="inmueble2_titulo2">Piso en venta</h4>
    <p id="inmueble2_titulo2_subtitulo">El Puerto de Santa María, PINAR ALTO</p>
    <h5 id="inmueble2_precio">150.000 €</h5>
    <div id="inmueble2_caracteristicas_inmueble_container">
      <ul>
        <li>60 M2 Construidos</li>
        <li>Buen estado</li>
      </ul>
    </div>
    <p id="inmueble2_descripcion_aut">Piso reformado en el centro con muy buenas vistas al mar cercano.</p>
    </body></html>
    """

    class FakeResponse:
        status_code = 200
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

    import httpx as httpx_module

    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)

    scraper = SamperScraper()
    data = await scraper.scrape_property_details("https://example.com/Venta-Piso-1")

    assert data.get("habitaciones") is None
    assert data.get("superficie_m2") == 60.0
    assert data.get("precio") == 150000.0

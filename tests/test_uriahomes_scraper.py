"""Unit tests for UriaHomesScraper — pure logic, no HTTP calls."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.uriahomes_scraper import (
    _parse_price_eu,
    _extract_superficie_m2,
    _extract_room_count,
    _extract_tipo,
    _extract_direccion,
    _extract_municipio,
    _extract_barrio,
    _extract_descripcion,
    _extract_fotos_detail,
    _extract_caracteristicas,
    _extract_energia,
    _extract_coords_from_js,
    _map_feature,
)
from bs4 import BeautifulSoup


# ── _parse_price_eu ──────────────────────────────────────────────────────────


def test_parse_price_eu_dot_thousands():
    assert _parse_price_eu("180.000") == 180000.0


def test_parse_price_eu_with_comma_decimal():
    assert _parse_price_eu("250.000,50") == 250000.5


def test_parse_price_eu_plain():
    assert _parse_price_eu("95000") == 95000.0


def test_parse_price_eu_invalid():
    assert _parse_price_eu("no price") is None


# ── _extract_superficie_m2 ───────────────────────────────────────────────────


def test_extract_superficie_m2():
    html = """
    <div id="inmueble2_caracteristicas">
      <i class="fa-solid fa-vector-square"></i><span class="p-2">70 m<sup>2</sup></span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_superficie_m2(soup) == 70.0


def test_extract_superficie_m2_none_when_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_superficie_m2(soup) is None


def test_extract_superficie_m2_handles_thousands():
    html = """
    <div id="inmueble2_caracteristicas">
      <i class="fa-solid fa-vector-square"></i><span class="p-2">1.234,5 m<sup>2</sup></span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_superficie_m2(soup) == 1234.5


# ── _extract_room_count ──────────────────────────────────────────────────────


def test_extract_room_count_bed():
    html = """
    <div id="inmueble2_caracteristicas">
      <i class="fas fa-bed"></i><span class="p-2">3</span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 3


def test_extract_room_count_bath():
    html = """
    <div id="inmueble2_caracteristicas">
      <i class="fas fa-bath"></i><span class="p-2">1</span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bath") == 1


def test_extract_room_count_none_when_missing():
    soup = BeautifulSoup("<html><body><p>nothing here</p></body></html>", "lxml")
    assert _extract_room_count(soup, "fa-bed") is None


def test_extract_room_count_ignores_outside_container():
    """The 'similares' section reuses fa-bed outside #inmueble2_caracteristicas — must be ignored."""
    html = """
    <div id="inmueble2_caracteristicas">
      <i class="fas fa-bed"></i><span class="p-2">3</span>
    </div>
    <div class="inmuebles_similares_habitaciones">
      <i class="fas fa-bed"></i><span class="p-2">99</span>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_room_count(soup, "fa-bed") == 3


# ── _extract_tipo ────────────────────────────────────────────────────────────


def test_extract_tipo_flat():
    html = "<h4 id='inmueble2_titulo2'>Flat for sale</h4>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_tipo(soup) == "piso"


def test_extract_tipo_chalet():
    html = "<h4 id='inmueble2_titulo2'>Chalet for sale</h4>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_tipo(soup) == "chalet"


def test_extract_tipo_house():
    html = "<h4 id='inmueble2_titulo2'>House for sale</h4>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_tipo(soup) == "casa"


def test_extract_tipo_none():
    soup = BeautifulSoup("<html><body><p>no title</p></body></html>", "lxml")
    assert _extract_tipo(soup) is None


# ── _extract_direccion / municipio / barrio ──────────────────────────────────


def test_extract_direccion():
    html = "<p id='inmueble2_titulo2_subtitulo'>El Puerto de Santa María, EL JUNCAL</p>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_direccion(soup) == "El Puerto de Santa María, EL JUNCAL"


def test_extract_direccion_excludes_mapa():
    """The #inmueble2_titulo2_subtitulo contains a map button whose text must be excluded."""
    html = '''
    <p id="inmueble2_titulo2_subtitulo" class="pl-0 pl-md-2 mb-2">
        El Puerto de Santa María, EL JUNCAL
        <span id="boton_modal_mapa" class="link color-dark">
            <i class="fas fa-map-marker-alt"></i> mapa
        </span>
    </p>
    '''
    soup = BeautifulSoup(html, "lxml")
    result = _extract_direccion(soup)
    assert result == "El Puerto de Santa María, EL JUNCAL"


def test_extract_direccion_excludes_map_english():
    """Same but with English 'map' text."""
    html = '''
    <p id="inmueble2_titulo2_subtitulo">
        El Puerto de Santa María, EL JUNCAL
        <span id="boton_modal_mapa"><i class="fas fa-map-marker-alt"></i> map</span>
    </p>
    '''
    soup = BeautifulSoup(html, "lxml")
    result = _extract_direccion(soup)
    assert result == "El Puerto de Santa María, EL JUNCAL"


def test_extract_municipio():
    direccion = "El Puerto de Santa María, EL JUNCAL"
    assert _extract_municipio(direccion) == "El Puerto de Santa María"


def test_extract_barrio():
    direccion = "El Puerto de Santa María, EL JUNCAL"
    assert _extract_barrio(direccion) == "El Juncal"


# ── _extract_descripcion ─────────────────────────────────────────────────────


def test_extract_descripcion():
    long_text = "Casa reformada con jardín y piscina privada. " * 3
    html = f"<p id='inmueble2_descripcion_aut'>{long_text}</p>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_descripcion(soup) == long_text.strip()


def test_extract_descripcion_none_when_short():
    html = "<p id='inmueble2_descripcion_aut'>Casa corta</p>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_descripcion(soup) is None


# ── _extract_fotos_detail ────────────────────────────────────────────────────


def test_extract_fotos_detail():
    html = """
    <div id="carousel-img-principal">
      <div class="carousel-item">
        <img src="https://www.uriahomesinmobiliaria.com/fotos/1.jpg?auto=compress">
        <img src="https://www.uriahomesinmobiliaria.com/fotos/2.jpg?auto=compress">
        <img src="https://www.uriahomesinmobiliaria.com/fotos/3.jpg?auto=compress">
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    fotos = _extract_fotos_detail(soup)
    assert fotos == [
        "https://www.uriahomesinmobiliaria.com/fotos/1.jpg",
        "https://www.uriahomesinmobiliaria.com/fotos/2.jpg",
        "https://www.uriahomesinmobiliaria.com/fotos/3.jpg",
    ]


def test_extract_fotos_detail_dedupes():
    html = """
    <div id="carousel-img-principal">
      <div class="carousel-item">
        <img src="https://www.uriahomesinmobiliaria.com/fotos/1.jpg">
        <img src="https://www.uriahomesinmobiliaria.com/fotos/1.jpg?auto=compress&h=650">
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_fotos_detail(soup) == [
        "https://www.uriahomesinmobiliaria.com/fotos/1.jpg"
    ]


def test_extract_fotos_detail_empty():
    soup = BeautifulSoup("<html><body><p>no carousel</p></body></html>", "lxml")
    assert _extract_fotos_detail(soup) == []


# ── _extract_caracteristicas ─────────────────────────────────────────────────


def test_extract_caracteristicas():
    html = """
    <div id="inmueble2_caracteristicas_inmueble_container">
      <ul>
        <li>Kitchen equipped</li>
        <li>Fitted wardrobes</li>
        <li>Terrace</li>
      </ul>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_caracteristicas(soup) == [
        "cocina equipada",
        "armarios empotrados",
        "terraza",
    ]


def test_extract_caracteristicas_maps_english():
    html = """
    <div id="inmueble2_caracteristicas_inmueble_container">
      <ul><li>Reformed</li></ul>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    assert _extract_caracteristicas(soup) == ["reformado"]


def test_extract_caracteristicas_empty():
    soup = BeautifulSoup("<html><body><p>no container</p></body></html>", "lxml")
    assert _extract_caracteristicas(soup) == []


# ── _extract_energia ─────────────────────────────────────────────────────────


def test_extract_energia():
    html = "<div id='certificado_energetico_estado'><span>In process</span></div>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_energia(soup) == "In process"


def test_extract_energia_none():
    soup = BeautifulSoup("<html><body><p>no energia</p></body></html>", "lxml")
    assert _extract_energia(soup) is None


# ── _extract_coords_from_js ──────────────────────────────────────────────────


def test_extract_coords_from_js():
    js = """
    <script>
      cargar_mapa_ubicacion_aproximada("map2", 36.6085028, -6.2167529, 15);
    </script>
    """
    assert _extract_coords_from_js(js) == (36.6085028, -6.2167529)


def test_extract_coords_from_js_none():
    html = "<html><body><p>no coordinates</p></body></html>"
    assert _extract_coords_from_js(html) == (None, None)


# ── _map_feature ─────────────────────────────────────────────────────────────


def test_map_feature_english():
    assert _map_feature("Kitchen equipped") == "cocina equipada"


def test_map_feature_spanish():
    assert _map_feature("Reformado") == "reformado"


def test_map_feature_unknown():
    assert _map_feature("Something else") == "Something else"
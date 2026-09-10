"""Unit tests for scraper.geo_utils coordinate extractors."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.geo_utils import (
    coords_from_apinmo_json,
    coords_from_cargar_mapa,
    coords_from_gmaps_center,
    coords_from_leaflet_circle,
    coords_from_leaflet_marker,
)


# ── coords_from_cargar_mapa (InmoServer: UriaHomes, Alonsaga) ────────────────


def test_cargar_mapa_extracts_pair():
    html = '<script>cargar_mapa_ubicacion_aproximada("map2", 36.59869, -6.242444, "aprox");</script>'
    assert coords_from_cargar_mapa(html) == (36.59869, -6.242444)


def test_cargar_mapa_missing_returns_none_pair():
    assert coords_from_cargar_mapa("<p>no map</p>") == (None, None)


def test_cargar_mapa_empty_html():
    assert coords_from_cargar_mapa("") == (None, None)


# ── coords_from_apinmo_json (Inmovilla/apinmo: Neopolis, PuertoInmobiliaria) ──


def test_apinmo_json_uses_latitud_altitud_pair():
    html = '..."ref":"P01160","latitud":36.601470322,"altitud":-6.222046068,"tipomensual":"MES"...'
    assert coords_from_apinmo_json(html) == (36.601470322, -6.222046068)


def test_apinmo_json_falls_back_to_coordenadas_param():
    html = '<iframe src="//procesos.apinmo.com/externo/googleplano.php?individual=si&coordenadas=36.59532075,-6.23977881"></iframe>'
    assert coords_from_apinmo_json(html) == (36.59532075, -6.23977881)


def test_apinmo_json_missing_returns_none_pair():
    assert coords_from_apinmo_json("<p>nada</p>") == (None, None)


# ── coords_from_gmaps_center (PuertoPiso) ────────────────────────────────────


def test_gmaps_center_extracts_pair():
    html = "map = new google.maps.Map(el, { zoom: 15, center: {lat: 36.581592896, lng: -6.21914451} });"
    assert coords_from_gmaps_center(html) == (36.581592896, -6.21914451)


def test_gmaps_center_missing_returns_none_pair():
    assert coords_from_gmaps_center("center: {}") == (None, None)


# ── coords_from_leaflet_marker (PuntoHogar) ─────────────────────────────────


def test_leaflet_marker_extracts_pair():
    html = "var marker = L.marker([36.578221570278,-6.2230599455122]).addTo(map);"
    assert coords_from_leaflet_marker(html) == (36.578221570278, -6.2230599455122)


def test_leaflet_marker_missing_returns_none_pair():
    assert coords_from_leaflet_marker("<p>no marker</p>") == (None, None)


# ── coords_from_leaflet_circle (PuntoHogar approximate mode) ────────────────


def test_leaflet_circle_extracts_center_and_radius():
    html = """
    var map = L.map('map').setView([36.6121453, -6.2508307], 15);
    coords = [36.6121453, -6.2508307];
    var circle = L.circle(coords, { color: '#FF0000', radius: 250 }).addTo(map);
    """
    assert coords_from_leaflet_circle(html) == (36.6121453, -6.2508307, 250)


def test_leaflet_circle_missing_returns_none_triple():
    assert coords_from_leaflet_circle("var marker = L.marker([36.5, -6.2]);") == (
        None,
        None,
        None,
    )


def test_leaflet_circle_defaults_radius_when_absent():
    html = "coords = [36.60, -6.24];\nvar circle = L.circle(coords, {color:'red'}).addTo(map);"
    assert coords_from_leaflet_circle(html) == (36.60, -6.24, None)


def test_leaflet_circle_ignores_css_border_radius():
    html = """
    <style>.btn{border-radius:9999px}</style>
    coords = [36.6121453, -6.2508307];
    var circle = L.circle(coords, {color:'#FF0000', radius: 250}).addTo(map);
    """
    assert coords_from_leaflet_circle(html) == (36.6121453, -6.2508307, 250)


# ── sanity box rejects out-of-region / swapped values ───────────────────────


def test_out_of_range_values_rejected():
    # lat/lng swapped -> lat -6.2 is outside the El Puerto box
    html = '<script>cargar_mapa_ubicacion_aproximada("map2", -6.2230599, 36.5782215, "x");</script>'
    assert coords_from_cargar_mapa(html) == (None, None)


def test_zeroed_coords_rejected():
    html = "center: {lat: 0, lng: 0}"
    assert coords_from_gmaps_center(html) == (None, None)

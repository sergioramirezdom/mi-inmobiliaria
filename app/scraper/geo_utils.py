"""Shared helpers to pull map coordinates out of detail-page HTML.

Every portal embeds its map differently, so each extractor keys off the
exact JS/markup pattern of one CMS family. Keeping them separate stops a
page's "similar properties" widget from leaking a neighbour's point.

All extractors return a ``(lat, lng)`` tuple, or ``(None, None)`` when the
pattern is absent or the values fall outside the El Puerto de Santa María
sanity box (which also catches lat/lng swaps and zeroed placeholders).
"""
import re
from typing import Optional, Tuple

Coords = Tuple[Optional[float], Optional[float]]

_EMPTY: Coords = (None, None)

# Bounding box around El Puerto de Santa María (Cádiz) with generous margin.
_LAT_MIN, _LAT_MAX = 35.5, 37.5
_LNG_MIN, _LNG_MAX = -7.5, -5.0

_NUM = r"[-+]?\d+(?:\.\d+)?"


def _pair(lat_s: str, lng_s: str) -> Coords:
    try:
        lat, lng = float(lat_s), float(lng_s)
    except (TypeError, ValueError):
        return _EMPTY
    if _LAT_MIN <= lat <= _LAT_MAX and _LNG_MIN <= lng <= _LNG_MAX:
        return lat, lng
    return _EMPTY


def coords_from_cargar_mapa(html: str) -> Coords:
    """InmoServer CMS (UriaHomes, Alonsaga).

    Pattern: ``cargar_mapa_ubicacion_aproximada("map2", 36.6085, -6.2167, ...)``
    """
    if not html:
        return _EMPTY
    m = re.search(
        r"cargar_mapa_ubicacion_aproximada\([^,]+,\s*(" + _NUM + r"),\s*(" + _NUM + r")",
        html,
    )
    return _pair(m.group(1), m.group(2)) if m else _EMPTY


def coords_from_apinmo_json(html: str) -> Coords:
    """Inmovilla / apinmo CMS (Neopolis, PuertoInmobiliaria).

    Primary: the property record blob ``"latitud":36.60,"altitud":-6.22``
    (the ``altitud`` key actually carries the longitude on this CMS).
    Fallback: the googleplano iframe ``?coordenadas=LAT,LNG`` query param.
    """
    if not html:
        return _EMPTY
    m = re.search(
        r'"latitud"\s*:\s*"?(' + _NUM + r')"?\s*,\s*"altitud"\s*:\s*"?(' + _NUM + r')"?',
        html,
    )
    if m:
        coords = _pair(m.group(1), m.group(2))
        if coords != _EMPTY:
            return coords
    m = re.search(r"coordenadas=(" + _NUM + r"),(" + _NUM + r")", html)
    return _pair(m.group(1), m.group(2)) if m else _EMPTY


def coords_from_gmaps_center(html: str) -> Coords:
    """Google Maps ``initMap`` (PuertoPiso).

    Pattern: ``center: {lat: 36.5815, lng: -6.2191}``
    """
    if not html:
        return _EMPTY
    m = re.search(
        r"center\s*:\s*\{\s*lat\s*:\s*(" + _NUM + r")\s*,\s*lng\s*:\s*(" + _NUM + r")",
        html,
    )
    return _pair(m.group(1), m.group(2)) if m else _EMPTY


def coords_from_leaflet_marker(html: str) -> Coords:
    """Leaflet marker — PuntoHogar's *exact* mode.

    Pattern: ``L.marker([36.5782, -6.2230])``
    """
    if not html:
        return _EMPTY
    m = re.search(
        r"L\.marker\(\s*\[\s*(" + _NUM + r")\s*,\s*(" + _NUM + r")\s*\]",
        html,
    )
    return _pair(m.group(1), m.group(2)) if m else _EMPTY


def coords_from_leaflet_circle(
    html: str,
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """Leaflet circle — PuntoHogar's *approximate* mode (no marker).

    Pattern::

        coords = [36.6121453, -6.2508307];
        var circle = L.circle(coords, { color: '#FF0000', radius: 250 }).addTo(map);

    Returns ``(lat, lng, radius_m)``; ``radius_m`` is ``None`` when the
    circle carries no explicit radius. Returns ``(None, None, None)`` when
    there is no ``L.circle`` call (i.e. not the approximate mode).
    """
    if not html:
        return (None, None, None)
    circle_at = html.find("L.circle(")
    if circle_at == -1:
        return (None, None, None)
    m = re.search(r"coords\s*=\s*\[\s*(" + _NUM + r")\s*,\s*(" + _NUM + r")\s*\]", html)
    if not m:
        return (None, None, None)
    lat, lng = _pair(m.group(1), m.group(2))
    if lat is None:
        return (None, None, None)
    # Scope the radius lookup to the L.circle(...) options block so it can't
    # pick up a CSS `border-radius` elsewhere on the page.
    circle_segment = html[circle_at : circle_at + 400]
    radius_match = re.search(r"[^-\w]radius\s*:\s*(\d+)", circle_segment)
    radius = int(radius_match.group(1)) if radius_match else None
    return (lat, lng, radius)

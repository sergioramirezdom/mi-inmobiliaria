"""PuertoPiso detail scraper: approximate coordinate extraction (respx-mocked)."""
import os
import sys

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from scraper.puertopiso_scraper import PuertoPisoScraper

DETAIL_URL = "https://www.puertopiso.com/buscador/inmueble.php?id=29183740"

_BASE_HTML = """
<html><body>
  <div class="uno"><h4>Piso en El Puerto</h4><h4>150.000€</h4></div>
  {maps}
</body></html>
"""


def _page(maps: str) -> str:
    return _BASE_HTML.format(maps=maps)


@respx.mock
@pytest.mark.asyncio
async def test_extracts_approximate_coordinates_from_gmaps_center():
    html = _page(
        "<script>map = new google.maps.Map(el, "
        "{zoom: 15, center: {lat: 36.581592896, lng: -6.21914451}});</script>"
    )
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=html))

    data = await PuertoPisoScraper().scrape_property_details(DETAIL_URL)

    assert data["latitud"] == 36.581592896
    assert data["longitud"] == -6.21914451
    assert data["ubicacion_aproximada"] is True


@respx.mock
@pytest.mark.asyncio
async def test_no_map_leaves_location_unset():
    respx.get(DETAIL_URL).mock(return_value=httpx.Response(200, text=_page("")))

    data = await PuertoPisoScraper().scrape_property_details(DETAIL_URL)

    assert "latitud" not in data
    assert "ubicacion_aproximada" not in data

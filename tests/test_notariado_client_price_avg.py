"""Unit tests for the PUBLIC price-avg client (respx-mocked HTTP).

Sibling of tests/test_notariado_client.py; covers fetch_price_avg and the
ZONA_COMBOS vocabulary. No credentials are involved — this endpoint is public.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import httpx
import pytest
import respx

from scraper.notariado_client import (
    CONSTRUCTION_TYPES,
    COMBOS,
    PRICE_AVG_URL,
    PROPERTY_TYPES,
    ZONA_COMBOS,
    NotariadoPriceAvgError,
    fetch_price_avg,
)

GEOMETRY = {"rings": [[[0, 0], [0, 1], [1, 1], [0, 0]]], "spatialReference": {"wkid": 102100}}
WHERE = "(clase_finca_urbana_id = 14) AND (tipo_construccion_id = 7)"


def test_price_avg_url_is_apex_host():
    assert PRICE_AVG_URL == "https://penotariado.com/inmobiliario/rest/v1/public/price-avg"
    assert "://www." not in PRICE_AVG_URL


@respx.mock
def test_fetch_price_avg_returns_int_on_200():
    route = respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(200, json={"data": {"priceAvg": 1821}})
    )

    result = fetch_price_avg(GEOMETRY, WHERE)

    assert route.called
    assert result == 1821
    assert isinstance(result, int)


@respx.mock
def test_fetch_price_avg_body_has_exactly_geometry_and_where():
    route = respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(200, json={"data": {"priceAvg": 1500}})
    )

    fetch_price_avg(GEOMETRY, WHERE)

    request = route.calls.last.request
    assert "Authorization" not in request.headers
    body = json.loads(request.content.decode("utf-8"))
    assert set(body.keys()) == {"geometry", "where"}
    assert body["geometry"] == GEOMETRY
    assert body["where"] == WHERE


@respx.mock
def test_fetch_price_avg_returns_none_on_pav002():
    respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"errorType": "PAV002", "errorMessage": "not enough data"}},
        )
    )

    assert fetch_price_avg(GEOMETRY, WHERE) is None


@respx.mock
def test_fetch_price_avg_raises_on_non_pav002_400():
    respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(
            400, json={"error": {"errorType": "9909", "errorMessage": "bad request"}}
        )
    )

    with pytest.raises(NotariadoPriceAvgError) as exc_info:
        fetch_price_avg(GEOMETRY, WHERE)

    text = str(exc_info.value)
    assert "400" in text
    assert "9909" in text
    assert "rings" not in text


@respx.mock
def test_fetch_price_avg_raises_on_406_9929():
    respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(
            406, json={"error": {"errorType": "9929", "errorMessage": "not acceptable"}}
        )
    )

    with pytest.raises(NotariadoPriceAvgError):
        fetch_price_avg(GEOMETRY, WHERE)


@respx.mock
def test_fetch_price_avg_raises_on_500():
    respx.post(PRICE_AVG_URL).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(NotariadoPriceAvgError) as exc_info:
        fetch_price_avg(GEOMETRY, WHERE)

    assert "500" in str(exc_info.value)


@respx.mock
def test_fetch_price_avg_raises_on_network_error():
    respx.post(PRICE_AVG_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(NotariadoPriceAvgError):
        fetch_price_avg(GEOMETRY, WHERE)


@respx.mock
def test_fetch_price_avg_raises_on_unexpected_200_shape():
    respx.post(PRICE_AVG_URL).mock(
        return_value=httpx.Response(200, json={"data": {"somethingElse": 1}})
    )

    with pytest.raises(NotariadoPriceAvgError):
        fetch_price_avg(GEOMETRY, WHERE)


def test_zona_combos_has_exactly_four_entries():
    assert len(ZONA_COMBOS) == 4


def test_zona_combos_pairs_map_back_to_numeric_combos():
    seen_pairs = []
    for property_slug, construction_slug, where in ZONA_COMBOS:
        pcode = PROPERTY_TYPES[property_slug]
        ccode = CONSTRUCTION_TYPES[construction_slug]
        seen_pairs.append((pcode, ccode))
        assert where == (
            f"(clase_finca_urbana_id = {pcode}) AND (tipo_construccion_id = {ccode})"
        )
        assert pcode in (14, 15)
        assert ccode in (7, 9)
        assert "1=1" not in where.replace(" ", "")

    assert seen_pairs == COMBOS

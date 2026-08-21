"""Unit tests for notariado_client — ROPC auth + stats fetch (respx-mocked HTTP)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import httpx
import pytest
import respx

from scraper.notariado_client import (
    SSO_TOKEN_URL,
    STATS_URL,
    USERS_URL,
    CLIENT_ID,
    COMBOS,
    LOCATION_CODE,
    login,
    fetch_stats,
    fetch_quota,
    NotariadoAuthError,
)


@respx.mock
def test_login_posts_ropc_form():
    route = respx.post(SSO_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "fake-access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "refresh_token": "fake-refresh-token",
                "refresh_expires_in": 1800,
            },
        )
    )

    token = login("user@example.com", "s3cr3t")

    assert route.called
    request = route.calls.last.request
    assert "Authorization" not in request.headers
    form = dict(httpx.QueryParams(request.content.decode("utf-8")))
    assert form == {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": "user@example.com",
        "password": "s3cr3t",
        "scope": "openid profile email",
    }
    assert token == "fake-access-token"


@respx.mock
def test_login_redacts_credentials_on_401():
    respx.post(SSO_TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": "invalid_grant"})
    )

    with pytest.raises(NotariadoAuthError) as exc_info:
        login("secret-user@example.com", "sup3r-s3cr3t-pw")

    error_text = str(exc_info.value)
    assert "secret-user@example.com" not in error_text
    assert "sup3r-s3cr3t-pw" not in error_text


@respx.mock
def test_fetch_stats_sends_bearer_and_query_params():
    route = respx.get(STATS_URL).mock(
        return_value=httpx.Response(200, json={"currentPricePerSqm": 1500})
    )

    for property_type, construction_type in COMBOS:
        result = fetch_stats(
            "fake-token", LOCATION_CODE, property_type, construction_type
        )
        assert result == {"currentPricePerSqm": 1500}

    assert route.call_count == len(COMBOS)
    for call, (property_type, construction_type) in zip(route.calls, COMBOS):
        request = call.request
        assert request.headers["Authorization"] == "Bearer fake-token"
        params = dict(httpx.QueryParams(request.url.query.decode("utf-8")))
        assert params == {
            "lang": "es",
            "locationCode": LOCATION_CODE,
            "locationType": "MN",
            "propertyType": str(property_type),
            "constructionType": str(construction_type),
            "kpi": "pricePerSqm",
        }


@respx.mock
def test_fetch_quota_sends_bearer_and_returns_data_block():
    route = respx.get(USERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "email": "user@example.com",
                    "numberMonthlyQueries": 48,
                    "numberExtraQueries": 0,
                }
            },
        )
    )

    quota = fetch_quota("fake-token")

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer fake-token"
    assert quota == {
        "email": "user@example.com",
        "numberMonthlyQueries": 48,
        "numberExtraQueries": 0,
    }

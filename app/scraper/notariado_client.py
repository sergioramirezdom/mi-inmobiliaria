"""Thin HTTP client for the Consejo General del Notariado market-stats API.

Auth is a single Keycloak ROPC (`grant_type=password`) POST — no PKCE, no
redirect, no session cookies. Verified live 2026-08-21 against the `peni`
realm's `.well-known/openid-configuration` (`grant_types_supported` includes
`"password"`).

Credential handling: `email`/`password` are only ever placed in the outgoing
POST form body. They are never logged, never interpolated into a URL, and
never embedded in a raised exception's message.
"""

import httpx

SSO_TOKEN_URL = "https://sso.notariado.org/realms/peni/protocol/openid-connect/token"
STATS_URL = "https://www.penotariado.com/inmobiliario/rest/v1/private/statistics"
CLIENT_ID = "peni-oidc-js"

# Verified live 2026-08-21 (locationCode=11027). 99 = "Todos" (unused — the 4
# combos below are the only ones this ingestion fetches).
PROPERTY_TYPES = {"piso": 14, "casa": 15}
CONSTRUCTION_TYPES = {"obra_nueva": 7, "segunda_mano": 9}
COMBOS = [(14, 7), (14, 9), (15, 7), (15, 9)]
LOCATION_CODE = "11027"


class NotariadoAuthError(Exception):
    """Raised when Keycloak login fails. Never carries the raw credentials."""

    pass


def login(email: str, password: str, *, timeout: float = 30.0) -> str:
    """Single POST, ROPC grant. Returns the Bearer access_token (valid ~300s).

    Raises NotariadoAuthError on any non-2xx response. The exception message
    carries only the HTTP status code — never the email or password.
    """
    form = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "username": email,
        "password": password,
        "scope": "openid profile email",
    }
    try:
        response = httpx.post(SSO_TOKEN_URL, data=form, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise NotariadoAuthError(
            f"Notariado login failed with status {exc.response.status_code}"
        ) from None
    except httpx.HTTPError as exc:
        raise NotariadoAuthError(
            f"Notariado login request error: {type(exc).__name__}"
        ) from None

    return response.json()["access_token"]


def fetch_stats(
    token: str,
    location_code: str,
    property_type: int,
    construction_type: int,
    *,
    timeout: float = 30.0,
) -> dict:
    """GET STATS_URL with Authorization: Bearer <token> and the combo's query
    params. Returns the raw JSON body."""
    response = httpx.get(
        STATS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={
            "locationCode": location_code,
            "propertyType": property_type,
            "constructionType": construction_type,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()

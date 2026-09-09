"""Thin HTTP client for the Consejo General del Notariado market-stats API.

Auth is a single Keycloak ROPC (`grant_type=password`) POST — no PKCE, no
redirect, no session cookies. Verified live 2026-08-21 against the `peni`
realm's `.well-known/openid-configuration` (`grant_types_supported` includes
`"password"`).

Credential handling: `email`/`password` are only ever placed in the outgoing
POST form body. They are never logged, never interpolated into a URL, and
never embedded in a raised exception's message.
"""

from typing import Optional

import httpx

SSO_TOKEN_URL = "https://sso.notariado.org/realms/peni/protocol/openid-connect/token"
STATS_URL = "https://www.penotariado.com/inmobiliario/rest/v1/private/statistics"
USERS_URL = "https://www.penotariado.com/inmobiliario/rest/v1/private/users"
# Public price-avg endpoint. Apex host is pinned: a POST to www.penotariado.com
# 301-redirects and httpx does not follow redirects, so the body would be dropped.
PRICE_AVG_URL = "https://penotariado.com/inmobiliario/rest/v1/public/price-avg"
CLIENT_ID = "peni-oidc-js"

# Verified live 2026-08-21 (locationCode=11027). 99 = "Todos" (unused — the 4
# combos below are the only ones this ingestion fetches).
PROPERTY_TYPES = {"piso": 14, "casa": 15}
CONSTRUCTION_TYPES = {"obra_nueva": 7, "segunda_mano": 9}
COMBOS = [(14, 7), (14, 9), (15, 7), (15, 9)]
LOCATION_CODE = "11027"

# Public price-avg query vocabulary. Derived from PROPERTY_TYPES / CONSTRUCTION_TYPES
# so the numeric API ids stay single-sourced with COMBOS. Dicts are insertion
# ordered, so this yields exactly COMBOS order: piso x obra_nueva, piso x
# segunda_mano, casa x obra_nueva, casa x segunda_mano.
ZONA_COMBOS: list = [
    (
        property_slug,
        construction_slug,
        f"(clase_finca_urbana_id = {property_code}) AND "
        f"(tipo_construccion_id = {construction_code})",
    )
    for property_slug, property_code in PROPERTY_TYPES.items()
    for construction_slug, construction_code in CONSTRUCTION_TYPES.items()
]


class NotariadoAuthError(Exception):
    """Raised when Keycloak login fails. Never carries the raw credentials."""

    pass


class NotariadoPriceAvgError(Exception):
    """Raised when the public price-avg endpoint fails for a real reason:
    a non-PAV002 non-2xx response, a network/timeout error, or an
    unexpected JSON shape. The message carries only the HTTP status code
    and the API errorType — never the response body or the geometry.
    """

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
            "lang": "es",
            "locationCode": location_code,
            "locationType": "MN",
            "propertyType": property_type,
            "constructionType": construction_type,
            "kpi": "pricePerSqm",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def fetch_quota(token: str, *, timeout: float = 30.0) -> dict:
    """GET USERS_URL with Authorization: Bearer <token>. Returns the `data`
    block of the response, which carries `numberMonthlyQueries` /
    `numberExtraQueries` quota counters alongside account fields.

    Endpoint/field names verified live 2026-08-21 via authenticated devtools
    capture (see Engram obs #17): `{"data": {..., "numberMonthlyQueries": 48,
    "numberExtraQueries": 0, ...}}`.
    """
    response = httpx.get(
        USERS_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["data"]


def fetch_price_avg(
    geometry: dict, where: str, *, timeout: float = 30.0
) -> Optional[int]:
    """POST the PUBLIC price-avg endpoint and return the EUR/m2 average.

    Returns the int on HTTP 200, None when the API reports errorType
    "PAV002" (an area with limited data — an expected outcome, not a
    failure), and raises NotariadoPriceAvgError on any other non-2xx
    response, network/timeout error, or unexpected JSON shape.

    Public endpoint: no credentials are sent and no secret is read (the
    module's credential rules govern login() only). The request body has
    exactly the two top-level keys "geometry" and "where".
    """
    body = {"geometry": geometry, "where": where}
    try:
        response = httpx.post(PRICE_AVG_URL, json=body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise NotariadoPriceAvgError(
            f"price-avg request error: {type(exc).__name__}"
        ) from None

    if response.status_code == 400:
        error_type = None
        try:
            error_type = response.json().get("error", {}).get("errorType")
        except ValueError:
            error_type = None
        if error_type == "PAV002":
            return None
        raise NotariadoPriceAvgError(
            f"price-avg failed with status 400 (errorType={error_type})"
        )

    if not response.is_success:
        raise NotariadoPriceAvgError(
            f"price-avg failed with status {response.status_code}"
        )

    try:
        return int(response.json()["data"]["priceAvg"])
    except (ValueError, KeyError, TypeError) as exc:
        raise NotariadoPriceAvgError(
            "unexpected price-avg response shape"
        ) from None

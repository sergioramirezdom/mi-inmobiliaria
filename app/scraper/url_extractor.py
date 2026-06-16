"""Generic property data extractor for individual URLs."""

import re
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

_SOLD_KEYWORDS = ("vendido", "vendida", "reservado", "reservada")


async def extract_from_url(url: str) -> dict:
    """
    Fetch a property page and extract basic data.
    Always returns a dict — never raises.
    On HTTP/network error sets "error" key.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, verify=True, timeout=15) as client:
            response = await client.get(url, headers=BROWSER_HEADERS)
            if response.status_code == 404:
                return {"error": "URL no encontrada (404)"}
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}
            html = response.text
    except Exception as e:
        return {"error": str(e)}

    return _parse_html(html)


def _parse_html(html: str) -> dict:
    """Parse HTML and extract property fields. Pure function — no HTTP calls."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    lower_text = page_text.lower()
    data: dict = {}

    # Sold detection — check first 3000 chars
    for keyword in _SOLD_KEYWORDS:
        if keyword in lower_text[:3000]:
            return {"activa": False, "estado": keyword.capitalize()}

    # Price — meta tags first, then regex in page text
    for meta_name in ("og:price:amount", "product:price:amount", "price"):
        tag = (
            soup.find("meta", attrs={"property": meta_name})
            or soup.find("meta", attrs={"name": meta_name})
        )
        if tag and tag.get("content"):
            price = _parse_price(tag["content"])
            if price and price > 10_000:
                data["precio"] = price
                break

    if "precio" not in data:
        for m in re.finditer(r"([\d.,]+)\s*€", page_text):
            price = _parse_price(m.group(1))
            if price and price > 10_000:
                data["precio"] = price
                break

    # Title — og:title, then first <h1>
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        data["titulo"] = og_title["content"].strip()
    else:
        h1 = soup.find("h1")
        if h1:
            data["titulo"] = h1.get_text(strip=True)

    # Surface m² — first match < 2000
    m = re.search(r"(\d[\d.,]*)\s*m[²2]", page_text, re.IGNORECASE)
    if m:
        val = _parse_float(m.group(1))
        if val and val < 2000:
            data["superficie_m2"] = val

    # Rooms
    m = re.search(r"(\d+)\s*(?:hab|dormitor|dorm)", page_text, re.IGNORECASE)
    if m:
        data["habitaciones"] = int(m.group(1))

    # Bathrooms
    m = re.search(r"(\d+)\s*ba[ñn]", page_text, re.IGNORECASE)
    if m:
        data["banos"] = int(m.group(1))

    # Municipio — meta locality tags
    for meta_name in ("og:locality", "locality"):
        tag = (
            soup.find("meta", attrs={"property": meta_name})
            or soup.find("meta", attrs={"name": meta_name})
        )
        if tag and tag.get("content"):
            data["municipio"] = tag["content"].strip()
            break

    return data


def _parse_price(text: str) -> Optional[float]:
    """Parse European price string: '195.000' or '195.000,50' → float."""
    text = str(text).strip().replace(" ", "")
    if "." in text and "," in text:
        # Both: dot=thousands, comma=decimal → "195.000,50" → 195000.50
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and len(text.split(",")[-1]) == 3:
        # "195,000" → thousands separator (no decimal)
        text = text.replace(",", "")
    elif "." in text and len(text.split(".")[-1]) == 3:
        # "195.000" → thousands separator
        text = text.replace(".", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_float(text: str) -> Optional[float]:
    """Parse European decimal: '69,84' or '69.84' → 69.84"""
    text = str(text).strip()
    if "." in text and "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None

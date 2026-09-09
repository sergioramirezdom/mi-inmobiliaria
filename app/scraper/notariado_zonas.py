"""Explicit registry and loader for public notariado zona geometries.

Each zona is a barrio polygon stored verbatim (no reprojection or
simplification) as an ArcGIS geometry object in
``app/scraper/notariado_zonas/<slug>.json``. The registry is an explicit
list, never directory globbing, so an accidental stray file cannot enter a
run and the order stays reviewable.

The sibling data directory ``notariado_zonas/`` has no ``__init__.py`` on
purpose: it must not become an importable package that shadows this module.

Stdlib only — no DB, no httpx, no config import.
"""
import json
from pathlib import Path

_GEOMETRY_DIR = Path(__file__).parent / "notariado_zonas"

ZONA_SLUGS: list[str] = ["crevillet"]


class ZonaGeometryError(Exception):
    """Raised when a zona geometry file is unknown, missing, invalid JSON,
    or not a usable ArcGIS geometry object."""


def available_zonas() -> list[str]:
    """Return a fresh copy of the registered zona slugs."""
    return list(ZONA_SLUGS)


def load_zona_geometry(slug: str) -> dict:
    """Read ``notariado_zonas/<slug>.json`` and return the parsed ArcGIS
    geometry object verbatim.

    Raises ``ZonaGeometryError`` when the slug is not registered, the file
    is missing, the JSON is invalid, or the payload is not a geometry
    object (a dict carrying a non-empty ``rings`` list and a
    ``spatialReference`` dict).
    """
    if slug not in ZONA_SLUGS:
        raise ZonaGeometryError(f"unknown zona slug: {slug!r}")

    path = _GEOMETRY_DIR / f"{slug}.json"
    try:
        with open(path, encoding="utf-8") as handle:
            geometry = json.load(handle)
    except FileNotFoundError as exc:
        raise ZonaGeometryError(f"zona geometry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ZonaGeometryError(f"zona geometry file is not valid JSON: {path}") from exc

    if not isinstance(geometry, dict):
        raise ZonaGeometryError(f"zona geometry is not an object: {slug!r}")
    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        raise ZonaGeometryError(f"zona geometry has no rings: {slug!r}")
    if not isinstance(geometry.get("spatialReference"), dict):
        raise ZonaGeometryError(f"zona geometry has no spatialReference: {slug!r}")

    return geometry

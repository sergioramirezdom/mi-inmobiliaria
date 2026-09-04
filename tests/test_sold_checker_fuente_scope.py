"""S4: check_sold_properties() optional fuente_id scoping.

Mirrors tests/test_sold_checker_strikes.py — a fake Session double is used
because Propiedad has an ARRAY column SQLite's DDL compiler cannot render.
The double compiles each statement it receives and applies the fuente_id
predicate in Python so the scoped path is genuinely exercised, while the
omitted-parameter path must emit no fuente_id predicate at all.
"""
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from sqlalchemy.dialects import sqlite

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper import sold_checker


_FUENTE_ID_PREDICATE = re.compile(r"propiedad\.fuente_id\s*=\s*(\d+)")


class FilteringFakeSession:
    """Like test_sold_checker_strikes.FakeSession, but honours a fuente_id
    WHERE predicate on the first exec() (the propiedades query) so a scoped
    call really returns fewer rows."""

    def __init__(self, propiedades, fuentes):
        self._propiedades = propiedades
        self._fuentes = fuentes
        self._call = 0
        self.added = []
        self.commits = 0
        self.statements = []

    def exec(self, stmt):
        self._call += 1
        compiled = str(
            stmt.compile(
                dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.statements.append(compiled)
        result = MagicMock()
        if self._call == 1:
            props = self._propiedades
            match = _FUENTE_ID_PREDICATE.search(compiled)
            if match:
                fid = int(match.group(1))
                props = [p for p in props if p.fuente_id == fid]
            result.all.return_value = props
        else:
            result.all.return_value = self._fuentes
        return result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


def _prop(prop_id=1, fuente_id=1, intentos_fallidos=0, titulo="Piso en venta", precio=100000):
    prop = MagicMock()
    prop.id = prop_id
    prop.fuente_id = fuente_id
    prop.intentos_fallidos = intentos_fallidos
    prop.activa = True
    prop.estado = None
    prop.fecha_baja = None
    prop.titulo = titulo
    prop.precio = precio
    prop.precio_anterior = None
    prop.updated_at = None
    prop.url_original = f"http://example.com/{prop_id}"
    prop.fecha_scraping = None
    return prop


def _fuente(fuente_id=1, notas=None):
    fuente = MagicMock()
    fuente.id = fuente_id
    fuente.notas = notas
    return fuente


def _patch_scraper(monkeypatch, side_effect):
    fake_scraper = MagicMock()
    fake_scraper.scrape_property_details = AsyncMock(side_effect=side_effect)
    monkeypatch.setattr(sold_checker, "_get_scraper", lambda detail_type, config: fake_scraper)
    return fake_scraper


async def test_fuente_id_scopes_fetch_and_writes_single_row(monkeypatch):
    prop_a = _prop(prop_id=1, fuente_id=10)
    prop_b = _prop(prop_id=2, fuente_id=20)
    prop_c = _prop(prop_id=3, fuente_id=20)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 100000})
    session = FilteringFakeSession([prop_a, prop_b, prop_c], [_fuente(10), _fuente(20)])

    stats = await sold_checker.check_sold_properties(session, fuente_id=20)

    # Only fuente 20's active properties were re-fetched / checked.
    assert stats["total"] == 2
    assert set(stats["por_fuente"].keys()) == {20}
    assert prop_a.activa is True  # fuente 10 property was never touched

    # Exactly one sold_check RegistroEjecucion row, for fuente 20.
    registros = [o for o in session.added if type(o).__name__ == "RegistroEjecucion"]
    assert len(registros) == 1
    assert registros[0].fuente_id == 20
    assert registros[0].tipo == "sold_check"

    # The property query carried the fuente_id predicate.
    assert _FUENTE_ID_PREDICATE.search(session.statements[0]).group(1) == "20"


async def test_omitted_fuente_id_keeps_default_all_fuentes_path(monkeypatch):
    prop_a = _prop(prop_id=1, fuente_id=10)
    prop_b = _prop(prop_id=2, fuente_id=20)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 100000})
    session = FilteringFakeSession([prop_a, prop_b], [_fuente(10), _fuente(20)])

    stats = await sold_checker.check_sold_properties(session)

    assert stats["total"] == 2
    assert set(stats["por_fuente"].keys()) == {10, 20}

    registros = [o for o in session.added if type(o).__name__ == "RegistroEjecucion"]
    assert len(registros) == 2

    # No fuente_id predicate is emitted on the default path.
    assert _FUENTE_ID_PREDICATE.search(session.statements[0]) is None

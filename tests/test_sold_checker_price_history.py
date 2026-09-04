"""check_sold_properties() must record price changes (update precio,
precio_anterior, insert a PrecioHistorico row, append to bajadas_precio) for
EVERY source, not only detail_scraper_type == "manual_auto".

Regression for issue #1: the daily sold-check already fetches every active
property's detail page, but the price-change block was hard-gated to
manual_auto, so PrecioHistorico stayed incomplete for scraped sources and the
cumulative-drop math was understated.

Uses the same FakeSession / MagicMock property double as
tests/test_sold_checker_strikes.py (Propiedad has an ARRAY column SQLite's DDL
compiler cannot render).
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper import sold_checker


class FakeSession:
    def __init__(self, propiedades, fuentes):
        self._propiedades = propiedades
        self._fuentes = fuentes
        self._call = 0
        self.added = []
        self.commits = 0

    def exec(self, stmt):
        self._call += 1
        result = MagicMock()
        result.all.return_value = self._propiedades if self._call == 1 else self._fuentes
        return result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


def _prop(prop_id=1, fuente_id=1, titulo="Piso en venta", precio=100000):
    prop = MagicMock()
    prop.id = prop_id
    prop.fuente_id = fuente_id
    prop.intentos_fallidos = 0
    prop.activa = True
    prop.estado = None
    prop.fecha_baja = None
    prop.titulo = titulo
    prop.precio = precio
    prop.precio_anterior = None
    prop.updated_at = None
    prop.favorita = False
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


def _precio_historico_rows(session):
    return [o for o in session.added if type(o).__name__ == "PrecioHistorico"]


# fuente.notas carrying a real scraper type (NOT manual_auto)
_TULAR_NOTAS = '{"detail_scraper_type": "tular"}'


async def test_price_drop_recorded_for_non_manual_source(monkeypatch):
    prop = _prop(precio=200000)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 180000})
    session = FakeSession([prop], [_fuente(notas=_TULAR_NOTAS)])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.precio == 180000
    assert prop.precio_anterior == 200000
    rows = _precio_historico_rows(session)
    assert len(rows) == 1
    assert rows[0].precio == 180000
    assert rows[0].propiedad_id == prop.id
    assert len(stats["bajadas_precio"]) == 1
    assert stats["bajadas_precio"][0]["precio_anterior"] == 200000
    assert stats["bajadas_precio"][0]["precio_nuevo"] == 180000


async def test_price_rise_recorded_for_non_manual_source_but_not_in_bajadas(monkeypatch):
    prop = _prop(precio=100000)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 115000})
    session = FakeSession([prop], [_fuente(notas=_TULAR_NOTAS)])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.precio == 115000
    assert prop.precio_anterior == 100000
    assert len(_precio_historico_rows(session)) == 1
    assert "bajadas_precio" not in stats or stats["bajadas_precio"] == []


async def test_subthreshold_change_is_ignored_for_non_manual_source(monkeypatch):
    prop = _prop(precio=100000)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 100050})
    session = FakeSession([prop], [_fuente(notas=_TULAR_NOTAS)])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.precio == 100000
    assert prop.precio_anterior is None
    assert _precio_historico_rows(session) == []
    assert "bajadas_precio" not in stats or stats["bajadas_precio"] == []


async def test_manual_auto_source_still_records_price_drop(monkeypatch):
    prop = _prop(precio=200000)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 175000})
    session = FakeSession(
        [prop], [_fuente(notas='{"detail_scraper_type": "manual_auto"}')]
    )

    stats = await sold_checker.check_sold_properties(session)

    assert prop.precio == 175000
    assert len(_precio_historico_rows(session)) == 1
    assert len(stats["bajadas_precio"]) == 1

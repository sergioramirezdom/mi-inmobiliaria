"""Integration-style tests for check_sold_properties() routed through
classify_check_outcome()/apply_check_outcome() (T4). A fake Session double is
used because Propiedad has an ARRAY column SQLite's DDL compiler cannot
render (same constraint documented in tests/test_registro_ejecucion.py).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper import sold_checker


class FakeSession:
    """Records add/commit calls; returns preset results for the two
    session.exec() calls check_sold_properties() makes (propiedades, fuentes)."""

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


async def test_gone_deactivates_same_run_no_strike_needed(monkeypatch):
    prop = _prop(intentos_fallidos=0)
    _patch_scraper(monkeypatch, lambda url: {"activa": False, "estado": "Vendida"})
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is False
    assert prop.intentos_fallidos == 0
    assert stats["vendidas"] == 1
    assert len(stats["vendidas_lista"]) == 1


async def test_404_exception_maps_to_gone_and_deactivates(monkeypatch):
    prop = _prop(intentos_fallidos=0)

    async def raise_404(url):
        raise Exception("404 Client Error: Not Found for url: " + url)

    _patch_scraper(monkeypatch, raise_404)
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is False
    assert stats["vendidas"] == 1


async def test_first_empty_outcome_leaves_property_active_and_records_one_strike(monkeypatch):
    prop = _prop(intentos_fallidos=0)
    _patch_scraper(monkeypatch, lambda url: {})
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is True
    assert prop.intentos_fallidos == 1
    assert stats["vendidas"] == 0
    assert stats["sin_datos"] == 1


async def test_second_empty_outcome_deactivates_and_resets_counter(monkeypatch):
    prop = _prop(intentos_fallidos=1)
    _patch_scraper(monkeypatch, lambda url: {})
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is False
    assert prop.intentos_fallidos == 0
    assert stats["vendidas"] == 1


async def test_non_404_exception_does_not_touch_strike_or_activa_counts_as_error(monkeypatch):
    prop = _prop(intentos_fallidos=1)

    async def raise_timeout(url):
        raise Exception("Timeout while fetching detail page")

    _patch_scraper(monkeypatch, raise_timeout)
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is True
    assert prop.intentos_fallidos == 1
    assert stats["errores"] == 1
    assert stats["vendidas"] == 0


async def test_stats_are_grouped_per_fuente_for_run_log(monkeypatch):
    prop_a = _prop(prop_id=1, fuente_id=10, intentos_fallidos=0)
    prop_b = _prop(prop_id=2, fuente_id=20, intentos_fallidos=0)
    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 100000})
    session = FakeSession([prop_a, prop_b], [_fuente(10), _fuente(20)])

    stats = await sold_checker.check_sold_properties(session)

    assert stats["por_fuente"][10]["total"] == 1
    assert stats["por_fuente"][20]["total"] == 1
    assert stats["por_fuente"][10]["activas"] == 1
    assert stats["por_fuente"][20]["activas"] == 1


async def test_writes_one_registro_ejecucion_row_per_fuente_touched(monkeypatch):
    """T7: check_sold_properties() writes one RegistroEjecucion row per fuente,
    tipo="sold_check", with counts matching that fuente's returned stats."""
    prop_a = _prop(prop_id=1, fuente_id=10, intentos_fallidos=0)
    prop_b = _prop(prop_id=2, fuente_id=20, intentos_fallidos=0)
    prop_c = _prop(prop_id=3, fuente_id=20, intentos_fallidos=0)

    async def fetch(url):
        # prop_b's URL: ALIVE. prop_c's URL: EMPTY (first strike).
        if url.endswith("/2"):
            return {"titulo": "Piso", "precio": 100000}
        return {}

    _patch_scraper(monkeypatch, fetch)
    session = FakeSession([prop_a, prop_b, prop_c], [_fuente(10), _fuente(20)])
    # prop_a's URL also matches the fallback EMPTY branch — treat as a strike too.

    stats = await sold_checker.check_sold_properties(session)

    registros = [obj for obj in session.added if type(obj).__name__ == "RegistroEjecucion"]
    assert len(registros) == 2

    by_fuente = {r.fuente_id: r for r in registros}
    assert by_fuente[10].tipo == "sold_check"
    assert by_fuente[10].total == 1
    assert by_fuente[10].sin_datos == stats["por_fuente"][10]["sin_datos"]

    assert by_fuente[20].total == 2
    assert by_fuente[20].activas == stats["por_fuente"][20]["activas"]
    assert by_fuente[20].sin_datos == stats["por_fuente"][20]["sin_datos"]

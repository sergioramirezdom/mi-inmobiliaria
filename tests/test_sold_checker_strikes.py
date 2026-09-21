"""Integration-style tests for check_sold_properties() routed through
classify_check_outcome()/apply_check_outcome() (T4). A fake Session double is
used because Propiedad has an ARRAY column SQLite's DDL compiler cannot
render (same constraint documented in tests/test_registro_ejecucion.py).
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

import httpx

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

    def rollback(self):
        self.rollbacks = getattr(self, "rollbacks", 0) + 1


def _prop(prop_id=1, fuente_id=1, intentos_fallidos=0, titulo="Piso en venta", precio=100000):
    prop = MagicMock()
    prop.id = prop_id
    prop.fuente_id = fuente_id
    prop.intentos_fallidos = intentos_fallidos
    prop.activa = True
    prop.estado = None
    prop.estado_baja = None
    prop.ultimo_strike = None
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


def _http_error(status, url="http://example.com/1"):
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"HTTP {status} for {url}", request=request, response=httpx.Response(status, request=request)
    )


async def test_404_status_error_maps_to_gone_and_deactivates(monkeypatch):
    prop = _prop(intentos_fallidos=0)
    prop.estado = "segunda mano"

    async def raise_404(url):
        raise _http_error(404, url)

    _patch_scraper(monkeypatch, raise_404)
    session = FakeSession([prop], [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert prop.activa is False
    assert prop.estado == "segunda mano"
    assert prop.estado_baja == "No disponible"
    assert stats["vendidas"] == 1
    assert stats["vendidas_lista"][0]["estado"] == "No disponible"


async def test_410_status_error_deactivates(monkeypatch):
    prop = _prop()

    async def raise_410(url):
        raise _http_error(410, url)

    _patch_scraper(monkeypatch, raise_410)

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.activa is False
    assert stats["vendidas"] == 1


async def test_503_whose_url_contains_404_is_an_error_not_a_deactivation(monkeypatch):
    prop = _prop()
    prop.url_original = "https://x.es/inmueble/14042"

    async def raise_503(url):
        raise _http_error(503, url)

    _patch_scraper(monkeypatch, raise_503)

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.activa is True
    assert stats["vendidas"] == 0
    assert stats["errores"] == 1


async def test_text_only_404_exception_is_not_treated_as_gone(monkeypatch):
    prop = _prop()

    async def raise_text(url):
        raise Exception("404 Client Error: Not Found for url: " + url)

    _patch_scraper(monkeypatch, raise_text)

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.activa is True
    assert stats["errores"] == 1


async def test_failed_commit_on_gone_is_rolled_back_and_counted_as_error(monkeypatch):
    prop = _prop()

    async def raise_404(url):
        raise _http_error(404, url)

    _patch_scraper(monkeypatch, raise_404)
    session = FakeSession([prop], [_fuente()])

    def boom():
        raise RuntimeError("db went away")

    session.commit = boom

    stats = await sold_checker.check_sold_properties(session)

    assert session.rollbacks == 1
    assert stats["errores"] == 1


async def test_gone_result_from_scraper_keeps_estado_and_sets_estado_baja(monkeypatch):
    prop = _prop()
    prop.estado = "nuevo"
    _patch_scraper(monkeypatch, lambda url: {"activa": False, "estado": "Vendida"})

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.estado == "nuevo"
    assert prop.estado_baja == "Vendida"
    assert stats["vendidas_lista"][0]["estado"] == "Vendida"


async def test_empty_deactivation_alert_shows_the_sale_status(monkeypatch):
    prop = _prop(intentos_fallidos=1)
    prop.estado = "segunda mano"
    _patch_scraper(monkeypatch, lambda url: {})

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.activa is False
    assert stats["vendidas_lista"][0]["estado"] == "No disponible"
    assert prop.estado == "segunda mano"


async def test_second_empty_within_the_same_day_is_one_strike_only(monkeypatch):
    prop = _prop(intentos_fallidos=1)
    prop.ultimo_strike = datetime.utcnow() - timedelta(hours=1)
    _patch_scraper(monkeypatch, lambda url: {})

    stats = await sold_checker.check_sold_properties(FakeSession([prop], [_fuente()]))

    assert prop.activa is True
    assert prop.intentos_fallidos == 1
    assert stats["vendidas"] == 0


async def test_source_mostly_empty_deactivates_nothing_and_is_reported_failing(monkeypatch):
    # 6 listings of one fuente, all returning a placeholder page; two already
    # carry an old strike, so an unguarded run would deactivate them.
    props = [_prop(prop_id=n, intentos_fallidos=1 if n < 3 else 0) for n in range(1, 7)]
    for prop in props:
        prop.ultimo_strike = datetime.utcnow() - timedelta(days=2) if prop.intentos_fallidos else None
    _patch_scraper(monkeypatch, lambda url: {})
    session = FakeSession(props, [_fuente()])

    stats = await sold_checker.check_sold_properties(session)

    assert all(p.activa is True for p in props)
    assert all(p.intentos_fallidos in (0, 1) for p in props)
    assert stats["vendidas"] == 0
    assert 1 in stats["fuentes_fallidas"]
    registro = [o for o in session.added if type(o).__name__ == "RegistroEjecucion"][0]
    assert registro.errores >= 1
    assert registro.error_mensaje


async def test_healthy_source_with_isolated_empties_still_deactivates_after_a_confirmed_strike(monkeypatch):
    props = [_prop(prop_id=n) for n in range(1, 7)]
    props[0].intentos_fallidos = 1
    props[0].ultimo_strike = datetime.utcnow() - timedelta(days=2)

    async def fetch(url):
        return {} if url.endswith("/1") else {"titulo": "Piso", "precio": 100000}

    _patch_scraper(monkeypatch, fetch)

    stats = await sold_checker.check_sold_properties(FakeSession(props, [_fuente()]))

    assert props[0].activa is False
    assert stats["vendidas"] == 1
    assert stats["fuentes_fallidas"] == {}


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


async def test_registro_ejecucion_rows_share_one_run_id_per_check_sold_properties_call(monkeypatch):
    """All RegistroEjecucion rows written by a single check_sold_properties()
    call must share the same run_id (one per top-level cycle)."""
    prop_a = _prop(prop_id=1, fuente_id=10, intentos_fallidos=0)
    prop_b = _prop(prop_id=2, fuente_id=20, intentos_fallidos=0)

    _patch_scraper(monkeypatch, lambda url: {"titulo": "Piso", "precio": 100000})
    session = FakeSession([prop_a, prop_b], [_fuente(10), _fuente(20)])

    await sold_checker.check_sold_properties(session)

    registros = [obj for obj in session.added if type(obj).__name__ == "RegistroEjecucion"]
    assert len(registros) == 2
    run_ids = {r.run_id for r in registros}
    assert len(run_ids) == 1
    assert None not in run_ids

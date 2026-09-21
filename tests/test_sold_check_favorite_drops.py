"""ScraperScheduler.run_sold_check now consumes stats['bajadas_precio'] and
dispatches favourite drops with a generic label, while still sending the sold
alert."""
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import FiltroAlerta
from notifications.alert_routing import TIPO_BAJADAS_FAVORITAS
import scraper.scheduler as sched_mod
from scraper.scheduler import ScraperScheduler


class FakeNotifier:
    chat_id = "GLOBAL_CHAT"

    def __init__(self):
        self.sold_calls = []
        self.drop_calls = []

    async def send_sold_properties_alert(self, vendidas):
        self.sold_calls.append(vendidas)
        return True

    async def send_price_drop_alerts(self, bajadas, fuente=None, source_label=None, chat_id=None):
        self.drop_calls.append(
            dict(bajadas=bajadas, fuente=fuente, source_label=source_label, chat_id=chat_id)
        )
        return True


@pytest.fixture
def wired(monkeypatch):
    engine = create_engine("sqlite://")
    FiltroAlerta.__table__.create(engine)
    monkeypatch.setattr(sched_mod, "Session", lambda _e: Session(engine))

    fn = FakeNotifier()
    monkeypatch.setattr(sched_mod, "TelegramNotifier", lambda: fn)

    with Session(engine) as s:
        s.add(FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True))
        s.commit()

    return fn


def _stats():
    return {
        "vendidas_lista": [
            {"titulo": "Vendida", "url": "u0", "precio": 100000, "estado": "Vendida"}
        ],
        "bajadas_precio": [
            {"titulo": "Fav", "url": "u1", "precio_anterior": 200000, "precio_nuevo": 180000,
             "bajada_pct": 10, "propiedad_id": 1, "favorita": True},
            {"titulo": "Plain", "url": "u2", "precio_anterior": 300000, "precio_nuevo": 280000,
             "bajada_pct": 6.7, "propiedad_id": 2, "favorita": False},
        ],
    }


async def test_run_sold_check_dispatches_favorites_and_still_sends_sold(wired, monkeypatch):
    async def fake_check(session):
        return _stats()

    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)

    await ScraperScheduler().run_sold_check()

    assert len(wired.sold_calls) == 1
    # every drop goes to the global chat, the favourite subset to the alert
    assert len(wired.drop_calls) == 2
    global_call = next(c for c in wired.drop_calls if c["chat_id"] is None)
    assert [d["titulo"] for d in global_call["bajadas"]] == ["Fav", "Plain"]
    call = next(c for c in wired.drop_calls if c["chat_id"] == "GLOBAL_CHAT")
    assert [d["titulo"] for d in call["bajadas"]] == ["Fav"]
    assert call["fuente"] is None
    assert call["source_label"] == "favoritas"


async def test_run_sold_check_non_favorite_drops_reach_global_chat_only(wired, monkeypatch):
    async def fake_check(session):
        s = _stats()
        s["bajadas_precio"] = [d for d in s["bajadas_precio"] if not d["favorita"]]
        return s

    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)

    await ScraperScheduler().run_sold_check()

    assert len(wired.sold_calls) == 1
    assert [c["chat_id"] for c in wired.drop_calls] == [None]
    assert [d["titulo"] for d in wired.drop_calls[0]["bajadas"]] == ["Plain"]


async def test_run_sold_check_empty_bajadas_key_is_safe(wired, monkeypatch):
    async def fake_check(session):
        s = _stats()
        s.pop("bajadas_precio")
        return s

    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)

    await ScraperScheduler().run_sold_check()

    assert wired.drop_calls == []


async def test_failing_sold_alert_does_not_skip_the_price_drops(wired, monkeypatch):
    async def fake_check(session):
        return _stats()

    async def boom(vendidas):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)
    monkeypatch.setattr(wired, "send_sold_properties_alert", boom)

    summary = await ScraperScheduler().run_sold_check()

    assert len(wired.drop_calls) == 2
    assert summary.fatal_error is None


async def test_failed_global_drop_send_does_not_skip_favourite_fan_out(wired, monkeypatch):
    async def fake_check(session):
        return _stats()

    async def flaky(bajadas, fuente=None, source_label=None, chat_id=None):
        wired.drop_calls.append(dict(bajadas=bajadas, chat_id=chat_id))
        if chat_id is None:
            raise RuntimeError("boom")
        return True

    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)
    monkeypatch.setattr(wired, "send_price_drop_alerts", flaky)

    await ScraperScheduler().run_sold_check()

    assert [c["chat_id"] for c in wired.drop_calls] == [None, "GLOBAL_CHAT"]


async def test_run_summary_reports_failed_telegram_sends(wired, monkeypatch):
    async def fake_check(session):
        return _stats()

    wired.failed_count = 2
    monkeypatch.setattr(sched_mod, "check_sold_properties", fake_check)

    summary = await ScraperScheduler().run_sold_check()

    assert summary.notifications_failed == 2
    assert summary.ok  # a Telegram outage is reported, it does not fail the run

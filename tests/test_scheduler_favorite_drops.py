"""ScraperScheduler._send_favorite_drop_alerts: favorite-drop dispatch to
active `bajadas_favoritas` alerts, routed per-alert."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import FiltroAlerta
from notifications.alert_routing import TIPO_NUEVAS, TIPO_BAJADAS_FAVORITAS
import scraper.scheduler as sched_mod
from scraper.scheduler import ScraperScheduler


class FakeNotifier:
    chat_id = "GLOBAL_CHAT"

    def __init__(self):
        self.calls = []

    async def send_price_drop_alerts(self, bajadas, fuente=None, source_label=None, chat_id=None):
        self.calls.append(
            dict(bajadas=bajadas, fuente=fuente, source_label=source_label, chat_id=chat_id)
        )
        return True


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    FiltroAlerta.__table__.create(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def fake_notifier(monkeypatch):
    fn = FakeNotifier()
    monkeypatch.setattr(sched_mod, "TelegramNotifier", lambda: fn)
    return fn


def _drops():
    return [
        {"titulo": "Fav piso", "url": "u1", "precio_anterior": 200000,
         "precio_nuevo": 180000, "bajada_pct": 10, "propiedad_id": 1, "favorita": True},
        {"titulo": "Normal piso", "url": "u2", "precio_anterior": 300000,
         "precio_nuevo": 280000, "bajada_pct": 6.7, "propiedad_id": 2, "favorita": False},
    ]


async def test_favorite_subset_sent_only_to_bajadas_favoritas_alerts(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Nuevas", tipo_alerta=TIPO_NUEVAS, activo=True))
    session.add(FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True))
    session.commit()

    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(_drops(), session, fuente=SimpleNamespace(nombre="Fuente X"))

    assert len(fake_notifier.calls) == 1
    call = fake_notifier.calls[0]
    assert [d["titulo"] for d in call["bajadas"]] == ["Fav piso"]
    assert call["fuente"].nombre == "Fuente X"


async def test_no_send_when_no_favorite_drops(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True))
    session.commit()

    non_fav = [d for d in _drops() if not d["favorita"]]
    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(non_fav, session, fuente=SimpleNamespace(nombre="F"))

    assert fake_notifier.calls == []


async def test_no_send_when_no_bajadas_favoritas_alert(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Nuevas", tipo_alerta=TIPO_NUEVAS, activo=True))
    session.commit()

    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(_drops(), session, fuente=SimpleNamespace(nombre="F"))

    assert fake_notifier.calls == []


async def test_inactive_bajadas_favoritas_alert_is_skipped(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=False))
    session.commit()

    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(_drops(), session, fuente=SimpleNamespace(nombre="F"))

    assert fake_notifier.calls == []


async def test_routes_to_alert_own_chat_when_set_else_global(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Own", tipo_alerta=TIPO_BAJADAS_FAVORITAS,
                             activo=True, chat_id_telegram="-100777"))
    session.add(FiltroAlerta(nombre="Global", tipo_alerta=TIPO_BAJADAS_FAVORITAS,
                             activo=True, chat_id_telegram=None))
    session.commit()

    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(_drops(), session, fuente=SimpleNamespace(nombre="F"))

    chats = sorted(c["chat_id"] for c in fake_notifier.calls)
    assert chats == ["-100777", "GLOBAL_CHAT"]


async def test_sold_check_style_generic_label(session, fake_notifier):
    session.add(FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True))
    session.commit()

    sch = ScraperScheduler()
    await sch._send_favorite_drop_alerts(_drops(), session, fuente=None, source_label="favoritas")

    assert fake_notifier.calls[0]["fuente"] is None
    assert fake_notifier.calls[0]["source_label"] == "favoritas"

"""ScraperScheduler._send_favorite_drop_alerts: favorite-drop dispatch to
active `bajadas_favoritas` alerts, routed per-alert."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, create_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import FiltroAlerta, Propiedad
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


# ── _send_notifications: which alerts see new listings ───────────────────────


class _NewListingsSession(Session):
    """Real FiltroAlerta queries; the (ARRAY-column) Propiedad query is canned."""

    def __init__(self, engine, props):
        super().__init__(engine)
        self._props = props

    def exec(self, stmt, *args, **kwargs):
        if stmt.column_descriptions[0]["entity"] is Propiedad:
            return SimpleNamespace(all=lambda: self._props)
        return super().exec(stmt, *args, **kwargs)


class RecordingNotifier:
    chat_id = "GLOBAL_CHAT"

    def __init__(self):
        self.filtered = []
        self.no_matches = []
        self.summaries = []

    async def send_filtered_summary(self, fuente, stats, filtro_matches):
        self.filtered.append([(f.nombre, len(p)) for f, p in filtro_matches])
        return True

    async def send_no_matches_summary(self, fuente, stats, num_filtros):
        self.no_matches.append(num_filtros)
        return True

    async def send_scraping_summary(self, stats, fuente, filtros_aplicados=None):
        self.summaries.append(stats)
        return True


def _new_prop():
    return Propiedad(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="t",
        titulo="Piso", precio=100000.0, tipo_operacion="venta",
    )


@pytest.fixture
def notif_engine():
    engine = create_engine("sqlite://")
    FiltroAlerta.__table__.create(engine)
    return engine


@pytest.fixture
def recording(monkeypatch):
    rn = RecordingNotifier()
    monkeypatch.setattr(sched_mod, "TelegramNotifier", lambda: rn)
    return rn


async def _run_notifications(engine, filtros, props):
    with Session(engine) as s:
        for f in filtros:
            s.add(f)
        s.commit()
    with _NewListingsSession(engine, props) as s:
        await ScraperScheduler()._send_notifications(
            SimpleNamespace(id=1, nombre="Fuente X"), {"nuevas": len(props)}, s
        )


async def test_bajadas_favoritas_alert_never_gets_new_listing_messages(notif_engine, recording):
    await _run_notifications(
        notif_engine,
        [FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True)],
        [_new_prop()],
    )

    assert recording.filtered == []
    # with no "nuevas" alert at all the run falls back to the plain summary
    assert len(recording.summaries) == 1


async def test_no_matches_summary_counts_only_nuevas_alerts(notif_engine, recording):
    await _run_notifications(
        notif_engine,
        [
            FiltroAlerta(nombre="Favs", tipo_alerta=TIPO_BAJADAS_FAVORITAS, activo=True),
            FiltroAlerta(nombre="Caro", tipo_alerta=TIPO_NUEVAS, activo=True,
                         criterios_json=json.dumps({"precio_min": 999999})),
        ],
        [_new_prop()],
    )

    assert recording.filtered == []
    assert recording.no_matches == [1]


async def test_filter_with_year_built_does_not_block_other_filters(notif_engine, recording):
    await _run_notifications(
        notif_engine,
        [
            FiltroAlerta(nombre="Legacy", tipo_alerta=TIPO_NUEVAS, activo=True,
                         criterios_json=json.dumps({"año_construccion_min": 2000})),
            FiltroAlerta(nombre="Barato", tipo_alerta=TIPO_NUEVAS, activo=True,
                         criterios_json=json.dumps({"precio_max": 200000})),
        ],
        [_new_prop()],
    )

    assert recording.filtered == [[("Barato", 1)]]


async def test_a_filter_that_raises_is_skipped_and_others_still_notify(
    notif_engine, recording, monkeypatch
):
    real = sched_mod.FilterMatcher.get_matching_properties

    def flaky(props, filtro):
        if filtro.nombre == "Roto":
            raise RuntimeError("boom")
        return real(props, filtro)

    monkeypatch.setattr(sched_mod.FilterMatcher, "get_matching_properties", flaky)
    await _run_notifications(
        notif_engine,
        [
            FiltroAlerta(nombre="Roto", tipo_alerta=TIPO_NUEVAS, activo=True,
                         criterios_json="{}"),
            FiltroAlerta(nombre="Sano", tipo_alerta=TIPO_NUEVAS, activo=True,
                         criterios_json="{}"),
        ],
        [_new_prop()],
    )

    assert recording.filtered == [[("Sano", 1)]]

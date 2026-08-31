"""FiltroAlerta.tipo_alerta field: default and persisted value."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, create_engine

from db.models import FiltroAlerta
from notifications.alert_routing import TIPO_NUEVAS, TIPO_BAJADAS_FAVORITAS


def _session():
    engine = create_engine("sqlite://")
    FiltroAlerta.__table__.create(engine)
    return Session(engine)


def test_tipo_alerta_defaults_to_nuevas_on_new_alert():
    with _session() as s:
        f = FiltroAlerta(nombre="Sin tipo")
        s.add(f)
        s.commit()
        s.refresh(f)
        assert f.tipo_alerta == TIPO_NUEVAS == "nuevas"


def test_tipo_alerta_persists_bajadas_favoritas():
    with _session() as s:
        f = FiltroAlerta(nombre="Favoritas", tipo_alerta=TIPO_BAJADAS_FAVORITAS)
        s.add(f)
        s.commit()
        s.refresh(f)
        assert f.tipo_alerta == "bajadas_favoritas"

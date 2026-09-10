"""Unit tests for UbicacionAproximadaCRUD (in-memory SQLite)."""
import os
import sys

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from db.database import UbicacionAproximadaCRUD
from db.models import UbicacionAproximada


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[UbicacionAproximada.__table__])
    with Session(engine) as s:
        yield s


def test_marcar_aproximada_inserts_row(session):
    row = UbicacionAproximadaCRUD.marcar_aproximada(session, propiedad_id=42)

    assert row.propiedad_id == 42
    assert row.aproximada is True
    assert row.radio_m == 300
    assert row.id is not None


def test_marcar_aproximada_custom_radius(session):
    row = UbicacionAproximadaCRUD.marcar_aproximada(session, 7, radio_m=500)
    assert row.radio_m == 500


def test_marcar_aproximada_is_idempotent_by_propiedad(session):
    first = UbicacionAproximadaCRUD.marcar_aproximada(session, 99, radio_m=300)
    second = UbicacionAproximadaCRUD.marcar_aproximada(session, 99, radio_m=750)

    assert first.id == second.id
    assert second.radio_m == 750
    assert len(session.exec(select(UbicacionAproximada)).all()) == 1


def test_get_by_propiedad_returns_none_when_absent(session):
    assert UbicacionAproximadaCRUD.get_by_propiedad(session, 1) is None

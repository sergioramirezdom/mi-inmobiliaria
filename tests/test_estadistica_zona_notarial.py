"""Tests for the EstadisticaZonaNotarial model and its CRUD helper.

Append-only public price-avg series, one row per
(zona, property_type, construction_type) whenever the outcome pair
(sin_datos, price_avg) changes. Uses the per-model SQLite table-create
pattern (never ``SQLModel.metadata.create_all`` — ``Propiedad``'s ARRAY
column is not SQLite-compatible), mirroring
``tests/test_estadistica_notarial_model.py``.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import Session, create_engine

from db.models import EstadisticaZonaNotarial
from db.database import EstadisticaZonaNotarialCRUD

WHERE_CLAUSE = "(clase_finca_urbana_id = 14) AND (tipo_construccion_id = 7)"


def _memory_engine():
    engine = create_engine("sqlite:///:memory:")
    EstadisticaZonaNotarial.__table__.create(bind=engine, checkfirst=True)
    return engine


def test_data_row_round_trips():
    engine = _memory_engine()
    with Session(engine) as session:
        row = EstadisticaZonaNotarial(
            zona="crevillet",
            property_type="piso",
            construction_type="obra_nueva",
            price_avg=1741.0,
            sin_datos=False,
            where_clause=WHERE_CLAUSE,
        )
        created = EstadisticaZonaNotarialCRUD.create(session, row)

        assert created.id is not None
        assert created.price_avg == 1741.0
        assert isinstance(created.price_avg, float)
        assert created.sin_datos is False
        assert created.where_clause == WHERE_CLAUSE
        assert isinstance(created.captured_at, datetime)


def test_no_data_row_round_trips():
    engine = _memory_engine()
    with Session(engine) as session:
        row = EstadisticaZonaNotarial(
            zona="crevillet",
            property_type="casa",
            construction_type="segunda_mano",
            price_avg=None,
            sin_datos=True,
            where_clause=WHERE_CLAUSE,
        )
        created = EstadisticaZonaNotarialCRUD.create(session, row)

        assert created.price_avg is None
        assert created.sin_datos is True


def test_model_has_exactly_eight_fields_and_no_raw_json():
    field_names = set(EstadisticaZonaNotarial.model_fields)

    assert field_names == {
        "id",
        "zona",
        "property_type",
        "construction_type",
        "price_avg",
        "sin_datos",
        "where_clause",
        "captured_at",
    }
    assert "raw_json" not in field_names
    assert not hasattr(EstadisticaZonaNotarial(zona="z", property_type="p",
                                               construction_type="c",
                                               where_clause=WHERE_CLAUSE), "raw_json")


def test_get_latest_for_zona_combo_returns_none_when_empty():
    engine = _memory_engine()
    with Session(engine) as session:
        latest = EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
            session, "crevillet", "piso", "obra_nueva"
        )
        assert latest is None


def test_get_latest_for_zona_combo_returns_most_recent_by_captured_at():
    engine = _memory_engine()
    with Session(engine) as session:
        older = EstadisticaZonaNotarial(
            zona="crevillet",
            property_type="piso",
            construction_type="obra_nueva",
            price_avg=1700.0,
            sin_datos=False,
            where_clause=WHERE_CLAUSE,
            captured_at=datetime(2026, 1, 1),
        )
        newer = EstadisticaZonaNotarial(
            zona="crevillet",
            property_type="piso",
            construction_type="obra_nueva",
            price_avg=1900.0,
            sin_datos=False,
            where_clause=WHERE_CLAUSE,
            captured_at=datetime(2026, 6, 1),
        )
        # Insert out of chronological order to prove the ORDER BY, not insertion order.
        EstadisticaZonaNotarialCRUD.create(session, newer)
        EstadisticaZonaNotarialCRUD.create(session, older)

        latest = EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
            session, "crevillet", "piso", "obra_nueva"
        )
        assert latest is not None
        assert latest.price_avg == 1900.0


def test_get_latest_for_zona_combo_is_combo_scoped():
    engine = _memory_engine()
    with Session(engine) as session:
        EstadisticaZonaNotarialCRUD.create(
            session,
            EstadisticaZonaNotarial(
                zona="crevillet",
                property_type="piso",
                construction_type="obra_nueva",
                price_avg=1741.0,
                sin_datos=False,
                where_clause=WHERE_CLAUSE,
            ),
        )

        other_combo = EstadisticaZonaNotarialCRUD.get_latest_for_zona_combo(
            session, "crevillet", "casa", "segunda_mano"
        )
        assert other_combo is None

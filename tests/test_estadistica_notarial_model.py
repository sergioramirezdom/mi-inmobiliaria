"""Tests for the EstadisticaNotarial model and its CRUD helper."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import create_engine, Session

from db.models import EstadisticaNotarial
from db.database import EstadisticaNotarialCRUD


def _memory_engine():
    return create_engine("sqlite:///:memory:")


def _create_table(engine):
    EstadisticaNotarial.__table__.create(bind=engine, checkfirst=True)


def test_create_and_query_by_combo():
    engine = _memory_engine()
    _create_table(engine)
    with Session(engine) as session:
        row = EstadisticaNotarial(
            location_code="11027",
            property_type="piso",
            construction_type="obra_nueva",
            current_price_per_sqm=1500.5,
            current_number_of_sales=12,
            current_average_price=180000.0,
            current_average_area_sqm=95.0,
            rate_price_change=2.3,
            last_data_update=datetime(2026, 6, 1),
            report_date=datetime(2026, 8, 1),
            raw_json='{"currentPricePerSqm": 1500.5}',
        )

        created = EstadisticaNotarialCRUD.create(session, row)

        assert created.id is not None
        assert created.location_code == "11027"
        assert created.property_type == "piso"
        assert created.construction_type == "obra_nueva"
        assert created.current_price_per_sqm == 1500.5
        assert created.raw_json == '{"currentPricePerSqm": 1500.5}'

        results = EstadisticaNotarialCRUD.get_by_combo(
            session, "11027", "piso", "obra_nueva"
        )
        assert len(results) == 1
        assert results[0].id == created.id


def test_get_by_combo_returns_empty_for_unknown_combo():
    engine = _memory_engine()
    _create_table(engine)
    with Session(engine) as session:
        results = EstadisticaNotarialCRUD.get_by_combo(
            session, "11027", "casa", "segunda_mano"
        )
        assert results == []

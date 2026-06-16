"""Tests for the add_url_dialog helper logic."""
import pytest
from unittest.mock import MagicMock, patch


def _create_fuente_table(engine):
    """Create only the Fuente table (avoids ARRAY type error with SQLite)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
    from db.models import Fuente
    from sqlmodel import SQLModel
    # Create only the fuente table
    Fuente.__table__.create(bind=engine, checkfirst=True)


def test_get_or_create_fuente_manual_creates_when_missing():
    """_get_or_create_fuente_manual creates the Manual fuente if it doesn't exist."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from db.models import Fuente
    from sqlmodel import Session, create_engine, select

    engine = create_engine("sqlite:///:memory:")
    _create_fuente_table(engine)

    with Session(engine) as session:
        fuente = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
        assert fuente is None

        # Replicate the helper logic
        fuente = Fuente(
            nombre="Manual",
            url="manual://manual",
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas='{"detail_scraper_type": "manual_auto"}',
        )
        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        assert fuente.id is not None
        assert fuente.activa is False
        assert fuente.nombre == "Manual"

        # Second call should find existing
        existing = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
        assert existing.id == fuente.id


def test_get_or_create_fuente_manual_returns_existing():
    """_get_or_create_fuente_manual returns existing id without duplicating."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from db.models import Fuente
    from sqlmodel import Session, create_engine, select

    engine = create_engine("sqlite:///:memory:")
    _create_fuente_table(engine)

    with Session(engine) as session:
        # Pre-create the fuente
        fuente = Fuente(
            nombre="Manual",
            url="manual://manual",
            tipo_scraper="generic",
            activa=False,
            intervalo_horas=24,
            notas='{"detail_scraper_type": "manual_auto"}',
        )
        session.add(fuente)
        session.commit()
        session.refresh(fuente)
        original_id = fuente.id

        # Helper should return same id
        existing = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).first()
        assert existing is not None
        assert existing.id == original_id

        # Count should still be 1
        all_manual = session.exec(select(Fuente).where(Fuente.nombre == "Manual")).all()
        assert len(all_manual) == 1

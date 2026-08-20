"""Tests for the RegistroEjecucion model and Propiedad.intentos_fallidos field.

Scope for this batch (PR1): model layer only. RegistroEjecucionCRUD and
call-site wiring (writers) land in PR2 (T4/T5/T6.3/T7/T8).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlmodel import create_engine, Session

from db.models import Propiedad, RegistroEjecucion, Fuente


def _memory_engine():
    return create_engine("sqlite:///:memory:")


def _create_fuente_and_registro_tables(engine):
    # Only Fuente + RegistroEjecucion; avoids Propiedad's ARRAY columns,
    # which SQLite's DDL compiler can't render (same pattern as
    # tests/test_propiedades_url_dialog.py).
    Fuente.__table__.create(bind=engine, checkfirst=True)
    RegistroEjecucion.__table__.create(bind=engine, checkfirst=True)


def test_propiedad_has_intentos_fallidos_defaulting_to_zero():
    # Propiedad has an ARRAY column (fotos) that SQLite's DDL compiler can't
    # render, so this checks the model contract directly (no table creation
    # needed) rather than a round-trip through a SQLite table.
    prop = Propiedad(
        hash_unico="abc123",
        url_original="http://example.com/1/prop",
        fuente_id=1,
        origen_web="Test",
        titulo="Piso en venta",
    )
    assert prop.intentos_fallidos == 0


def test_registro_ejecucion_table_creates_and_persists_a_row():
    engine = _memory_engine()
    _create_fuente_and_registro_tables(engine)
    with Session(engine) as session:
        fuente = Fuente(nombre="Test", url="http://example.com/2")
        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        registro = RegistroEjecucion(
            fuente_id=fuente.id,
            tipo="sold_check",
            total=10,
            activas=8,
            vendidas=1,
            sin_datos=1,
            errores=0,
            duracion_segundos=3.5,
        )
        session.add(registro)
        session.commit()
        session.refresh(registro)

        assert registro.id is not None
        assert registro.fuente_id == fuente.id
        assert registro.tipo == "sold_check"
        assert registro.total == 10
        assert registro.vendidas == 1
        assert registro.sin_datos == 1
        assert registro.fecha is not None


def test_registro_ejecucion_nuevas_duplicadas_are_optional_for_sold_check_rows():
    engine = _memory_engine()
    _create_fuente_and_registro_tables(engine)
    with Session(engine) as session:
        fuente = Fuente(nombre="Test", url="http://example.com/3")
        session.add(fuente)
        session.commit()
        session.refresh(fuente)

        registro = RegistroEjecucion(fuente_id=fuente.id, tipo="scrape", total=5, nuevas=2, duplicadas=3, errores=0)
        session.add(registro)
        session.commit()
        session.refresh(registro)

        assert registro.nuevas == 2
        assert registro.duplicadas == 3
        assert registro.vendidas is None
        assert registro.sin_datos is None

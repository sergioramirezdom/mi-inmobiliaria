"""Tests for the single listing-date resolver (app/listing_date.py).

Three shapes must agree on the same inputs: ORM object / dict, SQLAlchemy
column expression, pandas column.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Propiedad
from listing_date import es_candidato_backfill, fecha_listado, fecha_listado_col, with_fecha_listado

SCRAPING = datetime(2026, 1, 1, 12, 0, 0)
PUBLICACION = datetime(2025, 12, 1, 9, 0, 0)


def _prop(**kw):
    defaults = dict(
        id=1, hash_unico="x", url_original="https://example.com/1", fuente_id=1,
        origen_web="example.com", titulo="Piso", fecha_scraping=SCRAPING,
    )
    defaults.update(kw)
    return Propiedad(**defaults)


# ── fecha_listado (ORM + dict) ──────────────────────────────────────────

@pytest.mark.parametrize("fecha_publicacion,esperado", [
    (None, SCRAPING),
    (PUBLICACION, PUBLICACION),
])
def test_fecha_listado_orm(fecha_publicacion, esperado):
    prop = _prop(fecha_publicacion=fecha_publicacion)
    assert fecha_listado(prop) == esperado


@pytest.mark.parametrize("fecha_publicacion,esperado", [
    (None, SCRAPING),
    (PUBLICACION, PUBLICACION),
])
def test_fecha_listado_dict(fecha_publicacion, esperado):
    d = {"fecha_scraping": SCRAPING, "fecha_publicacion": fecha_publicacion}
    assert fecha_listado(d) == esperado


def test_fecha_listado_dict_sin_clave_publicacion():
    """Un dict que ni siquiera trae la clave (p.ej. dict antiguo) usa el fallback."""
    assert fecha_listado({"fecha_scraping": SCRAPING}) == SCRAPING


# ── fecha_listado_col (SQLAlchemy) ──────────────────────────────────────

def test_fecha_listado_col_es_coalesce():
    from sqlalchemy import func
    esperado = func.coalesce(Propiedad.fecha_publicacion, Propiedad.fecha_scraping)
    assert fecha_listado_col().compare(esperado)


def test_fecha_listado_col_compila_en_order_by():
    from sqlmodel import select
    stmt = select(Propiedad).order_by(fecha_listado_col().desc())
    assert "coalesce" in str(stmt).lower()


# ── with_fecha_listado (pandas) ──────────────────────────────────────────

def test_with_fecha_listado_agrega_columna():
    df = pd.DataFrame([
        {"id": 1, "fecha_scraping": SCRAPING, "fecha_publicacion": None},
        {"id": 2, "fecha_scraping": SCRAPING, "fecha_publicacion": PUBLICACION},
    ])
    out = with_fecha_listado(df)
    assert out.loc[out["id"] == 1, "fecha_listado"].iloc[0] == pd.Timestamp(SCRAPING)
    assert out.loc[out["id"] == 2, "fecha_listado"].iloc[0] == pd.Timestamp(PUBLICACION)


def test_with_fecha_listado_sin_columna_publicacion():
    df = pd.DataFrame([{"id": 1, "fecha_scraping": SCRAPING}])
    out = with_fecha_listado(df)
    assert out.loc[0, "fecha_listado"] == pd.Timestamp(SCRAPING)


def test_with_fecha_listado_df_vacio():
    df = pd.DataFrame(columns=["id", "fecha_scraping", "fecha_publicacion"])
    out = with_fecha_listado(df)
    assert out.empty
    assert "fecha_listado" in out.columns


# ── Las 3 formas concuerdan ────────────────────────────────────────────

@pytest.mark.parametrize("fecha_publicacion,esperado", [
    (None, SCRAPING),
    (PUBLICACION, PUBLICACION),
])
def test_las_tres_formas_coinciden(fecha_publicacion, esperado):
    prop = _prop(fecha_publicacion=fecha_publicacion)
    d = {"fecha_scraping": SCRAPING, "fecha_publicacion": fecha_publicacion}
    df = with_fecha_listado(pd.DataFrame([d]))
    assert fecha_listado(prop) == esperado
    assert fecha_listado(d) == esperado
    assert df.loc[0, "fecha_listado"] == pd.Timestamp(esperado)


# ── es_candidato_backfill ─────────────────────────────────────────────

def test_backfill_23h_es_candidato():
    fuente_created = datetime(2026, 1, 1, 0, 0, 0)
    assert es_candidato_backfill(fuente_created + timedelta(hours=23), fuente_created) is True


def test_backfill_25h_no_es_candidato():
    fuente_created = datetime(2026, 1, 1, 0, 0, 0)
    assert es_candidato_backfill(fuente_created + timedelta(hours=25), fuente_created) is False


def test_backfill_exactamente_24h_es_candidato():
    """Límite inclusive: exactamente el umbral cuenta como candidato."""
    fuente_created = datetime(2026, 1, 1, 0, 0, 0)
    assert es_candidato_backfill(fuente_created + timedelta(hours=24), fuente_created) is True


def test_backfill_umbral_personalizado():
    fuente_created = datetime(2026, 1, 1, 0, 0, 0)
    assert es_candidato_backfill(fuente_created + timedelta(hours=2), fuente_created, umbral_horas=1) is False


def test_backfill_sin_fecha_no_es_candidato():
    assert es_candidato_backfill(None, datetime(2026, 1, 1)) is False

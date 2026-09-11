"""ZonaPoligono model, CRUD, resolver, and scraper wiring."""
import os
import sys
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from db.database import ZonaPoligonoCRUD
from db.models import Propiedad, ZonaPoligono
from scraper.runner import ScraperRunner

# Square around central El Puerto de Santa María (GeoJSON lon/lat).
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [
            [-6.240, 36.590],
            [-6.220, 36.590],
            [-6.220, 36.605],
            [-6.240, 36.605],
            [-6.240, 36.590],
        ]
    ],
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[ZonaPoligono.__table__])
    with Session(engine) as s:
        yield s


# ── model + CRUD ───────────────────────────────────────────────────────────


def test_crear_roundtrips_geojson(session):
    zona = ZonaPoligonoCRUD.crear(session, "Centro", SQUARE, color="#3388ff")

    assert zona.id is not None
    assert zona.nombre == "Centro"
    assert zona.geometria == SQUARE
    assert zona.activo is True


def test_listar_only_active_by_default(session):
    ZonaPoligonoCRUD.crear(session, "Activa", SQUARE)
    inactiva = ZonaPoligonoCRUD.crear(session, "Inactiva", SQUARE)
    inactiva.activo = False
    session.add(inactiva)
    session.commit()

    nombres = [z.nombre for z in ZonaPoligonoCRUD.listar(session)]
    assert nombres == ["Activa"]
    assert len(ZonaPoligonoCRUD.listar(session, solo_activos=False)) == 2


def test_get_by_id(session):
    zona = ZonaPoligonoCRUD.crear(session, "Centro", SQUARE)
    assert ZonaPoligonoCRUD.get(session, zona.id).nombre == "Centro"
    assert ZonaPoligonoCRUD.get(session, 999) is None


# ── resolver_id ────────────────────────────────────────────────────────────


def test_resolver_id_point_inside(session):
    zona = ZonaPoligonoCRUD.crear(session, "Centro", SQUARE)
    poligonos = ZonaPoligonoCRUD.listar(session)
    assert ZonaPoligonoCRUD.resolver_id(36.598, -6.230, poligonos) == zona.id


def test_resolver_id_point_outside(session):
    ZonaPoligonoCRUD.crear(session, "Centro", SQUARE)
    poligonos = ZonaPoligonoCRUD.listar(session)
    assert ZonaPoligonoCRUD.resolver_id(36.700, -6.100, poligonos) is None


def test_resolver_id_no_coords():
    assert ZonaPoligonoCRUD.resolver_id(None, None, []) is None


def test_resolver_id_first_match_wins(session):
    a = ZonaPoligonoCRUD.crear(session, "A", SQUARE)
    ZonaPoligonoCRUD.crear(session, "B", SQUARE)  # same shape, overlaps
    poligonos = ZonaPoligonoCRUD.listar(session)  # ordered by nombre -> A first
    assert ZonaPoligonoCRUD.resolver_id(36.598, -6.230, poligonos) == a.id


# ── ScraperRunner wiring ───────────────────────────────────────────────────


def _runner_with_polygon(zona_id: int):
    runner = ScraperRunner(db_session=MagicMock())
    runner._zona_poligonos = [
        ZonaPoligono(id=zona_id, nombre="Centro", geometria=SQUARE)
    ]
    return runner


def test_runner_resolves_zona_for_property_with_coords():
    runner = _runner_with_polygon(7)
    prop = Propiedad(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="x",
        titulo="t", latitud=36.598, longitud=-6.230,
    )

    runner._resolver_zona_poligono(prop)

    assert prop.zona_poligono_id == 7
    runner.db_session.commit.assert_called_once()


def test_runner_skips_property_without_coords():
    runner = _runner_with_polygon(7)
    prop = Propiedad(hash_unico="h", url_original="u", fuente_id=1, origen_web="x", titulo="t")

    runner._resolver_zona_poligono(prop)

    assert prop.zona_poligono_id is None
    runner.db_session.commit.assert_not_called()


def test_runner_clears_stale_zona_when_point_leaves_all_polygons():
    runner = _runner_with_polygon(7)
    prop = Propiedad(
        hash_unico="h", url_original="u", fuente_id=1, origen_web="x",
        titulo="t", latitud=36.700, longitud=-6.100, zona_poligono_id=7,
    )

    runner._resolver_zona_poligono(prop)

    assert prop.zona_poligono_id is None

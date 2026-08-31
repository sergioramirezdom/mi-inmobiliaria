"""Tests for the manual exclusion flag (`excluir_de_estadisticas`) and its
gating at the `fetch_props`/`fetch_hist` choke point in
`app/pages/4_estadisticas.py`.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from sqlalchemy import ARRAY, text
from sqlalchemy.ext.compiler import compiles
from sqlmodel import Session, create_engine, select

from db.database import PropiedadCRUD
from db.models import Fuente, PrecioHistorico, Propiedad
from ui import market_stats as ms
from ui import offer_advisor as oa
from ui.property_queries import no_excluidas_clause


# SQLite can't render the ARRAY(String) columns (`fotos`, `amenidades`) used
# by Propiedad in production (Postgres). Compile them as TEXT for tests only.
@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(element, compiler, **kw):
    return "TEXT"


def _memory_engine():
    return create_engine("sqlite:///:memory:")


def _create_tables(engine):
    # In production, `excluir_de_estadisticas` is added via a raw
    # `ALTER TABLE ... ADD COLUMN ... DEFAULT FALSE` with NO NOT NULL
    # clause (see scripts/migrate_excluir_estadisticas.py) — unlike
    # SQLModel's `create_all()`, which would infer NOT NULL from the
    # non-Optional `bool` type hint. Relax it here so a real legacy NULL
    # can be simulated and `.isnot(True)` is tested faithfully.
    col = Propiedad.__table__.c.excluir_de_estadisticas
    original_nullable = col.nullable
    col.nullable = True
    try:
        Fuente.__table__.create(bind=engine, checkfirst=True)
        Propiedad.__table__.create(bind=engine, checkfirst=True)
        PrecioHistorico.__table__.create(bind=engine, checkfirst=True)
    finally:
        col.nullable = original_nullable


def _seed_fuente(session) -> int:
    fuente = Fuente(nombre="Test", url=f"http://example.com/{id(session)}")
    session.add(fuente)
    session.commit()
    session.refresh(fuente)
    return fuente.id


def _seed_propiedad(session, fuente_id, **kw) -> Propiedad:
    base = dict(
        hash_unico=f"hash-{kw.get('titulo', 'x')}-{id(kw)}",
        url_original="https://example.com/prop",
        fuente_id=fuente_id,
        origen_web="Test",
        titulo="Piso en venta",
        precio=150_000.0,
        activa=True,
    )
    base.update(kw)
    prop = Propiedad(**base)
    session.add(prop)
    session.commit()
    session.refresh(prop)
    return prop


NOW = datetime(2026, 7, 16, 12, 0, 0)


# ── 1.3 / 1.4 — PropiedadCRUD.marcar_excluida ────────────────────────────


def test_marcar_excluida_sets_flag_activa_false_fecha_baja_now():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        prop = _seed_propiedad(session, fuente_id, activa=True, fecha_baja=None)

        updated = PropiedadCRUD.marcar_excluida(session, prop.id, True, now=NOW)

        assert updated.excluir_de_estadisticas is True
        assert updated.activa is False
        assert updated.fecha_baja == NOW

        # Persisted, not just in-memory
        reloaded = session.get(Propiedad, prop.id)
        assert reloaded.excluir_de_estadisticas is True
        assert reloaded.activa is False
        assert reloaded.fecha_baja == NOW


def test_desmarcar_excluida_restores_activa_true_fecha_baja_none():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        prop = _seed_propiedad(
            session, fuente_id, activa=False, fecha_baja=NOW,
            excluir_de_estadisticas=True,
        )

        updated = PropiedadCRUD.marcar_excluida(session, prop.id, False)

        assert updated.excluir_de_estadisticas is False
        assert updated.activa is True
        assert updated.fecha_baja is None

        reloaded = session.get(Propiedad, prop.id)
        assert reloaded.excluir_de_estadisticas is False
        assert reloaded.activa is True
        assert reloaded.fecha_baja is None


# ── 2.1 / 2.2 — stats gating (`no_excluidas_clause` filter, choke point) ──
#
# `no_excluidas_clause()` lives in `ui/property_queries.py` (pure query
# layer, no Streamlit side effects) so it is importable/testable directly.
# `app/pages/4_estadisticas.py:fetch_props`/`fetch_hist` (tasks 2.3/2.4) are
# still the *only* two call sites that apply it — the single choke point
# from design is preserved; only the predicate's definition site moved out
# of the Streamlit page module so it can be unit tested without importing
# a module with heavy top-level side effects (full page render, live DB
# session calls at import time — see Deviations in the apply-progress
# report for the full rationale).


def test_isnot_true_treats_null_column_as_not_excluded():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        prop = _seed_propiedad(session, fuente_id)
        # Simulate a legacy row that predates the migration: column is NULL,
        # not False, at the raw SQL level.
        session.execute(
            text("UPDATE propiedad SET excluir_de_estadisticas = NULL WHERE id = :id"),
            {"id": prop.id},
        )
        session.commit()

        result_ids = session.exec(
            select(Propiedad.id).where(no_excluidas_clause())
        ).all()

        assert prop.id in result_ids


def test_fetch_props_excludes_flagged_property():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        normal = _seed_propiedad(session, fuente_id, titulo="Normal")
        flagged = _seed_propiedad(
            session, fuente_id, titulo="Excluida",
            excluir_de_estadisticas=True, activa=False, fecha_baja=NOW,
        )

        result_ids = {
            r for r in session.exec(
                select(Propiedad.id).where(no_excluidas_clause())
            ).all()
        }

        assert normal.id in result_ids
        assert flagged.id not in result_ids


def test_fetch_hist_excludes_flagged_propertys_precio_historico():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        normal = _seed_propiedad(session, fuente_id, titulo="Normal")
        flagged = _seed_propiedad(
            session, fuente_id, titulo="Excluida",
            excluir_de_estadisticas=True, activa=False, fecha_baja=NOW,
        )
        session.add(PrecioHistorico(propiedad_id=normal.id, precio=100_000.0, fecha=NOW))
        session.add(PrecioHistorico(propiedad_id=flagged.id, precio=200_000.0, fecha=NOW))
        session.commit()

        non_excluded_ids = select(Propiedad.id).where(no_excluidas_clause())
        hist_rows = session.exec(
            select(PrecioHistorico).where(
                PrecioHistorico.propiedad_id.in_(non_excluded_ids)
            )
        ).all()

        hist_prop_ids = {h.propiedad_id for h in hist_rows}
        assert normal.id in hist_prop_ids
        assert flagged.id not in hist_prop_ids


# ── Shared fixture: gate-filtered dicts, matching fetch_props()'s shape ──


def _to_fetch_props_dict(prop: Propiedad) -> dict:
    """Mirrors the exact dict shape `4_estadisticas.py:fetch_props` returns."""
    return {
        "id": prop.id, "titulo": prop.titulo, "precio": prop.precio,
        "precio_anterior": prop.precio_anterior, "superficie_m2": prop.superficie_m2,
        "habitaciones": prop.habitaciones, "tipo_propiedad": prop.tipo_propiedad,
        "barrio": prop.zona_normalizada or prop.barrio,
        "municipio": prop.municipio, "origen_web": prop.origen_web,
        "url_original": prop.url_original, "activa": prop.activa, "favorita": prop.favorita,
        "descartada": prop.descartada, "fecha_scraping": prop.fecha_scraping,
        "fecha_publicacion": prop.fecha_publicacion, "fecha_baja": prop.fecha_baja,
    }


def _seed_gated_fixture(session, fuente_id):
    """One normal recent listing + one manually-excluded former 'sale'.

    The excluded property is engineered to qualify for every kpis_pulso
    metric (nuevas/ventas/precio_m2/bajadas/dias_mercado) and for
    offer_advisor comparables if it were NOT gated out.
    """
    normal = _seed_propiedad(
        session, fuente_id, titulo="Normal", precio=200_000.0,
        superficie_m2=80.0, barrio="Centro", municipio="El Puerto",
        tipo_propiedad="piso", activa=True,
        fecha_scraping=NOW - timedelta(days=15),
    )
    flagged = _seed_propiedad(
        session, fuente_id, titulo="Excluida", precio=180_000.0,
        superficie_m2=82.0, barrio="Centro", municipio="El Puerto",
        tipo_propiedad="piso", activa=False, fecha_baja=NOW - timedelta(days=10),
        fecha_scraping=NOW - timedelta(days=40),
        excluir_de_estadisticas=True,
    )
    session.add(PrecioHistorico(propiedad_id=flagged.id, precio=220_000.0, fecha=NOW - timedelta(days=35)))
    session.add(PrecioHistorico(propiedad_id=flagged.id, precio=180_000.0, fecha=NOW - timedelta(days=10)))
    session.commit()
    return normal, flagged


def _all_and_filtered_dicts(session):
    all_rows = session.exec(select(Propiedad)).all()
    filtered_rows = session.exec(select(Propiedad).where(no_excluidas_clause())).all()
    all_hist = session.exec(select(PrecioHistorico)).all()
    filtered_ids = {p.id for p in filtered_rows}
    filtered_hist = [h for h in all_hist if h.propiedad_id in filtered_ids]
    return (
        [_to_fetch_props_dict(p) for p in all_rows],
        [_to_fetch_props_dict(p) for p in filtered_rows],
        [{"propiedad_id": h.propiedad_id, "precio": h.precio, "fecha": h.fecha} for h in all_hist],
        [{"propiedad_id": h.propiedad_id, "precio": h.precio, "fecha": h.fecha} for h in filtered_hist],
    )


# ── 2.5 — excluded property absent from all kpis_pulso metrics ──────────


def test_excluded_property_absent_from_all_kpis_pulso():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        normal, flagged = _seed_gated_fixture(session, fuente_id)
        all_dicts, filtered_dicts, all_hist, filtered_hist = _all_and_filtered_dicts(session)

        unfiltered = ms.kpis_pulso(ms.props_to_df(all_dicts), ms.hist_to_df(all_hist), NOW)
        filtered = ms.kpis_pulso(ms.props_to_df(filtered_dicts), ms.hist_to_df(filtered_hist), NOW)

        # Unfiltered: the flagged property's fake "sale" is counted.
        assert unfiltered["ventas"]["valor"] == 1
        assert unfiltered["bajadas"]["valor"] == 1
        assert unfiltered["dias_mercado"]["valor"] is not None

        # Gated: none of the 5 KPIs include the excluded property.
        assert filtered["ventas"]["valor"] == 0
        assert filtered["bajadas"]["valor"] == 0
        assert filtered["dias_mercado"]["valor"] is None
        assert filtered["nuevas"]["valor"] == unfiltered["nuevas"]["valor"] == 1


# ── 2.6 — excluded property absent from weekly chart + offer_advisor ────


def test_excluded_property_absent_from_weekly_chart_and_offer_advisor():
    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        normal, flagged = _seed_gated_fixture(session, fuente_id)
        _all_dicts, filtered_dicts, _all_hist, _filtered_hist = _all_and_filtered_dicts(session)

        filtered_df = ms.props_to_df(filtered_dicts)
        semanal = ms.serie_semanal_entradas(filtered_df, NOW, semanas=8)
        assert int(semanal["nuevas"].sum()) == 1  # only the non-excluded listing

        favorita = dict(filtered_dicts[0], id=999, superficie_m2=80.0, precio=210_000.0)
        comparables, _nivel = oa.seleccionar_comparables(favorita, filtered_dicts, NOW)
        comparable_ids = {c["id"] for c in comparables}
        assert flagged.id not in comparable_ids


# ── 2.7 — excluded property still visible under the 'vendidas' tab ──────


def test_excluded_property_still_visible_in_vendidas_tab():
    from ui.property_queries import build_stmt, tab_conditions

    engine = _memory_engine()
    _create_tables(engine)
    with Session(engine) as session:
        fuente_id = _seed_fuente(session)
        _normal, flagged = _seed_gated_fixture(session, fuente_id)

        stmt = build_stmt("vendidas", {}, "Más reciente")
        rows = session.exec(stmt).all()
        row_ids = {p.id for p in rows}

        assert flagged.id in row_ids
        # tab_conditions("vendidas") itself doesn't reference the flag —
        # it stays keyed on `activa` only, per design.
        assert all("excluir_de_estadisticas" not in str(c) for c in tab_conditions("vendidas"))

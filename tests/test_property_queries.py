"""Tests for the pure query layer of Propiedades 2.0."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Propiedad
from sqlalchemy import or_
from ui.property_queries import (
    CARACTERISTICAS,
    SORT_OPTIONS,
    build_stmt,
    counts_from_rows,
    filter_conditions,
    precio_por_m2,
    prop_to_dict,
    tab_conditions,
)


# ── tab_conditions ────────────────────────────────────────────────────

def test_tab_nuevas_is_active_not_discarded_not_viewed():
    conds = tab_conditions("nuevas")
    expected = [Propiedad.activa == True, Propiedad.descartada == False, Propiedad.vista == False]
    assert len(conds) == 3
    assert all(c.compare(e) for c, e in zip(conds, expected))


def test_tab_todas_is_active_not_discarded():
    conds = tab_conditions("todas")
    expected = [Propiedad.activa == True, Propiedad.descartada == False]
    assert len(conds) == 2
    assert all(c.compare(e) for c, e in zip(conds, expected))


def test_tab_favoritas_descartadas_vendidas():
    assert tab_conditions("favoritas")[0].compare(Propiedad.favorita == True)
    assert tab_conditions("descartadas")[0].compare(Propiedad.descartada == True)
    assert tab_conditions("vendidas")[0].compare(Propiedad.activa == False)


def test_tab_unknown_raises():
    with pytest.raises(ValueError):
        tab_conditions("nope")


# ── filter_conditions ─────────────────────────────────────────────────

def test_numeric_filters_include_null():
    conds = filter_conditions({"precio_min": 100_000})
    assert len(conds) == 1
    assert conds[0].compare(or_(Propiedad.precio >= 100_000, Propiedad.precio == None))


def test_zero_or_missing_filters_produce_no_conditions():
    assert filter_conditions({}) == []
    assert filter_conditions({"precio_min": 0, "m2_min": 0, "search": "", "tipos": []}) == []


def test_caracteristicas_require_true():
    conds = filter_conditions({"caracteristicas": ["Terraza", "Ascensor"]})
    assert len(conds) == 2
    assert conds[0].compare(Propiedad.terraza == True)
    assert conds[1].compare(Propiedad.ascensor == True)


def test_search_matches_titulo_or_descripcion():
    conds = filter_conditions({"search": "patio"})
    assert len(conds) == 1
    assert conds[0].compare(
        or_(Propiedad.titulo.ilike("%patio%"), Propiedad.descripcion.ilike("%patio%"))
    )


def test_tipos_and_distritos_use_in():
    conds = filter_conditions({"tipos": ["piso"], "distritos": ["Centro"]})
    assert len(conds) == 2
    assert conds[0].compare(Propiedad.tipo_propiedad.in_(["piso"]))
    assert conds[1].compare(Propiedad.distrito.in_(["Centro"]))


# ── build_stmt ────────────────────────────────────────────────────────

def test_build_stmt_compiles_and_limits():
    stmt = build_stmt("nuevas", {"precio_max": 200_000}, "Precio (menor)")
    sql = str(stmt)
    assert "LIMIT" in sql
    assert "ORDER BY" in sql


def test_build_stmt_unknown_sort_raises():
    with pytest.raises(KeyError):
        build_stmt("todas", {}, "no existe")


def test_build_stmt_fecha_sort_uses_coalesce_resolver():
    """Sort options for fecha use fecha_listado_col() (COALESCE), not the raw
    field-name lookup, so a manually corrected fecha_publicacion reorders."""
    stmt = build_stmt("todas", {}, "Más reciente")
    sql = str(stmt).lower()
    assert "coalesce" in sql

    stmt2 = build_stmt("todas", {}, "Más antiguo")
    sql2 = str(stmt2).lower()
    assert "coalesce" in sql2


def test_build_stmt_precio_sort_does_not_use_coalesce():
    stmt = build_stmt("todas", {}, "Precio (menor)")
    assert "coalesce" not in str(stmt).lower()


# ── precio_por_m2 ─────────────────────────────────────────────────────

def test_precio_por_m2():
    assert precio_por_m2(189_000, 102) == 1853
    assert precio_por_m2(None, 102) is None
    assert precio_por_m2(189_000, None) is None
    assert precio_por_m2(189_000, 0) is None


# ── prop_to_dict ──────────────────────────────────────────────────────

def _prop(**kwargs):
    defaults = dict(
        id=1,
        hash_unico="x",
        url_original="https://example.com/1",
        fuente_id=7,
        origen_web="example.com",
        titulo="Piso céntrico",
        precio=189_000.0,
        superficie_m2=102.0,
        habitaciones=3,
        banos=2,
        tipo_propiedad="piso",
        barrio="Centro",
        municipio="El Puerto de Santa María",
        terraza=True,
        ascensor=True,
        fecha_scraping=datetime.utcnow() - timedelta(days=2),
        activa=True,
    )
    defaults.update(kwargs)
    return Propiedad(**defaults)


def test_prop_to_dict_basics():
    d = prop_to_dict(_prop(), fuente_manual_id=99)
    assert d["id"] == 1
    assert d["precio_m2"] == 1853
    assert d["bajada"] is None
    assert d["dias"] == 2
    assert d["es_manual"] is False
    assert d["chips"] == ["Ascensor", "Terraza"]  # CARACTERISTICAS order
    assert d["url"] == "https://example.com/1"


def test_prop_to_dict_emits_excluida_from_flag():
    d = prop_to_dict(_prop(excluir_de_estadisticas=True))
    assert d["excluida"] is True

    d2 = prop_to_dict(_prop(excluir_de_estadisticas=False))
    assert d2["excluida"] is False


def test_prop_to_dict_bajada_only_when_lower():
    d = prop_to_dict(_prop(precio_anterior=195_000.0))
    assert d["bajada"] == 6_000
    d2 = prop_to_dict(_prop(precio_anterior=180_000.0))
    assert d2["bajada"] is None


def test_prop_to_dict_manual_badge():
    d = prop_to_dict(_prop(fuente_id=99), fuente_manual_id=99)
    assert d["es_manual"] is True


def test_prop_to_dict_dias_usa_fecha_publicacion_cuando_esta_corregida():
    """`dias` (badge de días en mercado) debe resolver vía fecha_publicacion
    cuando el usuario la ha corregido manualmente, no fecha_scraping crudo."""
    fecha_publicacion = datetime.utcnow() - timedelta(days=20)
    d = prop_to_dict(_prop(
        fecha_scraping=datetime.utcnow() - timedelta(days=2),
        fecha_publicacion=fecha_publicacion,
    ))
    assert d["dias"] == 20


def test_prop_to_dict_dias_usa_fecha_scraping_sin_correccion():
    d = prop_to_dict(_prop(fecha_scraping=datetime.utcnow() - timedelta(days=5)))
    assert d["dias"] == 5


# ── counts_from_rows ──────────────────────────────────────────────────

def test_counts_from_rows():
    rows = [
        # (activa, vista, descartada, favorita)
        (True, False, False, False),   # nueva + todas
        (True, True, False, True),     # todas + favorita
        (True, True, True, False),     # descartada
        (False, True, False, False),   # vendida
    ]
    c = counts_from_rows(rows)
    assert c == {"nuevas": 1, "todas": 2, "favoritas": 1, "descartadas": 1, "vendidas": 1}


def test_counts_from_rows_empty():
    assert counts_from_rows([]) == {"nuevas": 0, "todas": 0, "favoritas": 0, "descartadas": 0, "vendidas": 0}

"""Unit tests for app.scraper.price_drop.build_price_drop_entry — pure dict builder."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.price_drop import build_price_drop_entry


def _prop(**overrides):
    base = dict(
        id=42,
        titulo="Piso en el centro",
        url_original="https://example.com/p/42",
        favorita=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_entry_keeps_all_legacy_keys():
    entry = build_price_drop_entry(_prop(), 200000, 180000, 10.0)
    assert entry["titulo"] == "Piso en el centro"
    assert entry["url"] == "https://example.com/p/42"
    assert entry["precio_anterior"] == 200000
    assert entry["precio_nuevo"] == 180000
    assert entry["bajada_pct"] == 10.0


def test_entry_adds_propiedad_id_and_favorita():
    entry = build_price_drop_entry(_prop(id=7, favorita=True), 300000, 250000, 16.7)
    assert entry["propiedad_id"] == 7
    assert entry["favorita"] is True


def test_favorita_defaults_false_when_attr_missing():
    prop = SimpleNamespace(id=1, titulo="X", url_original="https://e/x")
    entry = build_price_drop_entry(prop, 100, 90, 10.0)
    assert entry["favorita"] is False


def test_favorita_is_bool_coerced():
    entry = build_price_drop_entry(_prop(favorita=1), 100, 90, 10.0)
    assert entry["favorita"] is True
    entry2 = build_price_drop_entry(_prop(favorita=0), 100, 90, 10.0)
    assert entry2["favorita"] is False


def test_entry_has_exactly_the_expected_keys():
    entry = build_price_drop_entry(_prop(), 200000, 180000, 10.0)
    assert set(entry) == {
        "titulo",
        "url",
        "precio_anterior",
        "precio_nuevo",
        "bajada_pct",
        "propiedad_id",
        "favorita",
    }

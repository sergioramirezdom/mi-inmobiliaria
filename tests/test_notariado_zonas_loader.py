"""Tests for the explicit zona geometry registry and loader
(``app/scraper/notariado_zonas.py``).

No HTTP and no DB — pure stdlib file loading. Cases that need a synthetic
geometry directory monkeypatch ``_GEOMETRY_DIR`` (and ``ZONA_SLUGS`` when a
non-real slug must resolve) onto a ``tmp_path``.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper import notariado_zonas as nz  # noqa: E402


def test_known_slug_returns_parsed_geometry_dict():
    geometry = nz.load_zona_geometry("crevillet")

    assert isinstance(geometry, dict)
    assert isinstance(geometry["rings"], list)
    assert len(geometry["rings"]) > 0
    assert isinstance(geometry["spatialReference"], dict)


def test_unknown_slug_raises():
    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("nowhere")


def test_known_slug_with_absent_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)

    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("crevillet")


def test_invalid_json_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)
    (tmp_path / "crevillet.json").write_text("{not valid json")

    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("crevillet")


def test_valid_json_that_is_not_a_geometry_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)
    (tmp_path / "crevillet.json").write_text('{"foo": 1}')

    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("crevillet")


def test_geometry_missing_spatial_reference_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)
    (tmp_path / "crevillet.json").write_text('{"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}')

    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("crevillet")


def test_geometry_with_empty_rings_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)
    (tmp_path / "crevillet.json").write_text('{"rings": [], "spatialReference": {"wkid": 102100}}')

    with pytest.raises(nz.ZonaGeometryError):
        nz.load_zona_geometry("crevillet")


def test_registered_synthetic_slug_loads_from_geometry_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(nz, "_GEOMETRY_DIR", tmp_path)
    monkeypatch.setattr(nz, "ZONA_SLUGS", ["crevillet", "sample"])
    (tmp_path / "sample.json").write_text(
        '{"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]], "spatialReference": {"wkid": 102100}}'
    )

    geometry = nz.load_zona_geometry("sample")

    assert geometry["spatialReference"] == {"wkid": 102100}
    assert geometry["rings"][0][0] == [0, 0]


def test_available_zonas_lists_crevillet():
    assert "crevillet" in nz.available_zonas()
    assert nz.available_zonas() == list(nz.ZONA_SLUGS)


def test_available_zonas_result_is_a_copy():
    result = nz.available_zonas()
    result.append("mutated")

    assert "mutated" not in nz.available_zonas()
    assert "mutated" not in nz.ZONA_SLUGS

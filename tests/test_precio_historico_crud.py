"""Tests for PrecioHistoricoCRUD (add / update / get_by_propiedad / validar)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.database import PrecioHistoricoCRUD
from db.models import PrecioHistorico


# --- validar (pure, DB-free) ---

def test_validar_acepta_precio_positivo_y_fecha_pasada():
    now = datetime(2026, 8, 25, 12, 0, 0)
    fecha = now - timedelta(days=1)
    es_valido, error = PrecioHistoricoCRUD.validar(150_000, fecha, now)
    assert es_valido is True
    assert error is None


def test_validar_acepta_fecha_igual_a_now():
    now = datetime(2026, 8, 25, 12, 0, 0)
    es_valido, error = PrecioHistoricoCRUD.validar(150_000, now, now)
    assert es_valido is True
    assert error is None


def test_validar_rechaza_fecha_futura():
    now = datetime(2026, 8, 25, 12, 0, 0)
    fecha_futura = now + timedelta(days=1)
    es_valido, error = PrecioHistoricoCRUD.validar(150_000, fecha_futura, now)
    assert es_valido is False
    assert error


def test_validar_rechaza_precio_cero():
    now = datetime(2026, 8, 25, 12, 0, 0)
    es_valido, error = PrecioHistoricoCRUD.validar(0, now - timedelta(days=1), now)
    assert es_valido is False
    assert error


def test_validar_rechaza_precio_negativo():
    now = datetime(2026, 8, 25, 12, 0, 0)
    es_valido, error = PrecioHistoricoCRUD.validar(-100, now - timedelta(days=1), now)
    assert es_valido is False
    assert error


def test_validar_rechaza_precio_none():
    now = datetime(2026, 8, 25, 12, 0, 0)
    es_valido, error = PrecioHistoricoCRUD.validar(None, now - timedelta(days=1), now)
    assert es_valido is False
    assert error


def test_validar_rechaza_fecha_none():
    now = datetime(2026, 8, 25, 12, 0, 0)
    es_valido, error = PrecioHistoricoCRUD.validar(100_000, None, now)
    assert es_valido is False
    assert error


def test_validar_usa_utcnow_por_defecto_cuando_now_no_se_pasa():
    fecha_pasada = datetime.utcnow() - timedelta(days=1)
    es_valido, error = PrecioHistoricoCRUD.validar(100_000, fecha_pasada)
    assert es_valido is True
    assert error is None


# --- add ---

def test_add_crea_registro_y_lo_persiste():
    session = MagicMock()
    fecha = datetime(2026, 1, 1)
    registro = PrecioHistoricoCRUD.add(session, propiedad_id=42, precio=200_000, fecha=fecha)
    session.add.assert_called_once()
    session.commit.assert_called_once()
    session.refresh.assert_called_once()
    assert isinstance(registro, PrecioHistorico)
    assert registro.propiedad_id == 42
    assert registro.precio == 200_000
    assert registro.fecha == fecha


# --- update ---

def test_update_modifica_precio_y_fecha_de_registro_existente():
    existente = PrecioHistorico(id=7, propiedad_id=42, precio=100_000, fecha=datetime(2025, 1, 1))
    session = MagicMock()
    session.get.return_value = existente

    nueva_fecha = datetime(2026, 2, 2)
    resultado = PrecioHistoricoCRUD.update(session, historico_id=7, precio=180_000, fecha=nueva_fecha)

    assert resultado is existente
    assert resultado.precio == 180_000
    assert resultado.fecha == nueva_fecha
    session.add.assert_called_once_with(existente)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(existente)


def test_update_devuelve_none_si_no_existe():
    session = MagicMock()
    session.get.return_value = None
    resultado = PrecioHistoricoCRUD.update(session, historico_id=999, precio=100, fecha=datetime(2026, 1, 1))
    assert resultado is None
    session.commit.assert_not_called()


# --- get_by_propiedad ---

def test_get_by_propiedad_devuelve_registros_ordenados_por_fecha():
    registros = [
        PrecioHistorico(id=1, propiedad_id=42, precio=200_000, fecha=datetime(2025, 1, 1)),
        PrecioHistorico(id=2, propiedad_id=42, precio=190_000, fecha=datetime(2025, 6, 1)),
    ]
    session = MagicMock()
    session.exec.return_value.all.return_value = registros
    resultado = PrecioHistoricoCRUD.get_by_propiedad(session, propiedad_id=42)
    assert resultado == registros

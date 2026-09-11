"""Database configuration and utilities."""

from sqlmodel import SQLModel, create_engine, Session, select
from typing import List, Optional, Tuple
from datetime import datetime
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from db.models import (
    Fuente,
    Propiedad,
    FiltroAlerta,
    PrecioHistorico,
    RegistroEjecucion,
    EstadisticaNotarial,
    EstadisticaZonaNotarial,
    UbicacionAproximada,
    ZonaPoligono,
)
from scraper.geo_utils import point_in_polygon

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # Test connection before using
    connect_args={"connect_timeout": 10}
)


def create_tables():
    """Create all tables in the database."""
    try:
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


def get_session():
    """Get a database session."""
    with Session(engine) as session:
        yield session


def init_db():
    """Initialize database."""
    create_tables()


# CRUD Helpers for Fuente
class FuenteCRUD:
    """CRUD operations for Fuente."""

    @staticmethod
    def create(session: Session, fuente: Fuente) -> Fuente:
        """Create a new source."""
        session.add(fuente)
        session.commit()
        session.refresh(fuente)
        return fuente

    @staticmethod
    def get(session: Session, fuente_id: int) -> Optional[Fuente]:
        """Get a source by ID."""
        return session.get(Fuente, fuente_id)

    @staticmethod
    def get_all(session: Session) -> List[Fuente]:
        """Get all sources."""
        return session.exec(select(Fuente)).all()

    @staticmethod
    def get_active(session: Session) -> List[Fuente]:
        """Get all active sources."""
        return session.exec(select(Fuente).where(Fuente.activa == True)).all()

    @staticmethod
    def update(session: Session, fuente_id: int, **kwargs) -> Optional[Fuente]:
        """Update a source."""
        fuente = session.get(Fuente, fuente_id)
        if not fuente:
            return None
        for key, value in kwargs.items():
            if hasattr(fuente, key):
                setattr(fuente, key, value)
        session.add(fuente)
        session.commit()
        session.refresh(fuente)
        return fuente

    @staticmethod
    def delete(session: Session, fuente_id: int) -> bool:
        """Delete a source."""
        fuente = session.get(Fuente, fuente_id)
        if not fuente:
            return False
        session.delete(fuente)
        session.commit()
        return True

    @staticmethod
    def get_by_url(session: Session, url: str) -> Optional[Fuente]:
        """Get a source by URL."""
        return session.exec(select(Fuente).where(Fuente.url == url)).first()


# CRUD Helpers for Propiedad
class PropiedadCRUD:
    """CRUD operations for Propiedad."""

    @staticmethod
    def create(session: Session, propiedad: Propiedad) -> Propiedad:
        """Create a new property."""
        session.add(propiedad)
        session.commit()
        session.refresh(propiedad)
        return propiedad

    @staticmethod
    def get(session: Session, propiedad_id: int) -> Optional[Propiedad]:
        """Get a property by ID."""
        return session.get(Propiedad, propiedad_id)

    @staticmethod
    def get_all(session: Session, skip: int = 0, limit: int = 100) -> List[Propiedad]:
        """Get all properties with pagination."""
        return session.exec(
            select(Propiedad).offset(skip).limit(limit)
        ).all()

    @staticmethod
    def get_by_hash(session: Session, hash_unico: str) -> Optional[Propiedad]:
        """Get a property by unique hash."""
        return session.exec(
            select(Propiedad).where(Propiedad.hash_unico == hash_unico)
        ).first()

    @staticmethod
    def update(session: Session, propiedad_id: int, **kwargs) -> Optional[Propiedad]:
        """Update a property."""
        propiedad = session.get(Propiedad, propiedad_id)
        if not propiedad:
            return None
        for key, value in kwargs.items():
            if hasattr(propiedad, key):
                setattr(propiedad, key, value)
        session.add(propiedad)
        session.commit()
        session.refresh(propiedad)
        return propiedad

    @staticmethod
    def delete(session: Session, propiedad_id: int) -> bool:
        """Delete a property."""
        propiedad = session.get(Propiedad, propiedad_id)
        if not propiedad:
            return False
        session.delete(propiedad)
        session.commit()
        return True

    @staticmethod
    def count_all(session: Session) -> int:
        """Count total properties."""
        return session.exec(select(Propiedad)).all().__len__()

    @staticmethod
    def mark_as_viewed(session: Session, propiedad_id: int) -> Optional[Propiedad]:
        """Mark a property as viewed."""
        return PropiedadCRUD.update(session, propiedad_id, vista=True)

    @staticmethod
    def mark_as_discarded(session: Session, propiedad_id: int) -> Optional[Propiedad]:
        """Mark a property as discarded."""
        return PropiedadCRUD.update(session, propiedad_id, descartada=True)

    @staticmethod
    def mark_as_favorite(session: Session, propiedad_id: int, favorita: bool = True) -> Optional[Propiedad]:
        """Mark a property as favorite (or unfavorite if favorita=False)."""
        return PropiedadCRUD.update(session, propiedad_id, favorita=favorita)

    @staticmethod
    def toggle_favorite(session: Session, propiedad_id: int) -> Optional[Propiedad]:
        """Toggle favorite status of a property."""
        propiedad = session.get(Propiedad, propiedad_id)
        if not propiedad:
            return None
        propiedad.favorita = not propiedad.favorita
        session.add(propiedad)
        session.commit()
        session.refresh(propiedad)
        return propiedad

    @staticmethod
    def marcar_excluida(
        session: Session, propiedad_id: int, excluir: bool, now: Optional[datetime] = None
    ) -> Optional[Propiedad]:
        """Manually mark/unmark a property as excluded from statistics.

        excluir=True  -> activa=False, fecha_baja=now, flag=True (never a real sale)
        excluir=False -> activa=True,  fecha_baja=None, flag=False (restore)
        """
        if now is None:
            now = datetime.utcnow()
        if excluir:
            return PropiedadCRUD.update(
                session, propiedad_id,
                excluir_de_estadisticas=True, activa=False, fecha_baja=now,
            )
        return PropiedadCRUD.update(
            session, propiedad_id,
            excluir_de_estadisticas=False, activa=True, fecha_baja=None,
        )

    @staticmethod
    def get_distinct_barrios(session: Session) -> List[str]:
        """Get all distinct non-empty barrio values, sorted alphabetically (case-insensitive)."""
        rows = session.exec(
            select(Propiedad.barrio).where(Propiedad.barrio.is_not(None)).distinct()
        ).all()
        return sorted({b.strip() for b in rows if b and b.strip()}, key=str.lower)

    @staticmethod
    def get_distinct_zonas_normalizadas(session: Session) -> List[str]:
        """Get all distinct non-empty zona_normalizada values, sorted alphabetically."""
        rows = session.exec(
            select(Propiedad.zona_normalizada).where(
                Propiedad.zona_normalizada.is_not(None)
            ).distinct()
        ).all()
        return sorted({z.strip() for z in rows if z and z.strip()}, key=str.lower)


# CRUD Helpers for PrecioHistorico (add/edit only — no delete, per design)
class PrecioHistoricoCRUD:
    """CRUD operations for PrecioHistorico. Add and edit only — no delete."""

    @staticmethod
    def validar(precio: Optional[float], fecha: Optional[datetime], now: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
        """Pure validation for a price-history entry.

        Rejects a missing/non-positive price, a missing date, or a future
        date (relative to `now`, defaulting to `datetime.utcnow()`).
        Returns `(es_valido, mensaje_error)`.
        """
        if now is None:
            now = datetime.utcnow()
        if precio is None or precio <= 0:
            return False, "El precio debe ser mayor que 0."
        if fecha is None:
            return False, "La fecha es obligatoria."
        if fecha > now:
            return False, "La fecha no puede ser futura."
        return True, None

    @staticmethod
    def add(session: Session, propiedad_id: int, precio: float, fecha: datetime) -> PrecioHistorico:
        """Add a new price-history row with a user-chosen date."""
        registro = PrecioHistorico(propiedad_id=propiedad_id, precio=precio, fecha=fecha)
        session.add(registro)
        session.commit()
        session.refresh(registro)
        return registro

    @staticmethod
    def update(session: Session, historico_id: int, precio: float, fecha: datetime) -> Optional[PrecioHistorico]:
        """Edit an existing price-history row's price and/or date."""
        registro = session.get(PrecioHistorico, historico_id)
        if not registro:
            return None
        registro.precio = precio
        registro.fecha = fecha
        session.add(registro)
        session.commit()
        session.refresh(registro)
        return registro

    @staticmethod
    def get_by_propiedad(session: Session, propiedad_id: int) -> List[PrecioHistorico]:
        """Get all price-history rows for a property, chronological order."""
        stmt = (
            select(PrecioHistorico)
            .where(PrecioHistorico.propiedad_id == propiedad_id)
            .order_by(PrecioHistorico.fecha.asc())
        )
        return session.exec(stmt).all()


class UbicacionAproximadaCRUD:
    """CRUD for the shared ``app_ubicacion_aproximada`` table.

    Scrapers only ever mark a location as approximate (upsert). Exact
    locations are represented by the *absence* of a row, so there is no
    "mark exact" / delete path here — the web map tool owns that.
    """

    @staticmethod
    def get_by_propiedad(session: Session, propiedad_id: int) -> Optional[UbicacionAproximada]:
        stmt = select(UbicacionAproximada).where(
            UbicacionAproximada.propiedad_id == propiedad_id
        )
        return session.exec(stmt).first()

    @staticmethod
    def marcar_aproximada(
        session: Session, propiedad_id: int, radio_m: int = 300
    ) -> UbicacionAproximada:
        """Insert or update the approximate-location flag for a property."""
        row = UbicacionAproximadaCRUD.get_by_propiedad(session, propiedad_id)
        if row is None:
            row = UbicacionAproximada(propiedad_id=propiedad_id)
        row.aproximada = True
        row.radio_m = radio_m
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


class ZonaPoligonoCRUD:
    """Read helpers for the shared ``app_zona_poligono`` table plus the
    point-in-polygon resolver used to set ``Propiedad.zona_poligono_id``.

    Writes (draw / rename / delete a polygon) are owned by the web app; only
    ``crear`` is exposed here for scripts and tests.
    """

    @staticmethod
    def listar(session: Session, solo_activos: bool = True) -> List[ZonaPoligono]:
        stmt = select(ZonaPoligono)
        if solo_activos:
            stmt = stmt.where(ZonaPoligono.activo == True)  # noqa: E712
        stmt = stmt.order_by(ZonaPoligono.nombre)
        return list(session.exec(stmt).all())

    @staticmethod
    def get(session: Session, zona_id: int) -> Optional[ZonaPoligono]:
        return session.get(ZonaPoligono, zona_id)

    @staticmethod
    def crear(
        session: Session, nombre: str, geometria: dict, color: Optional[str] = None
    ) -> ZonaPoligono:
        zona = ZonaPoligono(nombre=nombre, geometria=geometria, color=color)
        session.add(zona)
        session.commit()
        session.refresh(zona)
        return zona

    @staticmethod
    def resolver_id(
        lat: Optional[float],
        lng: Optional[float],
        poligonos: List[ZonaPoligono],
    ) -> Optional[int]:
        """Return the id of the first active polygon that contains (lat, lng).

        ``poligonos`` is passed in (typically from :meth:`listar`) so a caller
        iterating many properties loads the polygons once. Returns ``None``
        when the point is missing or falls outside every polygon.
        """
        if lat is None or lng is None:
            return None
        for zona in poligonos:
            if point_in_polygon(lat, lng, zona.geometria):
                return zona.id
        return None


# CRUD Helpers for FiltroAlerta
class FiltroAlertaCRUD:
    """CRUD operations for FiltroAlerta."""

    @staticmethod
    def create(session: Session, filtro: FiltroAlerta) -> FiltroAlerta:
        """Create a new alert filter."""
        session.add(filtro)
        session.commit()
        session.refresh(filtro)
        return filtro

    @staticmethod
    def get(session: Session, filtro_id: int) -> Optional[FiltroAlerta]:
        """Get a filter by ID."""
        return session.get(FiltroAlerta, filtro_id)

    @staticmethod
    def get_all(session: Session) -> List[FiltroAlerta]:
        """Get all filters."""
        return session.exec(select(FiltroAlerta)).all()

    @staticmethod
    def get_active(session: Session) -> List[FiltroAlerta]:
        """Get all active filters."""
        return session.exec(select(FiltroAlerta).where(FiltroAlerta.activo == True)).all()

    @staticmethod
    def update(session: Session, filtro_id: int, **kwargs) -> Optional[FiltroAlerta]:
        """Update a filter."""
        filtro = session.get(FiltroAlerta, filtro_id)
        if not filtro:
            return None
        for key, value in kwargs.items():
            if hasattr(filtro, key):
                setattr(filtro, key, value)
        session.add(filtro)
        session.commit()
        session.refresh(filtro)
        return filtro

    @staticmethod
    def delete(session: Session, filtro_id: int) -> bool:
        """Delete a filter."""
        filtro = session.get(FiltroAlerta, filtro_id)
        if not filtro:
            return False
        session.delete(filtro)
        session.commit()
        return True


# CRUD Helpers for RegistroEjecucion (append-only run log)
class RegistroEjecucionCRUD:
    """CRUD operations for RegistroEjecucion. Rows are append-only — no update/delete."""

    @staticmethod
    def create(session: Session, registro: RegistroEjecucion) -> RegistroEjecucion:
        """Persist one run-log row."""
        session.add(registro)
        session.commit()
        session.refresh(registro)
        return registro

    @staticmethod
    def get_by_fuente(session: Session, fuente_id: int, limit: int = 50) -> List[RegistroEjecucion]:
        """Get the most recent run-log rows for a single fuente."""
        stmt = (
            select(RegistroEjecucion)
            .where(RegistroEjecucion.fuente_id == fuente_id)
            .order_by(RegistroEjecucion.fecha.desc())
            .limit(limit)
        )
        return session.exec(stmt).all()

    @staticmethod
    def get_by_run_id(session: Session, run_id: str, limit: int = 200) -> List[RegistroEjecucion]:
        """Get every run-log row written during a single top-level cycle
        (same run_id), ordered chronologically (fecha ascending)."""
        stmt = (
            select(RegistroEjecucion)
            .where(RegistroEjecucion.run_id == run_id)
            .order_by(RegistroEjecucion.fecha.asc())
            .limit(limit)
        )
        return session.exec(stmt).all()

    @staticmethod
    def get_recent(session: Session, limit: int = 50) -> List[RegistroEjecucion]:
        """Get the most recent run-log rows across all fuentes."""
        stmt = select(RegistroEjecucion).order_by(RegistroEjecucion.fecha.desc()).limit(limit)
        return session.exec(stmt).all()


# CRUD Helpers for EstadisticaNotarial (append-only historical series)
class EstadisticaNotarialCRUD:
    """CRUD operations for EstadisticaNotarial. Rows are append-only — no update/delete."""

    @staticmethod
    def create(session: Session, estadistica: EstadisticaNotarial) -> EstadisticaNotarial:
        """Persist one notarial stats row."""
        session.add(estadistica)
        session.commit()
        session.refresh(estadistica)
        return estadistica

    @staticmethod
    def get_by_combo(
        session: Session,
        location_code: str,
        property_type: str,
        construction_type: str,
    ) -> List[EstadisticaNotarial]:
        """Get all stored rows for a single (location, property, construction) combo,
        most recent last_data_update first."""
        stmt = (
            select(EstadisticaNotarial)
            .where(EstadisticaNotarial.location_code == location_code)
            .where(EstadisticaNotarial.property_type == property_type)
            .where(EstadisticaNotarial.construction_type == construction_type)
            .order_by(EstadisticaNotarial.last_data_update.desc())
        )
        return session.exec(stmt).all()

    @staticmethod
    def get_latest_for_combo(
        session: Session,
        location_code: str,
        property_type: str,
        construction_type: str,
    ) -> Optional[EstadisticaNotarial]:
        """Get the most recent stored row for a combo, or None if no rows exist yet."""
        rows = EstadisticaNotarialCRUD.get_by_combo(
            session, location_code, property_type, construction_type
        )
        return rows[0] if rows else None

    @staticmethod
    def get_all(session: Session) -> List[EstadisticaNotarial]:
        """Get all stored rows across every combo."""
        return session.exec(select(EstadisticaNotarial)).all()


# CRUD Helpers for EstadisticaZonaNotarial (append-only public price-avg series)
class EstadisticaZonaNotarialCRUD:
    """CRUD operations for EstadisticaZonaNotarial. Rows are append-only — no update/delete."""

    @staticmethod
    def create(session: Session, estadistica: EstadisticaZonaNotarial) -> EstadisticaZonaNotarial:
        """Persist one public zona price-avg row."""
        session.add(estadistica)
        session.commit()
        session.refresh(estadistica)
        return estadistica

    @staticmethod
    def get_by_zona_combo(
        session: Session,
        zona: str,
        property_type: str,
        construction_type: str,
    ) -> List[EstadisticaZonaNotarial]:
        """Get all stored rows for a single (zona, property, construction) combo,
        most recent captured_at first."""
        stmt = (
            select(EstadisticaZonaNotarial)
            .where(EstadisticaZonaNotarial.zona == zona)
            .where(EstadisticaZonaNotarial.property_type == property_type)
            .where(EstadisticaZonaNotarial.construction_type == construction_type)
            .order_by(EstadisticaZonaNotarial.captured_at.desc())
        )
        return session.exec(stmt).all()

    @staticmethod
    def get_latest_for_zona_combo(
        session: Session,
        zona: str,
        property_type: str,
        construction_type: str,
    ) -> Optional[EstadisticaZonaNotarial]:
        """Get the most recent stored row for a zona combo, or None if no rows exist yet."""
        rows = EstadisticaZonaNotarialCRUD.get_by_zona_combo(
            session, zona, property_type, construction_type
        )
        return rows[0] if rows else None

    @staticmethod
    def get_all(session: Session) -> List[EstadisticaZonaNotarial]:
        """Get all stored rows across every zona combo."""
        return session.exec(select(EstadisticaZonaNotarial)).all()

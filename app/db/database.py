"""Database configuration and utilities."""

from sqlmodel import SQLModel, create_engine, Session, select
from typing import List, Optional
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from db.models import Fuente, Propiedad, FiltroAlerta

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

"""SQLModel data models for Mi Inmobiliaria Personal."""

from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, String
from sqlalchemy import ARRAY

# Handle Streamlit reloads: Clean up existing tables from metadata
# so they can be redefined without "already defined" errors
try:
    # Remove existing tables to allow redefinition
    if 'fuente' in SQLModel.metadata.tables:
        del SQLModel.metadata.tables['fuente']
    if 'propiedad' in SQLModel.metadata.tables:
        del SQLModel.metadata.tables['propiedad']
    if 'filtroalerta' in SQLModel.metadata.tables:
        del SQLModel.metadata.tables['filtroalerta']
except Exception:
    # If this fails, tables might not exist yet, which is fine
    pass


class Fuente(SQLModel, table=True):
    """Real estate source (portal URL) configuration."""

    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)
    url: str = Field(unique=True, index=True)
    tipo_scraper: str = Field(default="generic")  # generic | playwright
    activa: bool = Field(default=True, index=True)
    intervalo_horas: int = Field(default=24)
    ultima_ejecucion: Optional[datetime] = None
    notas: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Propiedad(SQLModel, table=True):
    """Property listing found by scraper."""

    id: Optional[int] = Field(default=None, primary_key=True)
    hash_unico: str = Field(unique=True, index=True)  # SHA256 of url_original
    url_original: str = Field(index=True)
    fuente_id: int = Field(foreign_key="fuente.id")
    origen_web: str = Field(index=True)  # e.g., "Idealista", "Fotocasa"

    # Basic info
    titulo: str
    precio: Optional[float] = Field(default=None, index=True)
    precio_anterior: Optional[float] = None  # Previous price (before reduction)
    precio_comunidad: Optional[float] = None
    precio_ibi: Optional[float] = None
    tipo_propiedad: Optional[str] = Field(default=None, index=True)  # piso | casa | ático | bajo | dúplex | estudio | local

    # Surface and rooms
    superficie_m2: Optional[float] = Field(default=None, index=True)
    superficie_util_m2: Optional[float] = None
    habitaciones: Optional[int] = Field(default=None, index=True)
    banos: Optional[int] = None
    aseos: Optional[int] = None

    # Characteristics
    planta: Optional[int] = Field(default=None, index=True)
    total_plantas: Optional[int] = None
    ascensor: Optional[bool] = None
    garaje: Optional[bool] = None
    trastero: Optional[bool] = None
    terraza: Optional[bool] = None
    balcon: Optional[bool] = None
    patio: Optional[bool] = None
    piscina: Optional[bool] = None
    aire_acondicionado: Optional[bool] = None
    calefaccion: Optional[str] = None  # central | individual | sin calefacción
    amueblado: Optional[bool] = None
    mascotas: Optional[bool] = None

    # State and certification
    estado: Optional[str] = None  # nuevo | segunda mano | obra nueva | a reformar
    certificado_energetico: Optional[str] = None  # A | B | C | D | E | F | G | en trámite

    # Location
    direccion: Optional[str] = None
    barrio: Optional[str] = Field(default=None, index=True)
    distrito: Optional[str] = Field(default=None, index=True)
    municipio: Optional[str] = Field(default=None, index=True)
    provincia: Optional[str] = None
    codigo_postal: Optional[str] = Field(default=None, index=True)
    latitud: Optional[float] = None
    longitud: Optional[float] = None

    # Metadata
    descripcion: Optional[str] = None
    fotos: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    amenidades: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(String)))  # e.g., ["Elevator", "Storage Room", "Air Conditioning"]
    fecha_publicacion: Optional[datetime] = None
    fecha_scraping: datetime = Field(default_factory=datetime.utcnow, index=True)
    activa: bool = Field(default=True, index=True)
    vista: bool = Field(default=False, index=True)
    descartada: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FiltroAlerta(SQLModel, table=True):
    """Alert filter for property notifications."""

    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True)

    # Advanced filtering: criteria stored as JSON for flexibility
    # Supports: precio_min, precio_max, m2_min, m2_max, habitaciones, banos,
    #          barrio, tipo_propiedad, estado, año_construccion_min,
    #          gastos_comunidad_max, amenidades, etc.
    criterios_json: Optional[str] = None  # JSON string with filter criteria

    # Legacy fields (kept for backwards compatibility)
    precio_max: Optional[float] = None
    precio_min: Optional[float] = None
    m2_min: Optional[float] = None
    habitaciones_min: Optional[int] = None
    tipo_propiedad: Optional[str] = None
    ascensor: Optional[bool] = None
    garaje: Optional[bool] = None
    palabras_clave: Optional[str] = None
    municipio: Optional[str] = None
    distrito: Optional[str] = None

    activo: bool = Field(default=True, index=True)
    chat_id_telegram: Optional[str] = None  # Optional: uses env variable if not set
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

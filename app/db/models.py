"""SQLModel data models for Mi Inmobiliaria Personal."""

from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, String
from sqlalchemy import ARRAY

# Handle Streamlit reloads: Clean up existing tables from metadata
# so they can be redefined without "already defined" errors
try:
    for _t in ('fuente', 'propiedad', 'filtroalerta', 'preciohistorico', 'registroejecucion', 'estadisticanotarial'):
        if _t in SQLModel.metadata.tables:
            del SQLModel.metadata.tables[_t]
except Exception:
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
    tipo_propiedad: Optional[str] = Field(default=None, index=True)  # piso | casa | ático | bajo | dúplex | estudio | local | garaje
    tipo_operacion: Optional[str] = Field(default=None, index=True)  # venta | alquiler

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
    zona_normalizada: Optional[str] = Field(default=None, index=True)  # zona canónica del catálogo
    zona_confianza: Optional[str] = None  # 'exacta' | 'via' | 'debil'
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
    fecha_baja: Optional[datetime] = Field(default=None, index=True)  # when activa became False
    excluir_de_estadisticas: bool = Field(default=False, index=True)  # manual exclusion flag; NOT a sale
    activa: bool = Field(default=True, index=True)
    vista: bool = Field(default=False, index=True)
    descartada: bool = Field(default=False, index=True)
    favorita: bool = Field(default=False, index=True)
    visitada: bool = Field(default=False, index=True)
    notas_visita: Optional[str] = None
    oferta_realizada: Optional[bool] = None
    respuesta_oferta: Optional[str] = None  # pendiente | aceptada | rechazada | contrapropuesta
    precio_oferta: Optional[float] = None
    intentos_fallidos: Optional[int] = Field(default=0)  # consecutive "no data" sold-check strikes
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PrecioHistorico(SQLModel, table=True):
    """Price history record for a property."""

    id: Optional[int] = Field(default=None, primary_key=True)
    propiedad_id: int = Field(foreign_key="propiedad.id", index=True)
    precio: float
    fecha: datetime = Field(default_factory=datetime.utcnow, index=True)


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


class RegistroEjecucion(SQLModel, table=True):
    """Append-only run-log row: one per fuente per scrape/sold_check run."""

    id: Optional[int] = Field(default=None, primary_key=True)
    fuente_id: int = Field(foreign_key="fuente.id", index=True)
    tipo: str = Field(index=True)  # "scrape" | "sold_check"
    fecha: datetime = Field(default_factory=datetime.utcnow, index=True)
    total: int = 0  # properties checked / scraped
    activas: Optional[int] = None
    vendidas: Optional[int] = None  # deactivated this run
    sin_datos: Optional[int] = None  # EMPTY outcomes (strikes issued, incl. non-deactivating)
    errores: int = 0
    nuevas: Optional[int] = None  # scrape only
    duplicadas: Optional[int] = None  # scrape only
    duracion_segundos: Optional[float] = None
    run_id: Optional[str] = Field(default=None, index=True)  # UUID4 shared by all rows from one top-level cycle


class EstadisticaNotarial(SQLModel, table=True):
    """Official Consejo General del Notariado market-stats row.

    Append-only historical series, one row per (location_code, property_type,
    construction_type, last_data_update). property_type/construction_type
    store the human-readable slug (piso|casa, obra_nueva|segunda_mano), not
    the numeric API code — the code→slug mapping lives only in
    scraper/notariado_client.py so the DB stays readable if the vendor
    renumbers.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    location_code: str = Field(index=True)
    property_type: str = Field(index=True)  # piso | casa
    construction_type: str = Field(index=True)  # obra_nueva | segunda_mano
    current_price_per_sqm: Optional[float] = None
    current_number_of_sales: Optional[int] = None
    current_average_price: Optional[float] = None
    current_average_area_sqm: Optional[float] = None
    rate_price_change: Optional[float] = None
    last_data_update: datetime = Field(index=True)  # dedup key (combined w/ combo)
    report_date: datetime
    raw_json: str  # full response body — no credentials, never redacted
    created_at: datetime = Field(default_factory=datetime.utcnow)
    

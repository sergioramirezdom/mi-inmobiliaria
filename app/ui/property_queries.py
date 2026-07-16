"""Capa de consultas de Propiedades 2.0 — funciones puras, sin Streamlit."""

from datetime import datetime, UTC

from sqlalchemy import or_
from sqlmodel import select

from db.models import Propiedad

# label → nombre de campo en Propiedad (el orden define el orden de los chips)
CARACTERISTICAS = {
    "Ascensor": "ascensor",
    "Garaje": "garaje",
    "Trastero": "trastero",
    "Terraza": "terraza",
    "Balcón": "balcon",
    "Patio": "patio",
    "Piscina": "piscina",
    "A/C": "aire_acondicionado",
    "Amueblado": "amueblado",
    "Mascotas": "mascotas",
}

SORT_OPTIONS = {
    "Más reciente": ("fecha_scraping", "desc"),
    "Más antiguo": ("fecha_scraping", "asc"),
    "Precio (menor)": ("precio", "asc"),
    "Precio (mayor)": ("precio", "desc"),
    "m² (mayor)": ("superficie_m2", "desc"),
}

RESULT_LIMIT = 300


def tab_conditions(tab: str) -> list:
    """Condiciones SQL de cada pestaña de estado."""
    if tab == "nuevas":
        return [Propiedad.activa == True, Propiedad.descartada == False, Propiedad.vista == False]
    if tab == "todas":
        return [Propiedad.activa == True, Propiedad.descartada == False]
    if tab == "favoritas":
        return [Propiedad.favorita == True]
    if tab == "descartadas":
        return [Propiedad.descartada == True]
    if tab == "vendidas":
        return [Propiedad.activa == False]
    raise ValueError(f"Pestaña desconocida: {tab}")


def filter_conditions(filters: dict) -> list:
    """Condiciones SQL del formulario de filtros.

    Los numéricos incluyen NULL (dato desconocido no excluye); las
    características exigen True; tipos/distritos usan IN.
    """
    conds = []
    if filters.get("precio_min"):
        conds.append(or_(Propiedad.precio >= filters["precio_min"], Propiedad.precio == None))
    if filters.get("precio_max"):
        conds.append(or_(Propiedad.precio <= filters["precio_max"], Propiedad.precio == None))
    if filters.get("m2_min"):
        conds.append(or_(Propiedad.superficie_m2 >= filters["m2_min"], Propiedad.superficie_m2 == None))
    if filters.get("hab_min"):
        conds.append(or_(Propiedad.habitaciones >= filters["hab_min"], Propiedad.habitaciones == None))
    if filters.get("banos_min"):
        conds.append(or_(Propiedad.banos >= filters["banos_min"], Propiedad.banos == None))
    if filters.get("tipos"):
        conds.append(Propiedad.tipo_propiedad.in_(filters["tipos"]))
    if filters.get("distritos"):
        conds.append(Propiedad.distrito.in_(filters["distritos"]))
    for label in filters.get("caracteristicas", []):
        conds.append(getattr(Propiedad, CARACTERISTICAS[label]) == True)
    if filters.get("search"):
        s = f"%{filters['search']}%"
        conds.append(or_(Propiedad.titulo.ilike(s), Propiedad.descripcion.ilike(s)))
    return conds


def build_stmt(tab: str, filters: dict, sort_key: str):
    """Select completo de la pestaña: condiciones + orden + límite."""
    stmt = select(Propiedad)
    for cond in tab_conditions(tab) + filter_conditions(filters):
        stmt = stmt.where(cond)
    field, direction = SORT_OPTIONS[sort_key]
    col = getattr(Propiedad, field)
    stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc())
    return stmt.limit(RESULT_LIMIT)


def precio_por_m2(precio, superficie):
    if not precio or not superficie:
        return None
    return round(precio / superficie)


def prop_to_dict(prop: Propiedad, fuente_manual_id: int | None = None) -> dict:
    """Dict plano para la tarjeta — sin objetos ORM vivos."""
    bajada = None
    if prop.precio and prop.precio_anterior and prop.precio_anterior > prop.precio:
        bajada = round(prop.precio_anterior - prop.precio)
    dias = None
    if prop.fecha_scraping:
        dias = (datetime.now(UTC).replace(tzinfo=None) - prop.fecha_scraping).days
    return {
        "id": prop.id,
        "titulo": prop.titulo,
        "precio": prop.precio,
        "bajada": bajada,
        "precio_m2": precio_por_m2(prop.precio, prop.superficie_m2),
        "superficie": prop.superficie_m2,
        "habitaciones": prop.habitaciones,
        "banos": prop.banos,
        "tipo": prop.tipo_propiedad,
        "barrio": prop.barrio,
        "municipio": prop.municipio,
        "chips": [label for label, field in CARACTERISTICAS.items() if getattr(prop, field)],
        "fotos": prop.fotos or [],
        "url": prop.url_original,
        "origen": prop.origen_web,
        "dias": dias,
        "es_manual": prop.fuente_id == fuente_manual_id,
        "activa": prop.activa,
        "estado": prop.estado,
        "vista": prop.vista,
        "favorita": prop.favorita,
        "descartada": prop.descartada,
    }


def counts_from_rows(rows) -> dict:
    """Contadores de pestañas desde tuplas (activa, vista, descartada, favorita)."""
    c = {"nuevas": 0, "todas": 0, "favoritas": 0, "descartadas": 0, "vendidas": 0}
    for activa, vista, descartada, favorita in rows:
        if activa and not descartada:
            c["todas"] += 1
            if not vista:
                c["nuevas"] += 1
        if favorita:
            c["favoritas"] += 1
        if descartada:
            c["descartadas"] += 1
        if not activa:
            c["vendidas"] += 1
    return c

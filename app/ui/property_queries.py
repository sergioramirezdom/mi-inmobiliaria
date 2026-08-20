"""Capa de consultas de Propiedades 2.0 — funciones puras, sin Streamlit."""

from datetime import datetime, UTC

from sqlalchemy import func, or_
from sqlmodel import select

from db.models import Propiedad, PrecioHistorico

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
    if tab == "visitadas":
        return [Propiedad.visitada == True]
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
    if filters.get("tipo_operacion"):
        conds.append(Propiedad.tipo_operacion == filters["tipo_operacion"])
    if filters.get("solo_bajadas"):
        conds.append(Propiedad.precio_anterior != None)
        conds.append(Propiedad.precio_anterior > Propiedad.precio)
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


def bajada_total_map(session, ids: list[int]) -> dict[int, float]:
    """id → precio máximo registrado en PrecioHistorico para esa propiedad.

    PrecioHistorico guarda un snapshot por cada cambio de precio detectado.
    Usamos el máximo histórico (no solo el último precio_anterior) para que
    la tarjeta pueda mostrar la bajada TOTAL acumulada, no solo el último paso.
    """
    if not ids:
        return {}
    rows = session.exec(
        select(PrecioHistorico.propiedad_id, func.max(PrecioHistorico.precio))
        .where(PrecioHistorico.propiedad_id.in_(ids))
        .group_by(PrecioHistorico.propiedad_id)
    ).all()
    return {propiedad_id: max_precio for propiedad_id, max_precio in rows}


def prop_to_dict(
    prop: Propiedad,
    fuente_manual_id: int | None = None,
    bajada_map: dict[int, float] | None = None,
) -> dict:
    """Dict plano para la tarjeta — sin objetos ORM vivos."""
    bajada = None
    if prop.precio:
        # El precio más alto conocido: el máximo del historial (varias bajadas
        # sucesivas) o, a falta de historial, el último precio_anterior.
        candidatos = [
            v
            for v in [(bajada_map or {}).get(prop.id), prop.precio_anterior]
            if v
        ]
        if candidatos:
            precio_max = max(candidatos)
            if precio_max > prop.precio:
                bajada = round(precio_max - prop.precio)
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
        "ascensor": prop.ascensor,
        "planta": prop.planta,
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
        "visitada": prop.visitada,
        "oferta_realizada": prop.oferta_realizada,
        "respuesta_oferta": prop.respuesta_oferta,
        "precio_oferta": prop.precio_oferta,
        "favorita": prop.favorita,
        "descartada": prop.descartada,
    }


def counts_from_rows(rows) -> dict:
    """Contadores de pestañas desde tuplas (activa, vista, visitada, descartada, favorita)."""
    c = {"nuevas": 0, "todas": 0, "favoritas": 0, "descartadas": 0, "visitadas": 0, "vendidas": 0}
    for activa, vista, visitada, descartada, favorita in rows:
        if activa and not descartada:
            c["todas"] += 1
            if not vista:
                c["nuevas"] += 1
        if visitada:
            c["visitadas"] += 1
        if favorita:
            c["favoritas"] += 1
        if descartada:
            c["descartadas"] += 1
        if not activa:
            c["vendidas"] += 1
    return c

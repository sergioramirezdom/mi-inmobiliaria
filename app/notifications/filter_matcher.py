"""Match properties against filter criteria."""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Propiedad, FiltroAlerta
from .alert_routing import TIPO_BAJADAS_FAVORITAS

logger = logging.getLogger(__name__)


class FilterMatcher:
    """Matches properties against filter criteria."""

    @staticmethod
    def parse_criteria(criteria_json: str) -> Dict[str, Any]:
        """Parse criteria from JSON string (lenient: for display, never raises).

        Matching goes through ``_load_criteria`` instead, which fails closed.
        """
        try:
            data = json.loads(criteria_json) if criteria_json else {}
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in criteria: {criteria_json}")
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _load_criteria(filtro: FiltroAlerta) -> Optional[Dict[str, Any]]:
        """Strictly load a filter's criteria; None means "unusable, match nothing".

        Missing, blank, corrupt or non-object ``criterios_json`` is logged at
        ERROR and reported as None. Only an explicit JSON object (``{}``
        included: the UI's deliberate "no criteria" alert) is usable.
        """
        raw = filtro.criterios_json
        if raw is None or not str(raw).strip():
            logger.error(
                f"Filter '{filtro.nombre}' has no criterios_json; it matches nothing"
            )
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.error(
                f"Filter '{filtro.nombre}' has invalid criterios_json; it matches nothing"
            )
            return None
        if not isinstance(data, dict):
            logger.error(
                f"Filter '{filtro.nombre}' criterios_json is not an object; "
                "it matches nothing"
            )
            return None
        return data

    @staticmethod
    def match_property(propiedad: Propiedad, criterios: Dict[str, Any]) -> bool:
        """
        Check if property matches all criteria.

        Returns True only if property matches ALL criteria (AND logic).
        """
        if not criterios:
            # No criteria = match all
            return True

        # Check each criterion. A criterion that cannot be evaluated for this
        # property (odd value, missing field) fails closed instead of raising
        # out of the whole alert round.
        for key, value in criterios.items():
            try:
                matched = FilterMatcher._match_criterion(propiedad, key, value)
            except (AttributeError, TypeError, ValueError) as e:
                logger.warning(f"Criterion {key}={value!r} could not be evaluated: {e}")
                return False
            if not matched:
                return False

        return True

    @staticmethod
    def _match_criterion(propiedad: Propiedad, key: str, value: Any) -> bool:
        """Check if property matches a single criterion."""
        if value is None or value == "":
            # Empty criteria = skip this check
            return True

        # Price checks
        if key == "precio_min":
            if propiedad.precio is None:
                return False
            return propiedad.precio >= float(value)

        if key == "precio_max":
            if propiedad.precio is None:
                return False
            return propiedad.precio <= float(value)

        # Size checks
        if key == "m2_min":
            if propiedad.superficie_m2 is None:
                return False
            return propiedad.superficie_m2 >= float(value)

        if key == "m2_max":
            if propiedad.superficie_m2 is None:
                return False
            return propiedad.superficie_m2 <= float(value)

        # Room checks
        if key == "habitaciones":
            if propiedad.habitaciones is None:
                return False
            return propiedad.habitaciones >= int(value)

        if key == "habitaciones_max":
            if propiedad.habitaciones is None:
                return False
            return propiedad.habitaciones <= int(value)

        # Bathroom checks
        if key == "banos":
            if propiedad.banos is None:
                return False
            return propiedad.banos >= int(value)

        # Zone/Neighborhood — OR entre dos vías, para no romper filtros
        # guardados antes de la normalización:
        #   (a) coincidencia exacta con la zona canónica, o
        #   (b) substring del barrio crudo (comportamiento histórico).
        # Al ser OR solo puede añadir coincidencias, nunca quitarlas.
        if key == "barrio":
            if isinstance(value, str):
                zonas = [z.strip().lower() for z in value.split(",") if z.strip()]
            else:
                zonas = [str(z).strip().lower() for z in value if str(z).strip()]
            if not zonas:
                return False

            zona_canonica = (propiedad.zona_normalizada or "").lower()
            if zona_canonica and zona_canonica in zonas:
                return True

            if propiedad.barrio:
                prop_barrio = propiedad.barrio.lower()
                if any(z in prop_barrio for z in zonas):
                    return True

            return False

        # Address (partial match)
        if key == "direccion":
            if propiedad.direccion is None:
                return False
            return value.lower() in propiedad.direccion.lower()

        # Property type (exact match or partial)
        if key == "tipo_propiedad":
            if propiedad.tipo_propiedad is None:
                return False
            return value.lower() in propiedad.tipo_propiedad.lower()

        # State/Condition
        if key == "estado":
            if propiedad.estado is None:
                return False
            return value.lower() in propiedad.estado.lower()

        # Operation type (venta | alquiler)
        if key == "tipo_operacion":
            if propiedad.tipo_operacion is None:
                return False
            return propiedad.tipo_operacion.strip().lower() == str(value).strip().lower()

        # Year built check. Propiedad has no such column, so it can never be
        # confirmed: a filter that requires it matches nothing.
        if key == "año_construccion_min":
            year_built = getattr(propiedad, "year_built", None)
            if year_built is None:
                return False
            return year_built >= int(value)

        # Community fees
        if key == "gastos_comunidad_max":
            if propiedad.precio_comunidad is None:
                return False
            return propiedad.precio_comunidad <= float(value)

        # Boolean amenity checks (a false flag means "no requirement")
        if key in ("ascensor", "garaje", "terraza", "piscina"):
            return bool(getattr(propiedad, key)) if value else True

        # Amenities (check if list contains any of the amenities)
        if key == "amenidades":
            if propiedad.amenidades is None or not propiedad.amenidades:
                return False
            # value should be a list or comma-separated string
            if isinstance(value, str):
                required_amenities = [a.strip().lower() for a in value.split(",")]
            else:
                required_amenities = [str(a).lower() for a in value]

            prop_amenities = [str(a).lower() for a in propiedad.amenidades]
            # All required amenities must be present
            return all(a in " ".join(prop_amenities) for a in required_amenities)

        # Unknown criterion: fail closed, a typo must not widen an alert
        logger.error(f"Unknown criterion {key!r}: property does not match")
        return False

    @staticmethod
    def get_matching_properties(
        propiedades: List[Propiedad],
        filtro: FiltroAlerta
    ) -> List[Propiedad]:
        """Get all properties that match a filter.

        Fails closed: a favourites-only alert never matches new listings and a
        filter with unusable criteria matches nothing.
        """
        if filtro.tipo_alerta == TIPO_BAJADAS_FAVORITAS:
            return []
        criterios = FilterMatcher._load_criteria(filtro)
        if criterios is None:
            return []
        return [p for p in propiedades if FilterMatcher.match_property(p, criterios)]

    @staticmethod
    def format_criteria(criterios: Dict[str, Any]) -> str:
        """Format criteria as readable string."""
        if not criterios:
            return "Sin criterios (todas las propiedades)"

        parts = []
        for key, value in criterios.items():
            if value is None or value == "":
                continue

            # Format based on key
            if key == "precio_min":
                parts.append(f"Precio mínimo: €{float(value):,.0f}")
            elif key == "precio_max":
                parts.append(f"Precio máximo: €{float(value):,.0f}")
            elif key == "m2_min":
                parts.append(f"Mínimo {float(value):.0f}m²")
            elif key == "m2_max":
                parts.append(f"Máximo {float(value):.0f}m²")
            elif key == "habitaciones":
                parts.append(f"Mínimo {int(value)} habitaciones")
            elif key == "habitaciones_max":
                parts.append(f"Máximo {int(value)} habitaciones")
            elif key == "banos":
                parts.append(f"Mínimo {int(value)} baños")
            elif key == "barrio":
                parts.append(f"Zona: {value}")
            elif key == "direccion":
                parts.append(f"Dirección contiene: {value}")
            elif key == "tipo_propiedad":
                parts.append(f"Tipo: {value}")
            elif key == "tipo_operacion":
                parts.append(f"Operación: {value}")
            elif key == "estado":
                parts.append(f"Estado: {value}")
            elif key == "año_construccion_min":
                parts.append(f"Construido después de {int(value)}")
            elif key == "gastos_comunidad_max":
                parts.append(f"Gastos comunidad máx: €{float(value):,.0f}")
            elif key == "amenidades":
                parts.append(f"Amenidades: {value}")
            elif key == "ascensor" and value:
                parts.append("Ascensor ✓")
            elif key == "garaje" and value:
                parts.append("Garaje ✓")
            elif key == "terraza" and value:
                parts.append("Terraza ✓")
            elif key == "piscina" and value:
                parts.append("Piscina ✓")

        return " • ".join(parts) if parts else "Sin criterios"

    @staticmethod
    def create_criteria_dict(
        precio_min: Optional[float] = None,
        precio_max: Optional[float] = None,
        m2_min: Optional[float] = None,
        m2_max: Optional[float] = None,
        habitaciones: Optional[int] = None,
        habitaciones_max: Optional[int] = None,
        banos: Optional[int] = None,
        barrio: Optional[str] = None,
        tipo_propiedad: Optional[str] = None,
        tipo_operacion: Optional[str] = None,
        estado: Optional[str] = None,
        año_construccion_min: Optional[int] = None,
        gastos_comunidad_max: Optional[float] = None,
        amenidades: Optional[str] = None,
        ascensor: bool = False,
        garaje: bool = False,
        terraza: bool = False,
        piscina: bool = False,
    ) -> Dict[str, Any]:
        """Create criteria dictionary from parameters."""
        criteria = {}

        if precio_min is not None:
            criteria["precio_min"] = precio_min
        if precio_max is not None:
            criteria["precio_max"] = precio_max
        if m2_min is not None:
            criteria["m2_min"] = m2_min
        if m2_max is not None:
            criteria["m2_max"] = m2_max
        if habitaciones is not None:
            criteria["habitaciones"] = habitaciones
        if habitaciones_max is not None:
            criteria["habitaciones_max"] = habitaciones_max
        if banos is not None:
            criteria["banos"] = banos
        if barrio:
            criteria["barrio"] = barrio
        if tipo_propiedad:
            criteria["tipo_propiedad"] = tipo_propiedad
        if tipo_operacion:
            criteria["tipo_operacion"] = tipo_operacion
        if estado:
            criteria["estado"] = estado
        if año_construccion_min is not None:
            criteria["año_construccion_min"] = año_construccion_min
        if gastos_comunidad_max is not None:
            criteria["gastos_comunidad_max"] = gastos_comunidad_max
        if amenidades:
            criteria["amenidades"] = amenidades
        if ascensor:
            criteria["ascensor"] = True
        if garaje:
            criteria["garaje"] = True
        if terraza:
            criteria["terraza"] = True
        if piscina:
            criteria["piscina"] = True

        return criteria

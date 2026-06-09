"""Match properties against filter criteria."""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from db.models import Propiedad, FiltroAlerta

logger = logging.getLogger(__name__)


class FilterMatcher:
    """Matches properties against filter criteria."""

    @staticmethod
    def parse_criteria(criteria_json: str) -> Dict[str, Any]:
        """Parse criteria from JSON string."""
        try:
            return json.loads(criteria_json) if criteria_json else {}
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in criteria: {criteria_json}")
            return {}

    @staticmethod
    def match_property(propiedad: Propiedad, criterios: Dict[str, Any]) -> bool:
        """
        Check if property matches all criteria.

        Returns True only if property matches ALL criteria (AND logic).
        """
        if not criterios:
            # No criteria = match all
            return True

        # Check each criterion
        for key, value in criterios.items():
            if not FilterMatcher._match_criterion(propiedad, key, value):
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

        # Zone/Neighborhood (partial match)
        if key == "barrio":
            if propiedad.barrio is None:
                return False
            # Case-insensitive partial match
            return value.lower() in propiedad.barrio.lower()

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

        # Year built check
        if key == "año_construccion_min":
            if propiedad.year_built is None:
                return False
            return propiedad.year_built >= int(value)

        # Community fees
        if key == "gastos_comunidad_max":
            if propiedad.precio_comunidad is None:
                return False
            return propiedad.precio_comunidad <= float(value)

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

        # Unknown criterion (skip)
        logger.debug(f"Unknown criterion: {key}")
        return True

    @staticmethod
    def get_matching_properties(
        propiedades: List[Propiedad],
        filtro: FiltroAlerta
    ) -> List[Propiedad]:
        """Get all properties that match a filter."""
        criterios = FilterMatcher.parse_criteria(filtro.criterios_json)
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
            elif key == "estado":
                parts.append(f"Estado: {value}")
            elif key == "año_construccion_min":
                parts.append(f"Construido después de {int(value)}")
            elif key == "gastos_comunidad_max":
                parts.append(f"Gastos comunidad máx: €{float(value):,.0f}")
            elif key == "amenidades":
                parts.append(f"Amenidades: {value}")

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
        estado: Optional[str] = None,
        año_construccion_min: Optional[int] = None,
        gastos_comunidad_max: Optional[float] = None,
        amenidades: Optional[str] = None,
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
        if estado:
            criteria["estado"] = estado
        if año_construccion_min is not None:
            criteria["año_construccion_min"] = año_construccion_min
        if gastos_comunidad_max is not None:
            criteria["gastos_comunidad_max"] = gastos_comunidad_max
        if amenidades:
            criteria["amenidades"] = amenidades

        return criteria

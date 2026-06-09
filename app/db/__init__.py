"""Database package - models are defined here to ensure single initialization."""

# Import models once at package level
# This ensures SQLModel metadata is only created once, even if Streamlit reloads
from db.models import Fuente, Propiedad, FiltroAlerta  # noqa: F401

__all__ = ["Fuente", "Propiedad", "FiltroAlerta"]

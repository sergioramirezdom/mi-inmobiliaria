"""Single source of truth for listing-date resolution.

Rule: `fecha_publicacion` when set, otherwise `fecha_scraping`. Exposed in
the three shapes the codebase consumes dates in — ORM object / plain dict,
SQLAlchemy column expression, pandas column — so no call site re-implements
the fallback.
"""

from datetime import datetime

import pandas as pd
from sqlalchemy import func

from db.models import Propiedad


def fecha_listado(obj) -> datetime | None:
    """Resolve the listing date for an ORM `Propiedad` or a plain dict."""
    if isinstance(obj, dict):
        return obj.get("fecha_publicacion") or obj.get("fecha_scraping")
    return getattr(obj, "fecha_publicacion", None) or getattr(obj, "fecha_scraping", None)


def fecha_listado_col():
    """SQLAlchemy column expression: COALESCE(fecha_publicacion, fecha_scraping)."""
    return func.coalesce(Propiedad.fecha_publicacion, Propiedad.fecha_scraping)


def with_fecha_listado(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with a `fecha_listado` column added.

    `df` is expected to carry a `fecha_scraping` column (already parsed as
    datetime by callers such as `props_to_df`), and optionally a
    `fecha_publicacion` column.
    """
    df = df.copy()
    if df.empty:
        df["fecha_listado"] = pd.Series(dtype="datetime64[ns]")
        return df
    fecha_scraping = pd.to_datetime(df["fecha_scraping"])
    if "fecha_publicacion" in df.columns:
        fecha_publicacion = pd.to_datetime(df["fecha_publicacion"])
        df["fecha_listado"] = fecha_publicacion.fillna(fecha_scraping)
    else:
        df["fecha_listado"] = fecha_scraping
    return df


def es_candidato_backfill(fecha_scraping, fuente_created_at, umbral_horas: int = 24) -> bool:
    """True if `fecha_scraping` falls within `umbral_horas` of `fuente_created_at`.

    A candidate flags a property likely belonging to a source's initial
    catalog import (bulk backfill), for manual-review surfacing only — it
    never alters KPI/sort behavior by itself.
    """
    if fecha_scraping is None or fuente_created_at is None:
        return False
    delta_horas = abs((fecha_scraping - fuente_created_at).total_seconds()) / 3600
    return delta_horas <= umbral_horas

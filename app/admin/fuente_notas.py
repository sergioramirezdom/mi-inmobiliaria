"""Streamlit-free option list, config templates and `notas` handling for the
Fuentes admin page (kept out of the page so they can be unit-tested).

Editing a Fuente must never silently replace a scraper config the form cannot
represent (issue #46): see `merge_notas`.
"""

import json
from typing import List, Optional, Tuple

# ── Scraper detail-type templates ────────────────────────────────────────────

DETAIL_SCRAPER_OPTIONS: List[Tuple[str, Optional[str]]] = [
    ("Automático (genérico)", None),
    ("Puerto Inmobiliaria", "puerto"),
    ("Mobilia", "mobilia"),
    ("Punto Hogar", "puntohogar"),
    ("Guadalete", "guadalete"),
    ("Jiménez Ruiz", "jimenezruiz"),
    ("Puerto Piso", "puertopiso"),
    ("Alonsaga", "alonsaga"),
    ("Samper", "samper"),
    ("Tular", "tular"),
    ("UriaHomes", "uriahomes"),
    ("Neopolis", "neopolis"),
]

DETAIL_SCRAPER_LABELS = {v: label for label, v in DETAIL_SCRAPER_OPTIONS}

SCRAPER_CONFIG_TEMPLATES = {
    "puntohogar": {
        "detail_scraper_type": "puntohogar",
        "pagination_param": "pagina",
        "pagination_start": 0,
        "pagination_skip_first": True,
        "use_results_per_page": False,
        "max_pages": 10,
        "municipio_filter": "El Puerto de Santa María",
        "selectors": {
            "property_container": "div.card-content",
            "link": "a.card-more",
            "title": "h3.card-title",
        },
    },
    "guadalete": {
        "detail_scraper_type": "guadalete",
        "max_pages": 1,
        "use_results_per_page": False,
        "selectors": {"link_href_contains": "/inmuebles/"},
    },
    "mobilia": {
        "detail_scraper_type": "mobilia",
        "pagination_param": "pag",
        "pagination_start": 1,
        "use_results_per_page": True,
        "selectors": {
            "link_href_contains": "/ref-",
        },
    },
    "puerto": {
        "detail_scraper_type": "puerto",
        "pagination_param": "pag",
        "pagination_start": 1,
        "use_results_per_page": True,
    },
    "jimenezruiz": {
        "detail_scraper_type": "jimenezruiz",
        "verify_ssl": False,
        "max_pages": 1,
        "pagination_skip_first": True,
        "use_results_per_page": False,
        "selectors": {
            "property_container": "div.listado5_contendor_inmueble",
            "link": "a",
            "title": ".listado5_contendor_inmueble_datos_titulo",
            "description": ".listado5_contendor_inmueble_datos_descripcion",
        },
    },
    "puertopiso": {
        "detail_scraper_type": "puertopiso",
        "pagination_param": "pag",
        "pagination_start": 1,
        "pagination_skip_first": True,
        "use_results_per_page": False,
        "max_pages": 10,
        "municipio_filter": "El Puerto de Santa María",
        "selectors": {
            "property_container": "div.mcb-wrap-inner",
            "link": "div.desc a",
            "title": "div.desc p strong",
        },
    },
    "alonsaga": {
        "detail_scraper_type": "alonsaga",
        "selectors": {
            "property_container": "div.listado5_contendor_inmueble",
            "title": "div.listado5_contendor_inmueble_datos_titulo",
        },
        "patterns": {"price_pattern": r"([\d.,]+)\s*€"},
        "pagination_param": "pag",
        "pagination_start": 1,
        "pagination_skip_first": True,
        "use_results_per_page": False,
    },
    "samper": {
        "detail_scraper_type": "samper",
        # Sin municipio_filter: solo hay link_href_contains (sin selector de
        # title), GenericScraper cae en "Sin título" en el listado y el
        # filtro descartaría el 100% de los resultados. La URL ya filtra
        # por El Puerto de Santa María en servidor.
        "max_pages": 1,
        "pagination_param": "pag",
        "pagination_start": 1,
        "pagination_skip_first": True,
        "use_results_per_page": False,
        "selectors": {"link_href_contains": "/Venta-"},
    },
    # Shared with scripts/add_neopolis_fuente.py so the seed and the UI cannot drift.
    "neopolis": {
        # NOTE: listing-page hrefs are relative and have NO leading slash
        # (e.g. "ficha/piso/...", not "/ficha/piso/..."). A leading-slash value
        # here matches zero properties (confirmed live 2026-08-24: 0 found).
        "selectors": {"link_href_contains": "ficha/"},
        "detail_scraper_type": "neopolis",
        "pagination_param": "pag",
        "pagination_start": 1,
        "pagination_skip_first": False,
        # Only the pag=N pagination was verified live; &res=N was never tried.
        "use_results_per_page": False,
        "max_pages": 10,
        "timeout": 120,
        "retries": 2,
        "verify_ssl": True,
    },
    "tular": {
        "detail_scraper_type": "tular",
        # Sin municipio_filter (ref bug #43): solo hay link_href_contains (sin
        # selector de title), GenericScraper cae en "Sin título" en el listado
        # y el filtro descartaría el 100% de los resultados. La URL ya filtra
        # por El Puerto de Santa María + Vivienda en servidor, y TularScraper
        # fija municipio="El Puerto de Santa María".
        # max_pages=1: el buscador Venta+Vivienda+El Puerto devuelve una sola
        # página (contenedor #listado2_paginacion vacío en el T0).
        "max_pages": 1,
        "pagination_param": "pag",
        "pagination_start": 1,
        "pagination_skip_first": True,
        "use_results_per_page": False,
        "selectors": {"link_href_contains": "/Venta-"},
    },
}

DETAIL_SCRAPER_LABELS = {v: label for label, v in DETAIL_SCRAPER_OPTIONS}


def parse_notas(notas: Optional[str]) -> dict:
    """Parse notas field as JSON config, return empty dict on failure."""
    if not notas:
        return {}
    try:
        data = json.loads(notas)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _with_max_pages(config: dict, max_pages: Optional[int]) -> dict:
    """Return config with max_pages set (>0), removed (0) or left alone (None)."""
    config = dict(config)
    if max_pages is not None and max_pages > 0:
        config["max_pages"] = max_pages
    elif max_pages == 0:
        config.pop("max_pages", None)
    return config


def build_notas(
    detail_scraper_type: Optional[str], max_pages_override: Optional[int] = None
) -> Optional[str]:
    """Return notas JSON for a NEW fuente of a given detail_scraper_type."""
    if not detail_scraper_type:
        return None
    template = SCRAPER_CONFIG_TEMPLATES.get(
        detail_scraper_type, {"detail_scraper_type": detail_scraper_type}
    )
    return json.dumps(_with_max_pages(template, max_pages_override), ensure_ascii=False)


def detail_options_for(current_type: Optional[str]) -> List[Tuple[str, Optional[str]]]:
    """Options for the edit form, plus the fuente's current type when the form
    does not know it, so saving keeps it instead of resetting it to generic."""
    if current_type is None or current_type in DETAIL_SCRAPER_LABELS:
        return DETAIL_SCRAPER_OPTIONS
    return DETAIL_SCRAPER_OPTIONS + [(f"{current_type} (personalizado, se conserva)", current_type)]


def merge_notas(
    existing_notas: Optional[str],
    new_detail_type: Optional[str],
    max_pages: Optional[int] = None,
) -> Optional[str]:
    """Notas to store when an existing fuente is edited.

    Applies the form's changes on top of the stored config instead of
    rebuilding it from a template, so selectors, pagination and any custom
    field the form cannot represent survive an unrelated edit. Only an
    explicit switch to another detail scraper with a template replaces the
    config; switching to generic just drops the type. Notas that are not a
    JSON config (free text) are kept unless a scraper type is chosen.
    """
    existing = parse_notas(existing_notas)
    if not existing:
        if new_detail_type is None:
            return existing_notas
        return build_notas(new_detail_type, max_pages)

    if new_detail_type == existing.get("detail_scraper_type"):
        config = existing
    elif new_detail_type in SCRAPER_CONFIG_TEMPLATES:
        config = SCRAPER_CONFIG_TEMPLATES[new_detail_type]
    else:
        config = {k: v for k, v in existing.items() if k != "detail_scraper_type"}
        if new_detail_type:
            config["detail_scraper_type"] = new_detail_type

    config = _with_max_pages(config, max_pages)
    if config == existing:
        return existing_notas
    return json.dumps(config, ensure_ascii=False) if config else None

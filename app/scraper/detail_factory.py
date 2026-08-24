"""Shared detail-scraper factory.

Single source of truth for mapping a Fuente's `detail_scraper_type` string
to its detail-scraper class. Both `paginated_scraper.py` and `sold_checker.py`
must resolve through this registry so they cannot silently diverge again
(the Aug 20 incident: `sold_checker` was missing `uriahomes`/`jimenezruiz`,
mis-classified those properties with the generic fallback scraper, and mass
deactivated them).
"""

from typing import Dict, Optional, Type

from .base import ScraperBase
from .config import ScraperConfig
from .puerto_inmobiliaria import PuertoInmobiliariaScraper
from .mobilia_scraper import MobiliaScraper
from .punto_hogar_scraper import PuntoHogarScraper
from .guadalete_scraper import GuadaleteScraper
from .jimenezruiz_scraper import JimenezRuizScraper
from .puertopiso_scraper import PuertoPisoScraper
from .manual_scraper import ManualScraper
from .alonsaga_scraper import AlonsagaScraper
from .uriahomes_scraper import UriaHomesScraper
from .neopolis_scraper import NeopolisScraper

# Parity source of truth: this must match paginated_scraper.py's if/elif
# chain exactly. tests/test_detail_factory.py enforces this.
DETAIL_SCRAPERS: Dict[str, Type[ScraperBase]] = {
    "mobilia": MobiliaScraper,
    "puntohogar": PuntoHogarScraper,
    "guadalete": GuadaleteScraper,
    "jimenezruiz": JimenezRuizScraper,
    "puertopiso": PuertoPisoScraper,
    "manual_auto": ManualScraper,
    "alonsaga": AlonsagaScraper,
    "uriahomes": UriaHomesScraper,
    "neopolis": NeopolisScraper,
}

DEFAULT_DETAIL_SCRAPER: Type[ScraperBase] = PuertoInmobiliariaScraper


def get_detail_scraper(detail_type: Optional[str], config: ScraperConfig) -> ScraperBase:
    """Resolve a `detail_scraper_type` string to a scraper instance.

    Unknown or missing types fall back to `PuertoInmobiliariaScraper`,
    matching the previous inline behavior in both call sites.
    """
    scraper_class = DETAIL_SCRAPERS.get(detail_type, DEFAULT_DETAIL_SCRAPER)
    return scraper_class(config)

"""Tests for ManualScraper wiring in sold_checker and paginated_scraper."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_get_scraper_manual_auto_returns_manual_scraper():
    """_get_scraper returns ManualScraper for manual_auto detail type."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from scraper.sold_checker import _get_scraper
    from scraper.config import ScraperConfig
    from scraper.manual_scraper import ManualScraper

    config = ScraperConfig()
    config.detail_scraper_type = "manual_auto"
    scraper = _get_scraper("manual_auto", config)
    assert isinstance(scraper, ManualScraper)


def test_get_scraper_other_types_not_manual():
    """_get_scraper does not return ManualScraper for other types."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from scraper.sold_checker import _get_scraper
    from scraper.config import ScraperConfig
    from scraper.manual_scraper import ManualScraper

    config = ScraperConfig()
    scraper = _get_scraper(None, config)
    assert not isinstance(scraper, ManualScraper)


@pytest.mark.asyncio
async def test_sold_checker_price_change_for_manual_auto():
    """check_sold_properties detects and records price change for manual_auto properties."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from scraper.sold_checker import check_sold_properties

    mock_prop = MagicMock()
    mock_prop.activa = True
    mock_prop.precio = 200000.0
    mock_prop.precio_anterior = None
    mock_prop.titulo = "Test property"
    mock_prop.url_original = "https://example.com/prop/1"
    mock_prop.fuente_id = 99
    mock_prop.id = 1
    mock_prop.favorita = True

    mock_fuente = MagicMock()
    mock_fuente.id = 99
    mock_fuente.notas = '{"detail_scraper_type": "manual_auto"}'

    mock_session = MagicMock()
    mock_session.exec.return_value.all.side_effect = [
        [mock_prop],    # propiedades query
        [mock_fuente],  # fuentes query
    ]

    with patch("scraper.sold_checker._get_scraper") as mock_get_scraper:
        mock_scraper = MagicMock()
        mock_scraper.scrape_property_details = AsyncMock(return_value={
            "activa": True,
            "precio": 185000.0,
        })
        mock_get_scraper.return_value = mock_scraper

        stats = await check_sold_properties(mock_session)

    assert mock_prop.precio == 185000.0
    assert mock_prop.precio_anterior == 200000.0
    assert "bajadas_precio" in stats
    assert len(stats["bajadas_precio"]) == 1
    drop = stats["bajadas_precio"][0]
    assert drop["bajada_pct"] == 7.5
    assert drop["propiedad_id"] == 1
    assert drop["favorita"] is True


@pytest.mark.asyncio
async def test_sold_checker_price_drop_entry_favorita_false_for_non_favorite():
    """Non-favourite property drop still records propiedad_id and favorita=False."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

    from scraper.sold_checker import check_sold_properties

    mock_prop = MagicMock()
    mock_prop.activa = True
    mock_prop.precio = 200000.0
    mock_prop.precio_anterior = None
    mock_prop.titulo = "Test property"
    mock_prop.url_original = "https://example.com/prop/2"
    mock_prop.fuente_id = 99
    mock_prop.id = 8
    mock_prop.favorita = False

    mock_fuente = MagicMock()
    mock_fuente.id = 99
    mock_fuente.notas = '{"detail_scraper_type": "manual_auto"}'

    mock_session = MagicMock()
    mock_session.exec.return_value.all.side_effect = [
        [mock_prop],
        [mock_fuente],
    ]

    with patch("scraper.sold_checker._get_scraper") as mock_get_scraper:
        mock_scraper = MagicMock()
        mock_scraper.scrape_property_details = AsyncMock(return_value={
            "activa": True,
            "precio": 185000.0,
        })
        mock_get_scraper.return_value = mock_scraper

        stats = await check_sold_properties(mock_session)

    drop = stats["bajadas_precio"][0]
    assert drop["propiedad_id"] == 8
    assert drop["favorita"] is False

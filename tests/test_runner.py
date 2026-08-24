"""Unit tests for ScraperRunner orchestrator."""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.runner import ScraperRunner
from scraper.config import ScraperConfig
from scraper.exceptions import ValidationException
from scraper.generic import GenericScraper
from db.models import Fuente, Propiedad


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def mock_fuente():
    """Create a mock Fuente."""
    return Fuente(
        id=1,
        nombre="Test Source",
        url="https://example.com/properties",
        tipo_scraper="generic",
        activa=True,
        intervalo_horas=24,
    )


@pytest.fixture
def mock_fuente_with_config():
    """Create a Fuente with custom ScraperConfig in notas."""
    import json

    config_dict = {
        "timeout": 60,
        "retries": 5,
        "selectors": {
            "property_container": "div.property",
            "link": "a.link",
            "price": "span.price",
        },
    }
    notas_json = json.dumps(config_dict)

    return Fuente(
        id=2,
        nombre="Configured Source",
        url="https://example.com/props",
        tipo_scraper="generic",
        activa=True,
        intervalo_horas=24,
        notas=notas_json,
    )


@pytest.fixture
def mock_db_session():
    """Create a mock SQLModel Session."""
    session = MagicMock(spec=Session)
    return session


@pytest.fixture
def scraper_runner(mock_db_session):
    """Create a ScraperRunner instance with mock DB."""
    return ScraperRunner(mock_db_session)


@pytest.fixture
def raw_property_data():
    """Sample raw property data from scraper."""
    return {
        "url_original": "https://example.com/prop/1",
        "titulo": "Piso 3 hab",
        "precio": "€150.000",
        "m2": "100",
        "rooms": "3",
        "bathrooms": "2",
        "address": "Calle Main 123",
    }


# ============================================================
# TESTS FOR _get_scraper()
# ============================================================


class TestGetScraper:
    """Tests for _get_scraper() factory method."""

    def test_get_scraper_generic(self, scraper_runner, mock_fuente):
        """Test getting generic scraper."""
        scraper = scraper_runner._get_scraper(mock_fuente)

        assert isinstance(scraper, GenericScraper)
        assert scraper.config is not None

    def test_get_scraper_with_config_from_notas(self, scraper_runner, mock_fuente_with_config):
        """Test scraper loads config from Fuente.notas."""
        scraper = scraper_runner._get_scraper(mock_fuente_with_config)

        assert isinstance(scraper, GenericScraper)
        # Config should be loaded from notas (custom timeout)
        assert scraper.config.timeout == 60

    def test_get_scraper_default_generic(self, scraper_runner, mock_fuente):
        """Test that generic is default scraper type."""
        mock_fuente.tipo_scraper = None  # No type specified
        scraper = scraper_runner._get_scraper(mock_fuente)

        assert isinstance(scraper, GenericScraper)

    def test_get_scraper_unknown_type(self, scraper_runner, mock_fuente):
        """Test error on unknown scraper type."""
        mock_fuente.tipo_scraper = "unknown_scraper"

        with pytest.raises(ValueError, match="Unknown scraper type"):
            scraper_runner._get_scraper(mock_fuente)


# ============================================================
# TESTS FOR _check_duplicate()
# ============================================================


class TestCheckDuplicate:
    """Tests for _check_duplicate() method."""

    def test_check_duplicate_exists(self, scraper_runner, mock_db_session):
        """Test duplicate detection when property exists."""
        propiedad = Propiedad(
            hash_unico="abc123",
            url_original="https://example.com/1",
            fuente_id=1,
        )

        # Mock query to return existing property
        mock_query = MagicMock()
        mock_query.exec.return_value.first.return_value = Propiedad(hash_unico="abc123")
        mock_db_session.exec.return_value.first.return_value = Propiedad(hash_unico="abc123")

        result = scraper_runner._check_duplicate(propiedad)

        assert result is True

    def test_check_duplicate_not_exists(self, scraper_runner, mock_db_session):
        """Test duplicate detection when property does not exist."""
        propiedad = Propiedad(
            hash_unico="xyz789",
            url_original="https://example.com/2",
            fuente_id=1,
        )

        # Mock query to return None (not found)
        mock_db_session.exec.return_value.first.return_value = None

        result = scraper_runner._check_duplicate(propiedad)

        assert result is False

    def test_check_duplicate_multiple_with_same_hash(self, scraper_runner, mock_db_session):
        """Test that even if multiple properties exist, we detect duplicate."""
        propiedad = Propiedad(
            hash_unico="dup123",
            url_original="https://example.com/3",
            fuente_id=1,
        )

        # Mock returns first match
        mock_db_session.exec.return_value.first.return_value = Propiedad(hash_unico="dup123")

        result = scraper_runner._check_duplicate(propiedad)

        assert result is True

    def test_check_duplicate_db_error_returns_false(self, scraper_runner, mock_db_session):
        """Test that DB errors in duplicate check return False (safe default)."""
        propiedad = Propiedad(
            hash_unico="error123",
            url_original="https://example.com/4",
            fuente_id=1,
        )

        # Mock DB error
        mock_db_session.exec.side_effect = Exception("DB error")

        result = scraper_runner._check_duplicate(propiedad)

        assert result is False


# ============================================================
# TESTS FOR _save_propiedad()
# ============================================================


class TestSavePropiedad:
    """Tests for _save_propiedad() method."""

    def test_save_propiedad_success(self, scraper_runner, mock_db_session):
        """Test successful property save."""
        propiedad = Propiedad(
            hash_unico="save123",
            url_original="https://example.com/5",
            fuente_id=1,
            titulo="Test Property",
        )

        scraper_runner._save_propiedad(propiedad)

        mock_db_session.add.assert_called_once_with(propiedad)
        mock_db_session.commit.assert_called_once()

    def test_save_propiedad_refresh_after_commit(self, scraper_runner, mock_db_session):
        """Test that property is refreshed after commit."""
        propiedad = Propiedad(
            hash_unico="refresh123",
            url_original="https://example.com/6",
            fuente_id=1,
        )

        scraper_runner._save_propiedad(propiedad)

        mock_db_session.refresh.assert_called_once_with(propiedad)

    def test_save_propiedad_rollback_on_error(self, scraper_runner, mock_db_session):
        """Test that transaction is rolled back on error."""
        propiedad = Propiedad(
            hash_unico="error_save",
            url_original="https://example.com/7",
            fuente_id=1,
        )

        mock_db_session.commit.side_effect = Exception("DB insert error")

        with pytest.raises(Exception, match="Failed to save property"):
            scraper_runner._save_propiedad(propiedad)

        mock_db_session.rollback.assert_called_once()


# ============================================================
# TESTS FOR run_scraper() async
# ============================================================


class TestRunScraper:
    """Tests for run_scraper() async method."""

    @pytest.mark.asyncio
    async def test_run_scraper_success_with_new_properties(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Test successful scraping with new properties."""
        # Mock _get_scraper to return mock scraper
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            # normalize_property is sync, use MagicMock for it
            mock_scraper.normalize_property = MagicMock(
                return_value=Propiedad(
                    hash_unico="new_hash_123",
                    url_original=raw_property_data["url_original"],
                    fuente_id=mock_fuente.id,
                    titulo=raw_property_data["titulo"],
                )
            )
            mock_get_scraper.return_value = mock_scraper

            # Mock duplicate check to return False (no duplicate)
            with patch.object(scraper_runner, "_check_duplicate", return_value=False):
                # Mock save
                with patch.object(scraper_runner, "_save_propiedad"):
                    result = await scraper_runner.run_scraper(mock_fuente)

        assert result["fuente_id"] == mock_fuente.id
        assert result["nombre"] == mock_fuente.nombre
        assert result["nuevas"] == 1
        assert result["duplicadas"] == 0
        assert result["errores"] == 0
        assert result["tiempo_segundos"] >= 0

    @pytest.mark.asyncio
    async def test_run_scraper_with_duplicates(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Test scraping that finds duplicates."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            # Return 2 properties
            mock_scraper.scrape.return_value = [raw_property_data, raw_property_data]
            # normalize_property is sync, use MagicMock for it
            mock_scraper.normalize_property = MagicMock(
                return_value=Propiedad(
                    hash_unico="dup_hash",
                    url_original=raw_property_data["url_original"],
                    fuente_id=mock_fuente.id,
                    titulo=raw_property_data["titulo"],
                )
            )
            mock_get_scraper.return_value = mock_scraper

            # Mock duplicate check: first is new, second is duplicate
            with patch.object(
                scraper_runner, "_check_duplicate", side_effect=[False, True]
            ):
                with patch.object(scraper_runner, "_save_propiedad"):
                    result = await scraper_runner.run_scraper(mock_fuente)

        assert result["nuevas"] == 1
        assert result["duplicadas"] == 1
        assert result["errores"] == 0

    @pytest.mark.asyncio
    async def test_run_scraper_with_errors(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Test scraping with error in property processing."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            # normalize_property raises error
            mock_scraper.normalize_property.side_effect = Exception("Parse error")
            mock_get_scraper.return_value = mock_scraper

            result = await scraper_runner.run_scraper(mock_fuente)

        assert result["nuevas"] == 0
        assert result["duplicadas"] == 0
        assert result["errores"] == 1

    @pytest.mark.asyncio
    async def test_run_scraper_scraper_execution_error(
        self, scraper_runner, mock_fuente, mock_db_session
    ):
        """Test when scraper.scrape() itself fails."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = Exception("Network timeout")
            mock_get_scraper.return_value = mock_scraper

            result = await scraper_runner.run_scraper(mock_fuente)

        assert "error" in result
        assert result["nuevas"] == 0
        assert result["duplicadas"] == 0

    @pytest.mark.asyncio
    async def test_run_scraper_invalid_fuente(self, scraper_runner):
        """Test error on None fuente."""
        with pytest.raises(ValidationException):
            await scraper_runner.run_scraper(None)

    @pytest.mark.asyncio
    async def test_run_scraper_empty_results(self, scraper_runner, mock_fuente, mock_db_session):
        """Test scraping that returns no properties."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = []
            mock_get_scraper.return_value = mock_scraper

            result = await scraper_runner.run_scraper(mock_fuente)

        assert result["nuevas"] == 0
        assert result["duplicadas"] == 0
        assert result["errores"] == 0


# ============================================================
# TESTS FOR dry_run_scraper()
# ============================================================


class TestDryRunScraper:
    """Tests for dry_run_scraper() — preview mode, no DB writes."""

    @pytest.mark.asyncio
    async def test_dry_run_scraper_limits_to_default_5(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """8 listing results should only enrich the first 5 by default."""
        raw_data_list = [
            {**raw_property_data, "url_original": f"https://example.com/prop/{i}"}
            for i in range(8)
        ]
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = raw_data_list
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso 3 hab",
                    "precio": 150000,
                    "fotos": [],
                }
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente)

        assert result["encontradas"] == 8
        assert result["muestreadas"] == 5
        assert len(result["resultados"]) == 5
        assert result["con_datos"] == 5

    @pytest.mark.asyncio
    async def test_dry_run_scraper_respects_custom_limit(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """A custom limit caps how many properties are enriched."""
        raw_data_list = [
            {**raw_property_data, "url_original": f"https://example.com/prop/{i}"}
            for i in range(8)
        ]
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = raw_data_list
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso", "precio": 100000, "fotos": [],
                }
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente, limit=2)

        assert result["muestreadas"] == 2
        assert len(result["resultados"]) == 2

    @pytest.mark.asyncio
    async def test_dry_run_scraper_marks_missing_data_as_not_ok(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """A property whose detail scrape yields no title/price is flagged ok=False."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "url_original": raw_property_data["url_original"],
                }
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente)

        assert result["con_datos"] == 0
        assert result["resultados"][0]["ok"] is False

    @pytest.mark.asyncio
    async def test_dry_run_scraper_summarizes_photos(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Photo count and a 2-photo preview are reported per property."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso",
                    "precio": 100000,
                    "fotos": [f"https://x.com/{i}.jpg" for i in range(6)],
                }
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente)

        item = result["resultados"][0]
        assert item["tiene_fotos"] is True
        assert item["num_fotos"] == 6
        assert len(item["fotos_preview"]) == 2

    @pytest.mark.asyncio
    async def test_dry_run_scraper_no_photos(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """A property with no photos reports tiene_fotos=False and an empty preview."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso", "precio": 100000,
                }
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente)

        item = result["resultados"][0]
        assert item["tiene_fotos"] is False
        assert item["num_fotos"] == 0
        assert item["fotos_preview"] == []

    @pytest.mark.asyncio
    async def test_dry_run_scraper_detail_error_does_not_raise(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """A per-property detail-scrape failure is captured, not raised."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.side_effect = Exception("boom")
                mock_get_detail.return_value = mock_detail

                result = await scraper_runner.dry_run_scraper(mock_fuente)

        assert result["con_datos"] == 0
        item = result["resultados"][0]
        assert item["ok"] is False
        assert item["error"] == "boom"

    @pytest.mark.asyncio
    async def test_dry_run_scraper_listing_error_returns_error_no_raise(
        self, scraper_runner, mock_fuente, mock_db_session
    ):
        """A listing-scrape failure is captured in the report, not raised."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.side_effect = Exception("Network timeout")
            mock_get_scraper.return_value = mock_scraper

            result = await scraper_runner.dry_run_scraper(mock_fuente)

        assert "error" in result
        assert result["muestreadas"] == 0
        assert result["resultados"] == []

    @pytest.mark.asyncio
    async def test_dry_run_scraper_invalid_fuente(self, scraper_runner):
        """None fuente raises ValidationException, matching run_scraper()."""
        with pytest.raises(ValidationException):
            await scraper_runner.dry_run_scraper(None)

    @pytest.mark.asyncio
    async def test_dry_run_scraper_empty_listing(
        self, scraper_runner, mock_fuente, mock_db_session
    ):
        """An empty listing produces a valid, empty report."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = []
            mock_get_scraper.return_value = mock_scraper

            result = await scraper_runner.dry_run_scraper(mock_fuente)

        assert result["encontradas"] == 0
        assert result["muestreadas"] == 0
        assert result["con_datos"] == 0
        assert result["resultados"] == []

    @pytest.mark.asyncio
    async def test_dry_run_scraper_does_not_touch_db(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Nothing is ever written to the DB session, unlike run_scraper()."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso", "precio": 100000, "fotos": [],
                }
                mock_get_detail.return_value = mock_detail

                await scraper_runner.dry_run_scraper(mock_fuente)

        mock_db_session.add.assert_not_called()
        mock_db_session.commit.assert_not_called()
        mock_db_session.exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_scraper_resolves_detail_scraper_via_factory(
        self, scraper_runner, mock_db_session, raw_property_data
    ):
        """Any source's detail_scraper_type is resolved through detail_factory —
        this is what makes the dry run work for any Fuente, not just one hardcoded
        source name (the previous run_scraper() behavior)."""
        import json

        fuente = Fuente(
            id=14,
            nombre="Samper",
            url="https://sampergestionesinmobiliarias.es/buscar.php",
            tipo_scraper="generic",
            activa=True,
            notas=json.dumps({"detail_scraper_type": "samper"}),
        )
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_get_scraper.return_value = mock_scraper

            with patch("scraper.runner.get_detail_scraper") as mock_get_detail:
                mock_detail = AsyncMock()
                mock_detail.scrape_property_details.return_value = {
                    "titulo": "Piso", "precio": 100000, "fotos": [],
                }
                mock_get_detail.return_value = mock_detail

                await scraper_runner.dry_run_scraper(fuente)

                assert mock_get_detail.call_args.args[0] == "samper"


# ============================================================
# INTEGRATION TESTS
# ============================================================


class TestIntegration:
    """Integration tests for ScraperRunner."""

    @pytest.mark.asyncio
    async def test_full_scraping_workflow_new_properties(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Test complete workflow: scrape → normalize → dedup → save."""
        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = [raw_property_data]
            mock_propiedad = Propiedad(
                hash_unico="complete_test_hash",
                url_original=raw_property_data["url_original"],
                fuente_id=mock_fuente.id,
                titulo=raw_property_data["titulo"],
            )
            # normalize_property is sync, use MagicMock for it
            mock_scraper.normalize_property = MagicMock(return_value=mock_propiedad)
            mock_get_scraper.return_value = mock_scraper

            with patch.object(scraper_runner, "_check_duplicate", return_value=False):
                with patch.object(scraper_runner, "_save_propiedad") as mock_save:
                    result = await scraper_runner.run_scraper(mock_fuente)

                    # Verify save was called with the property
                    mock_save.assert_called_once_with(mock_propiedad)

        assert result["nuevas"] == 1
        assert result["duplicadas"] == 0

    @pytest.mark.asyncio
    async def test_scraper_selection_by_type(self, scraper_runner, mock_db_session):
        """Test that correct scraper is selected by type."""
        fuente1 = Fuente(
            id=1,
            nombre="Generic Source",
            url="https://example.com",
            tipo_scraper="generic",
        )

        scraper1 = scraper_runner._get_scraper(fuente1)
        assert isinstance(scraper1, GenericScraper)

        # Both should be different instances
        scraper2 = scraper_runner._get_scraper(fuente1)
        assert isinstance(scraper2, GenericScraper)
        assert scraper1 is not scraper2

    @pytest.mark.asyncio
    async def test_statistics_accuracy(
        self, scraper_runner, mock_fuente, mock_db_session, raw_property_data
    ):
        """Test that statistics are accurate after mixed results."""
        # Create 5 raw properties
        raw_data_list = [raw_property_data for _ in range(5)]

        with patch.object(scraper_runner, "_get_scraper") as mock_get_scraper:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = raw_data_list

            # Normalize always returns valid property
            # normalize_property is sync, use MagicMock for it
            mock_scraper.normalize_property = MagicMock(
                return_value=Propiedad(
                    hash_unico="hash_that_changes",  # Will be overridden per call
                    url_original="https://example.com/test",
                    fuente_id=mock_fuente.id,
                )
            )
            mock_get_scraper.return_value = mock_scraper

            # Dedup pattern: new, dup, new, error, dup
            with patch.object(
                scraper_runner, "_check_duplicate", side_effect=[False, True, False, False, True]
            ):
                # Error on 4th property
                with patch.object(
                    scraper_runner, "_save_propiedad", side_effect=[None, None, Exception("Save failed")]
                ):
                    result = await scraper_runner.run_scraper(mock_fuente)

        assert result["nuevas"] == 2
        assert result["duplicadas"] == 2
        assert result["errores"] == 1

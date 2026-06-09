"""Unit tests for Streamlit UI scraping functionality."""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db.models import Fuente, Propiedad
from scraper.runner import ScraperRunner


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def mock_fuente_active():
    """Create an active Fuente."""
    return Fuente(
        id=1,
        nombre="Test Source",
        url="https://example.com/properties",
        tipo_scraper="generic",
        activa=True,
        intervalo_horas=24,
    )


@pytest.fixture
def mock_fuente_inactive():
    """Create an inactive Fuente."""
    return Fuente(
        id=2,
        nombre="Inactive Source",
        url="https://example.com/inactive",
        tipo_scraper="generic",
        activa=False,
        intervalo_horas=24,
    )


@pytest.fixture
def mock_scraping_stats_success():
    """Sample successful scraping stats."""
    return {
        "fuente_id": 1,
        "nombre": "Test Source",
        "nuevas": 5,
        "duplicadas": 2,
        "errores": 0,
        "tiempo_segundos": 12.5,
    }


@pytest.fixture
def mock_scraping_stats_with_errors():
    """Sample scraping stats with errors."""
    return {
        "fuente_id": 1,
        "nombre": "Test Source",
        "nuevas": 3,
        "duplicadas": 1,
        "errores": 2,
        "tiempo_segundos": 15.0,
        "error": "Connection timeout on some items",
    }


@pytest.fixture
def mock_nuevas_propiedades():
    """Sample newly scraped properties."""
    return [
        Propiedad(
            id=1,
            hash_unico="hash_1",
            url_original="https://example.com/prop/1",
            fuente_id=1,
            titulo="Piso 3 hab céntrico",
            precio=150000.0,
            superficie_m2=100.0,
            habitaciones=3,
            banos=2,
            direccion="Calle Mayor 123",
            created_at=datetime.now(),
        ),
        Propiedad(
            id=2,
            hash_unico="hash_2",
            url_original="https://example.com/prop/2",
            fuente_id=1,
            titulo="Apartamento moderno",
            precio=200000.0,
            superficie_m2=80.0,
            habitaciones=2,
            banos=1,
            direccion="Avenida Principal 456",
            created_at=datetime.now(),
        ),
    ]


# ============================================================
# TESTS FOR ScraperRunner INTEGRATION
# ============================================================


class TestScraperRunnerIntegration:
    """Tests for ScraperRunner integration with UI logic."""

    @pytest.mark.asyncio
    async def test_runner_returns_stats(self, mock_fuente_active):
        """Test that ScraperRunner returns proper stats dict."""
        with patch("scraper.generic.GenericScraper") as mock_scraper_class:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = []
            mock_scraper_class.return_value = mock_scraper

            mock_session = MagicMock()
            runner = ScraperRunner(mock_session)
            stats = await runner.run_scraper(mock_fuente_active)

            # Verify stats structure
            assert isinstance(stats, dict)
            assert "fuente_id" in stats
            assert "nombre" in stats
            assert "nuevas" in stats
            assert "duplicadas" in stats
            assert "errores" in stats
            assert "tiempo_segundos" in stats

    @pytest.mark.asyncio
    async def test_runner_with_new_properties(self, mock_fuente_active):
        """Test ScraperRunner processing new properties."""
        raw_data = {
            "url_original": "https://example.com/prop/test",
            "titulo": "Test Property",
            "precio": "€150.000",
            "m2": "100",
        }

        mock_session = MagicMock()
        runner = ScraperRunner(mock_session)

        # Mock the _get_scraper to return a mock scraper
        mock_scraper = AsyncMock()
        mock_scraper.scrape.return_value = [raw_data]

        mock_propiedad = Propiedad(
            hash_unico="test_hash",
            url_original=raw_data["url_original"],
            fuente_id=mock_fuente_active.id,
            titulo=raw_data["titulo"],
        )
        mock_scraper.normalize_property = MagicMock(return_value=mock_propiedad)

        with patch.object(runner, "_get_scraper", return_value=mock_scraper):
            with patch.object(runner, "_check_duplicate", return_value=False):
                with patch.object(runner, "_save_propiedad"):
                    stats = await runner.run_scraper(mock_fuente_active)

        assert stats["nuevas"] == 1
        assert stats["duplicadas"] == 0


# ============================================================
# TESTS FOR UI LOGIC
# ============================================================


class TestUIScrapingLogic:
    """Tests for UI scraping logic and data formatting."""

    def test_propiedad_to_dataframe_formatting(self, mock_nuevas_propiedades):
        """Test conversion of Propiedad to dataframe format."""
        propiedades_data = []
        for prop in mock_nuevas_propiedades:
            propiedades_data.append({
                "Título": prop.titulo or "Sin título",
                "Precio": f"€{prop.precio:,.0f}" if prop.precio else "N/A",
                "m²": f"{prop.superficie_m2:.0f}" if prop.superficie_m2 else "N/A",
                "Hab.": str(prop.habitaciones) if prop.habitaciones else "N/A",
                "Baños": str(prop.banos) if prop.banos else "N/A",
                "Dirección": prop.direccion or "N/A",
                "URL": prop.url_original[:50] + "..." if len(prop.url_original) > 50 else prop.url_original,
            })

        # Verify formatting
        assert len(propiedades_data) == 2
        assert propiedades_data[0]["Título"] == "Piso 3 hab céntrico"
        assert propiedades_data[0]["Precio"] == "€150,000"
        assert propiedades_data[0]["m²"] == "100"
        assert propiedades_data[0]["Hab."] == "3"
        assert propiedades_data[0]["Baños"] == "2"

    def test_propiedad_formatting_with_none_values(self):
        """Test formatting handles None values gracefully."""
        prop = Propiedad(
            hash_unico="hash_none",
            url_original="https://example.com/prop",
            fuente_id=1,
            titulo=None,
            precio=None,
            superficie_m2=None,
            habitaciones=None,
            banos=None,
            direccion=None,
        )

        data = {
            "Título": prop.titulo or "Sin título",
            "Precio": f"€{prop.precio:,.0f}" if prop.precio else "N/A",
            "m²": f"{prop.superficie_m2:.0f}" if prop.superficie_m2 else "N/A",
            "Hab.": str(prop.habitaciones) if prop.habitaciones else "N/A",
            "Baños": str(prop.banos) if prop.banos else "N/A",
            "Dirección": prop.direccion or "N/A",
        }

        assert data["Título"] == "Sin título"
        assert data["Precio"] == "N/A"
        assert data["m²"] == "N/A"
        assert data["Hab."] == "N/A"
        assert data["Baños"] == "N/A"
        assert data["Dirección"] == "N/A"

    def test_url_truncation(self):
        """Test URL truncation for display."""
        long_url = "https://example.com/property/123456789?filter=test&sort=price"
        truncated = long_url[:50] + "..." if len(long_url) > 50 else long_url
        assert len(truncated) == 53  # 50 + 3 for "..."
        assert truncated.endswith("...")

    def test_stats_display_format(self, mock_scraping_stats_success):
        """Test stats are in correct format for display."""
        stats = mock_scraping_stats_success

        # All required fields present
        assert "nuevas" in stats
        assert "duplicadas" in stats
        assert "errores" in stats
        assert "tiempo_segundos" in stats

        # Values are numeric
        assert isinstance(stats["nuevas"], int)
        assert isinstance(stats["duplicadas"], int)
        assert isinstance(stats["errores"], int)
        assert isinstance(stats["tiempo_segundos"], (int, float))

    def test_stats_with_error_field(self, mock_scraping_stats_with_errors):
        """Test stats can include error field."""
        stats = mock_scraping_stats_with_errors

        assert "error" in stats
        assert isinstance(stats["error"], str)
        assert len(stats["error"]) > 0


# ============================================================
# TESTS FOR UI STATE MANAGEMENT
# ============================================================


class TestUIStateManagement:
    """Tests for Streamlit session state management."""

    def test_session_state_key_generation(self):
        """Test session state key naming convention."""
        fuente_id = 1
        key = f"scraping_{fuente_id}"
        assert key == "scraping_1"

    def test_button_state_toggle(self):
        """Test button state toggling logic."""
        # Simulate session state
        session_state = {}
        fuente_id = 1
        key = f"scraping_{fuente_id}"

        # Initial state - not scraping
        assert session_state.get(key, False) is False

        # Set to scraping
        session_state[key] = True
        assert session_state.get(key, False) is True

        # Reset after completion
        session_state[key] = False
        assert session_state.get(key, False) is False

    def test_multiple_fuente_states(self):
        """Test session state with multiple fuentes."""
        session_state = {}

        # Multiple fuentes with independent states
        for fuente_id in [1, 2, 3]:
            key = f"scraping_{fuente_id}"
            session_state[key] = False

        # Only activate one
        session_state["scraping_2"] = True

        assert session_state.get("scraping_1", False) is False
        assert session_state.get("scraping_2", False) is True
        assert session_state.get("scraping_3", False) is False


# ============================================================
# TESTS FOR ERROR HANDLING
# ============================================================


class TestErrorHandling:
    """Tests for error handling in UI scraping."""

    def test_timeout_error_message(self):
        """Test timeout error is handled gracefully."""
        error_type = "timeout"
        error_messages = {
            "timeout": "⏱️ Timeout: El scraping tardó demasiado tiempo",
            "error": "❌ Error durante scraping",
        }

        assert error_messages.get(error_type) is not None

    def test_error_in_stats(self):
        """Test error field in stats is displayed."""
        stats_with_error = {
            "nuevas": 2,
            "duplicadas": 1,
            "errores": 1,
            "tiempo_segundos": 10.0,
            "error": "Connection failed for some items",
        }

        # Should show error if present
        if stats_with_error.get("error"):
            assert isinstance(stats_with_error["error"], str)

    def test_inactive_fuente_button_disabled(self, mock_fuente_inactive):
        """Test button is disabled for inactive fuentes."""
        # Button should be disabled if fuente is not active
        is_disabled = not mock_fuente_inactive.activa
        assert is_disabled is True

    def test_active_fuente_button_enabled(self, mock_fuente_active):
        """Test button is enabled for active fuentes."""
        # Button should be enabled if fuente is active
        is_disabled = not mock_fuente_active.activa
        assert is_disabled is False


# ============================================================
# INTEGRATION TESTS
# ============================================================


class TestUIIntegration:
    """Integration tests for complete UI scraping workflow."""

    @pytest.mark.asyncio
    async def test_complete_scraping_workflow(
        self, mock_fuente_active, mock_scraping_stats_success, mock_nuevas_propiedades
    ):
        """Test complete workflow: click → scrape → display."""
        # Simulate button click
        session_state = {f"scraping_{mock_fuente_active.id}": True}

        # Execute scraper
        with patch("scraper.generic.GenericScraper") as mock_scraper_class:
            mock_scraper = AsyncMock()
            mock_scraper.scrape.return_value = []
            mock_scraper_class.return_value = mock_scraper

            mock_session = MagicMock()
            runner = ScraperRunner(mock_session)
            stats = await runner.run_scraper(mock_fuente_active)

        # Verify stats exist for UI
        assert stats is not None
        assert stats["fuente_id"] == mock_fuente_active.id

        # Simulate fetching new properties
        nuevas_count = stats.get("nuevas", 0)
        assert nuevas_count >= 0

        # Reset state
        session_state[f"scraping_{mock_fuente_active.id}"] = False
        assert session_state.get(f"scraping_{mock_fuente_active.id}") is False

    def test_property_display_with_various_data_types(self, mock_nuevas_propiedades):
        """Test property display with different data types."""
        for prop in mock_nuevas_propiedades:
            # Test float formatting
            if prop.precio:
                formatted_price = f"€{prop.precio:,.0f}"
                assert "€" in formatted_price
                assert "," in formatted_price

            # Test int formatting
            if prop.superficie_m2:
                formatted_m2 = f"{prop.superficie_m2:.0f}"
                assert formatted_m2.isdigit() or "." in formatted_m2

            # Test URL truncation
            truncated_url = (
                prop.url_original[:50] + "..."
                if len(prop.url_original) > 50
                else prop.url_original
            )
            assert len(truncated_url) <= 53

    def test_stats_metrics_calculation(self):
        """Test that metrics from stats can be properly displayed."""
        stats = {
            "nuevas": 5,
            "duplicadas": 2,
            "errores": 0,
            "tiempo_segundos": 12.5,
        }

        # Verify all metrics are displayable
        assert isinstance(stats["nuevas"], int)
        assert isinstance(stats["duplicadas"], int)
        assert isinstance(stats["errores"], int)
        assert isinstance(stats["tiempo_segundos"], float)

        # Total properties processed
        total = stats["nuevas"] + stats["duplicadas"] + stats["errores"]
        assert total == 7

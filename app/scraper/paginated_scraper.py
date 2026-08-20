"""Paginated scraper - handles multiple pages and deduplication."""

import logging
from datetime import datetime
from typing import List, Optional, Dict
from sqlmodel import Session, select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from .base import ScraperBase
from .generic import GenericScraper
from .puerto_inmobiliaria import PuertoInmobiliariaScraper
from .operacion_detector import detectar_operacion, es_garaje
from .detail_factory import get_detail_scraper
from .description_enricher import extract_barrio_from_text
from .config import ScraperConfig
from .zona_normalizer import CatalogoInvalidoError
from .check_outcome import CheckOutcome, classify_check_outcome, apply_check_outcome
from db.models import Fuente, Propiedad, PrecioHistorico


class PaginatedScraper:
    """Scraper that handles pagination and smart deduplication."""

    def __init__(self, db_session: Session, config: Optional[ScraperConfig] = None):
        """Initialize paginated scraper."""
        self.db_session = db_session
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(__name__)
        self.generic_scraper = GenericScraper(config)
        self.detail_scraper = PuertoInmobiliariaScraper(config)

    async def scrape_all_pages(
        self,
        fuente: Fuente,
        results_per_page: int = 48,
        max_pages: Optional[int] = None
    ) -> dict:
        """
        Scrape all pages from a paginated source.

        Args:
            fuente: Source configuration
            results_per_page: Number of results per page (res parameter, default 48)
            max_pages: Maximum pages to scrape (None = all)

        Returns:
            Stats dictionary with results
        """
        stats = {
            "fuente_id": fuente.id,
            "nombre": fuente.nombre,
            "nuevas": 0,
            "duplicadas": 0,
            "errores": 0,
            "paginas_procesadas": 0,
            "urls_encontradas": 0,
        }

        # Load config from fuente.notas if available
        fuente_config = self.config
        if fuente.notas:
            try:
                fuente_config = ScraperConfig.from_fuente_notas(fuente.notas)
                self.generic_scraper.config = fuente_config
            except Exception as e:
                self.logger.warning(f"Could not load config from fuente.notas: {e}")

        # Choose detail scraper based on config — routed through the shared
        # registry (app/scraper/detail_factory.py) so this call site cannot
        # silently diverge from sold_checker.py's resolution again.
        detail_type = fuente_config.detail_scraper_type
        self.detail_scraper = get_detail_scraper(detail_type, fuente_config)

        # Config max_pages overrides the parameter
        if fuente_config.max_pages is not None:
            max_pages = fuente_config.max_pages

        try:
            page = 1
            consecutive_empty_pages = 0

            while True:
                if max_pages and page > max_pages:
                    self.logger.info(f"Reached max pages limit: {max_pages}")
                    break

                self.logger.info(f"\n{'='*80}")
                self.logger.info(f"📄 Processing page {page}...")
                self.logger.info(f"{'='*80}")

                # Build URL with pagination parameters
                if page == 1 and fuente_config.pagination_skip_first:
                    page_url = fuente.url
                else:
                    pagination_param = fuente_config.pagination_param
                    pagination_value = fuente_config.pagination_start + (page - 1)
                    separator = "&" if "?" in fuente.url else "?"
                    page_url = f"{fuente.url}{separator}{pagination_param}={pagination_value}"
                if fuente_config.use_results_per_page:
                    page_url += f"&res={results_per_page}"

                # Scrape the page
                try:
                    # Create a temporary copy of fuente with the paginated URL
                    temp_fuente = Fuente(
                        id=fuente.id,
                        nombre=fuente.nombre,
                        url=page_url,
                        tipo_scraper=fuente.tipo_scraper,
                        activa=fuente.activa,
                        intervalo_horas=fuente.intervalo_horas,
                        notas=fuente.notas
                    )
                    urls_on_page = await self.generic_scraper.scrape(temp_fuente)
                except Exception as e:
                    self.logger.error(f"Error scraping page {page}: {e}")
                    break  # Stop pagination if we can't scrape

                if not urls_on_page:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 2:
                        self.logger.info(f"No properties found on page {page}, stopping pagination")
                        break
                    self.logger.info(f"Page {page} empty, trying next page...")
                    page += 1
                    continue

                # Reset empty page counter
                consecutive_empty_pages = 0
                self.logger.info(f"Found {len(urls_on_page)} properties on page {page}")
                stats["urls_encontradas"] += len(urls_on_page)

                # Check if we got fewer properties than expected (indicates last page).
                # Only meaningful when use_results_per_page=True; otherwise the site
                # controls page size and a small count doesn't mean it's the last page.
                if fuente_config.use_results_per_page and len(urls_on_page) < results_per_page - 5:
                    self.logger.info(f"Page {page} has fewer properties ({len(urls_on_page)} < {results_per_page}), likely last page")
                    will_continue_after = False
                else:
                    will_continue_after = True

                # Process each property
                for raw_data in urls_on_page:
                    try:
                        url_original = raw_data.get("url_original")
                        if not url_original:
                            stats["errores"] += 1
                            continue

                        # Filter by municipio using listing-page title (before fetching detail).
                        # Uses word-level matching to handle variants like "Puerto de Santa María El".
                        if fuente_config.municipio_filter:
                            titulo_listing = raw_data.get("titulo", "")
                            if titulo_listing:
                                import unicodedata
                                def _norm(s):
                                    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
                                filter_words = [w for w in _norm(fuente_config.municipio_filter).split() if len(w) > 2]
                                titulo_norm = _norm(titulo_listing)
                                if not all(w in titulo_norm for w in filter_words):
                                    self.logger.info(f"⏭️ Municipio en listado no coincide ({titulo_listing[:50]}), se omite")
                                    stats["filtradas"] = stats.get("filtradas", 0) + 1
                                    continue

                        # Canonicalize URL if the detail scraper supports it (e.g. puertopiso
                        # strips variable pagination params so the hash is stable across runs)
                        raw_url = url_original
                        if hasattr(self.detail_scraper, 'canonicalize_url'):
                            url_original = self.detail_scraper.canonicalize_url(url_original)
                            raw_data['url_original'] = url_original

                        # Check if already in DB
                        hash_unico = self.generic_scraper.calculate_hash(url_original)
                        stmt = select(Propiedad).where(Propiedad.hash_unico == hash_unico)
                        existing = self.db_session.exec(stmt).first()

                        # Backward compat: records saved before URL canonicalization have a
                        # different hash — also try the raw listing URL hash
                        if not existing and raw_url != url_original:
                            hash_raw = self.generic_scraper.calculate_hash(raw_url)
                            stmt = select(Propiedad).where(Propiedad.hash_unico == hash_raw)
                            existing = self.db_session.exec(stmt).first()

                        if existing:
                            # Re-enrich if metadata is missing (e.g. saved during a broken run)
                            if existing.activa and existing.precio is None:
                                try:
                                    details = await self.detail_scraper.scrape_property_details(url_original)
                                    existing.precio = details.get("precio")
                                    existing.superficie_m2 = details.get("superficie_m2")
                                    existing.habitaciones = details.get("habitaciones")
                                    existing.banos = details.get("banos")
                                    existing.garaje = details.get("garaje")
                                    existing.tipo_propiedad = details.get("tipo_propiedad")
                                    existing.descripcion = details.get("descripcion")
                                    existing.municipio = details.get("municipio")
                                    if existing.precio:
                                        self.db_session.add(PrecioHistorico(propiedad_id=existing.id, precio=existing.precio))
                                    self.db_session.add(existing)
                                    self.db_session.commit()
                                    self.logger.info(f"🔄 Re-enriquecida: {existing.titulo[:50]} {existing.precio}€")
                                except Exception:
                                    pass

                            # For active duplicates older than 3 days, re-check detail page
                            if existing.activa and existing.fecha_scraping:
                                days_old = (datetime.utcnow() - existing.fecha_scraping).days
                                if days_old >= 3:
                                    try:
                                        details = await self.detail_scraper.scrape_property_details(url_original)
                                        # Routed through the same shared gate as sold_checker.py so
                                        # both paths read/update the same strike counter: GONE
                                        # deactivates immediately, EMPTY only deactivates on the
                                        # 2nd confirming strike, ERROR is unreachable here (this
                                        # classifier never returns it — fetch failures are caught
                                        # by the `except Exception: pass` below, untouched).
                                        outcome = classify_check_outcome(details)
                                        estado = details.get("estado", "No disponible") if outcome is CheckOutcome.GONE else None
                                        result = apply_check_outcome(self.db_session, existing, outcome, estado=estado)

                                        if result == "deactivated":
                                            self.logger.info(f"🚫 Marcada como no disponible: {existing.titulo}")
                                            stats["vendidas"] = stats.get("vendidas", 0) + 1
                                        elif result == "strike":
                                            self.logger.info(f"⚠️ Sin datos (1ª confirmación), sigue activa: {existing.titulo}")
                                        elif result == "alive":
                                            # Check for price change
                                            nuevo_precio = details.get("precio")
                                            if nuevo_precio and existing.precio and abs(nuevo_precio - existing.precio) > 100:
                                                precio_anterior = existing.precio
                                                existing.precio_anterior = precio_anterior
                                                existing.precio = nuevo_precio
                                                existing.updated_at = datetime.utcnow()
                                                self.db_session.add(existing)
                                                historial = PrecioHistorico(propiedad_id=existing.id, precio=nuevo_precio)
                                                self.db_session.add(historial)
                                                self.db_session.commit()
                                                if nuevo_precio < precio_anterior:
                                                    bajada = round(100 * (precio_anterior - nuevo_precio) / precio_anterior, 1)
                                                    self.logger.info(f"📉 Bajada {bajada}%: {existing.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")
                                                    stats.setdefault("bajadas_precio", []).append({
                                                        "titulo": existing.titulo,
                                                        "url": existing.url_original,
                                                        "precio_anterior": precio_anterior,
                                                        "precio_nuevo": nuevo_precio,
                                                        "bajada_pct": bajada,
                                                    })
                                                else:
                                                    self.logger.info(f"📈 Subida precio: {existing.titulo[:50]} {precio_anterior:.0f}€ → {nuevo_precio:.0f}€")
                                    except Exception:
                                        pass
                            stats["duplicadas"] += 1
                            continue

                        # Enrich with details
                        self.logger.debug(f"Enriching new property: {url_original[:60]}...")
                        try:
                            details = await self.detail_scraper.scrape_property_details(url_original)
                            raw_data.update(details)
                        except Exception as e:
                            self.logger.warning(f"Could not enrich property: {e}")

                        # Auto-apply barrio from description if still missing
                        if not raw_data.get("barrio"):
                            raw_data["barrio"] = extract_barrio_from_text(
                                raw_data.get("titulo", ""),
                                raw_data.get("descripcion", ""),
                            )

                        # Skip sold properties (don't save them)
                        if not raw_data.get("activa", True):
                            self.logger.info(f"⏭️ Propiedad vendida, no se guarda: {url_original[:60]}")
                            stats["vendidas"] = stats.get("vendidas", 0) + 1
                            continue

                        # Skip rental properties (second check — scrapers also detect, but this is a safety net)
                        operacion = raw_data.get("tipo_operacion") or detectar_operacion(
                            titulo=raw_data.get("titulo"),
                            precio=raw_data.get("precio"),
                            url=url_original,
                            descripcion=raw_data.get("descripcion"),
                        )
                        if operacion == "alquiler":
                            raw_data["tipo_operacion"] = "alquiler"
                            raw_data["activa"] = False
                            raw_data["estado"] = "Alquiler"
                            self.logger.info(f"⏭️ Alquiler detectado, no se guarda: {url_original[:60]}")
                            stats["alquileres"] = stats.get("alquileres", 0) + 1
                            continue

                        # Skip garajes
                        if es_garaje(
                            titulo=raw_data.get("titulo"),
                            tipo_propiedad=raw_data.get("tipo_propiedad"),
                            url=url_original,
                        ):
                            raw_data["tipo_propiedad"] = "garaje"
                            self.logger.info(f"⏭️ Garaje detectado, no se guarda: {url_original[:60]}")
                            stats["garajes"] = stats.get("garajes", 0) + 1
                            continue

                        # Ensure tipo_operacion is set for venta
                        if not operacion:
                            raw_data["tipo_operacion"] = "venta"

                        # Skip properties from wrong municipality
                        if fuente_config.municipio_filter:
                            prop_muni = raw_data.get("municipio", "")
                            if prop_muni and prop_muni.lower() != fuente_config.municipio_filter.lower():
                                self.logger.info(f"⏭️ Municipio diferente ({prop_muni}), se omite: {url_original[:60]}")
                                stats["filtradas"] = stats.get("filtradas", 0) + 1
                                continue

                        # Normalize and save
                        propiedad = self.generic_scraper.normalize_property(raw_data, fuente)
                        self.db_session.add(propiedad)
                        self.db_session.commit()
                        self.db_session.refresh(propiedad)

                        # Save initial price to history
                        if propiedad.precio:
                            self.db_session.add(PrecioHistorico(propiedad_id=propiedad.id, precio=propiedad.precio))
                            self.db_session.commit()

                        self.logger.debug(f"✓ Saved new property: {propiedad.titulo}")
                        stats["nuevas"] += 1

                    except CatalogoInvalidoError:
                        raise
                    except Exception as e:
                        self.logger.warning(f"Error processing property: {e}")
                        stats["errores"] += 1
                        try:
                            self.db_session.rollback()
                        except Exception:
                            pass
                        continue

                stats["paginas_procesadas"] += 1

                # Stop after last page if detected
                if not will_continue_after:
                    self.logger.info(f"Reached last page ({page}), stopping pagination")
                    break

                page += 1

            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"✅ Pagination complete!")
            self.logger.info(f"   Total pages: {stats['paginas_procesadas']}")
            self.logger.info(f"   Total URLs: {stats['urls_encontradas']}")
            self.logger.info(f"   New properties: {stats['nuevas']}")
            self.logger.info(f"   Duplicates skipped: {stats['duplicadas']}")
            self.logger.info(f"{'='*80}")

            return stats

        except Exception as e:
            self.logger.error(f"❌ Pagination failed: {e}")
            stats["error"] = str(e)
            return stats

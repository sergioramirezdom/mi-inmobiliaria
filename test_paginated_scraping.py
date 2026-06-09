#!/usr/bin/env python3
"""Test paginated scraping."""

import sys
import asyncio
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from sqlmodel import Session, select
from db.database import engine
from db.models import Fuente
from scraper.paginated_scraper import PaginatedScraper
from scraper.config import ScraperConfig

# Configure logging to see progress
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)


async def test_paginated_scraping():
    """Test paginated scraping."""
    print("\n" + "="*100)
    print("🧪 TESTING PAGINATED SCRAPING")
    print("="*100 + "\n")

    with Session(engine) as session:
        # Get Puerto Inmobiliaria fuente
        stmt = select(Fuente).where(Fuente.nombre == "Puerto Inmobiliaria")
        fuente = session.exec(stmt).first()

        if not fuente:
            print("❌ Puerto Inmobiliaria fuente not found")
            return False

        print(f"📍 Fuente: {fuente.nombre}")
        print(f"🔗 URL: {fuente.url}\n")

        # Create paginated scraper
        config = ScraperConfig(timeout=60.0)
        scraper = PaginatedScraper(session, config)

        try:
            # Scrape with pagination
            # res=48 is optimal (site has 95 total properties)
            # max_pages=2 means get first 2 pages (for testing)
            # Remove max_pages=None to get ALL pages
            stats = await scraper.scrape_all_pages(
                fuente,
                results_per_page=48,
                max_pages=2  # Testing with 2 pages - change to None for all pages
            )

            print("\n" + "="*100)
            print("✅ SCRAPING COMPLETE")
            print("="*100)
            print(f"\n📊 Results:")
            print(f"   URLs encontradas: {stats['urls_encontradas']}")
            print(f"   Nuevas guardadas: {stats['nuevas']}")
            print(f"   Duplicadas (ignoradas): {stats['duplicadas']}")
            print(f"   Errores: {stats['errores']}")
            print(f"   Páginas procesadas: {stats['paginas_procesadas']}")

            if stats["nuevas"] > 0:
                print(f"\n✅ Successfully scraped and saved {stats['nuevas']} new properties!")
                return True
            else:
                print(f"\n⚠️ No new properties found (all were duplicates or errors)")
                return True  # Still success, just no new data

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    try:
        # Make sure DB is initialized
        from sqlmodel import SQLModel
        SQLModel.metadata.create_all(engine)

        success = asyncio.run(test_paginated_scraping())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

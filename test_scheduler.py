#!/usr/bin/env python3
"""Test ScraperScheduler logic."""

import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent / "app"))

from db.database import engine
from db.models import Fuente
from scraper.scheduler import ScraperScheduler


def test_scheduler_logic():
    """Test scheduler's decision logic."""
    print("\n" + "="*80)
    print("🧪 TESTING SCRAPER SCHEDULER LOGIC")
    print("="*80 + "\n")

    # Create test scheduler (don't use daemon)
    scheduler = ScraperScheduler(check_interval_minutes=1, results_per_page=48)

    with Session(engine) as session:
        # Get all fuentes
        stmt = select(Fuente).where(Fuente.activa == True)
        fuentes = session.exec(stmt).all()

        if not fuentes:
            print("❌ No active fuentes found in database")
            return False

        print(f"📋 Checking {len(fuentes)} active fuente(s):\n")

        all_ok = True
        for fuente in fuentes:
            print(f"Fuente: {fuente.nombre}")
            print(f"  Intervalo: {fuente.intervalo_horas} horas")

            if fuente.ultima_ejecucion:
                last = fuente.ultima_ejecucion.strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"  Última ejecución: {last}")
            else:
                print(f"  Última ejecución: NUNCA")

            # Check if should scrape
            should_scrape = scheduler._should_scrape(fuente)

            if should_scrape:
                print(f"  ✅ Status: 🚀 SHOULD SCRAPE NOW")
            else:
                next_time = scheduler._get_next_scrape_time(fuente)
                time_until = scheduler._format_time_delta(next_time)
                print(f"  ⏭️ Status: Too soon (next in {time_until})")

            print()

        print("="*80)
        print("Test completed successfully ✅")
        print("="*80 + "\n")

        return True


async def test_one_scrape():
    """Test a single scheduled scrape (without daemon)."""
    print("\n" + "="*80)
    print("🧪 TESTING SINGLE SCHEDULED SCRAPE")
    print("="*80 + "\n")

    scheduler = ScraperScheduler(check_interval_minutes=1, results_per_page=48)

    print("Running check_and_scrape() once...\n")
    await scheduler.check_and_scrape()

    print("\n" + "="*80)
    print("Single scrape test completed ✅")
    print("="*80 + "\n")


def update_test_fuente():
    """Manually update a fuente's última_ejecucion for testing."""
    print("\n" + "="*80)
    print("🔧 UPDATING TEST FUENTE")
    print("="*80 + "\n")

    with Session(engine) as session:
        stmt = select(Fuente).where(Fuente.nombre == "Puerto Inmobiliaria")
        fuente = session.exec(stmt).first()

        if not fuente:
            print("❌ Puerto Inmobiliaria not found")
            return

        print(f"Fuente: {fuente.nombre}")
        print(f"Current ultima_ejecucion: {fuente.ultima_ejecucion}")

        # Set to 48 hours ago (should trigger scheduling)
        fuente.ultima_ejecucion = datetime.utcnow() - timedelta(hours=48)
        session.add(fuente)
        session.commit()

        print(f"Updated to: {fuente.ultima_ejecucion} (48 hours ago)")
        print("\n✅ Next check_and_scrape() will scrape this fuente")
        print("="*80 + "\n")


if __name__ == "__main__":
    print("\n🧪 SCHEDULER TEST MENU\n")
    print("1. Check scheduler logic (no scraping)")
    print("2. Run one check_and_scrape() cycle")
    print("3. Update test fuente's última_ejecucion (for testing)")
    print("4. Run all tests")

    choice = input("\nSelect option (1-4): ").strip()

    try:
        if choice == "1":
            test_scheduler_logic()
        elif choice == "2":
            asyncio.run(test_one_scrape())
        elif choice == "3":
            update_test_fuente()
        elif choice == "4":
            test_scheduler_logic()
            update_test_fuente()
            asyncio.run(test_one_scrape())
        else:
            print("Invalid choice")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

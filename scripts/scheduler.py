#!/usr/bin/env python3
"""
Automated scraper scheduler.

Runs continuously and executes scraping for each fuente based on intervalo_horas.

Usage:
    python scripts/scheduler.py              # Check every 1 minute
    python scripts/scheduler.py --interval 5  # Check every 5 minutes
    python scripts/scheduler.py --help        # Show options
"""

import sys
import asyncio
import logging
from pathlib import Path
from argparse import ArgumentParser

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scraper.scheduler import ScraperScheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scheduler.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = ArgumentParser(
        description="Automated scraper scheduler for real estate portals"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Check interval in minutes (default: 1)"
    )
    parser.add_argument(
        "--results-per-page",
        type=int,
        default=48,
        help="Results per page for pagination (default: 48)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check cycle and exit (for GitHub Actions / cron jobs)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force scraping of all active fuentes regardless of intervalo_horas"
    )

    args = parser.parse_args()

    # Create logs directory if needed
    Path("logs").mkdir(exist_ok=True)

    logger.info("=" * 80)
    logger.info("🚀 SCRAPER SCHEDULER STARTING")
    logger.info("=" * 80)
    logger.info(f"Check interval: {args.interval} minute(s)")
    logger.info(f"Results per page: {args.results_per_page}")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 80)

    try:
        scheduler = ScraperScheduler(
            check_interval_minutes=args.interval,
            results_per_page=args.results_per_page
        )
        if args.once:
            if args.force:
                logger.info("▶️  Running forced cycle (--once --force mode)")
                asyncio.run(scheduler.force_scrape_all())
            else:
                logger.info("▶️  Running single cycle (--once mode)")
                asyncio.run(scheduler.check_and_scrape())
            logger.info("✅ Single cycle complete — exiting")
        else:
            asyncio.run(scheduler.start_daemon())

    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("⏹️ SCRAPER SCHEDULER STOPPED")
        logger.info("=" * 80)
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

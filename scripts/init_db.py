#!/usr/bin/env python3
"""Initialize database tables."""

import sys
import logging
from pathlib import Path

# Add parent directory to path so we can import app module
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("✓ Database initialized successfully!")
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        sys.exit(1)

#!/usr/bin/env python3
"""Migrate FiltroAlerta table for advanced filtering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))

from sqlmodel import SQLModel, create_engine, Session, select
from db.database import engine
from db.models import FiltroAlerta

def migrate():
    """Migrate FiltroAlerta table."""
    print("\n" + "="*80)
    print("🔄 MIGRATING FILTROALERTA TABLE")
    print("="*80 + "\n")

    try:
        # Get raw connection to execute ALTER TABLE
        from sqlalchemy import text, inspect

        with engine.connect() as conn:
            inspector = inspect(engine)
            columns = inspector.get_columns('filtroalerta')
            column_names = {col['name'] for col in columns}

            print(f"Current columns: {sorted(column_names)}\n")

            # Add criterios_json column if it doesn't exist
            if 'criterios_json' not in column_names:
                print("➕ Adding 'criterios_json' column...")
                conn.execute(text(
                    "ALTER TABLE filtroalerta ADD COLUMN criterios_json TEXT"
                ))
                conn.commit()
                print("   ✓ Done\n")
            else:
                print("✓ criterios_json column already exists\n")

            # Make chat_id_telegram optional if it's currently NOT NULL
            if 'chat_id_telegram' in column_names:
                print("🔧 Making 'chat_id_telegram' optional...")
                try:
                    conn.execute(text(
                        "ALTER TABLE filtroalerta ALTER COLUMN chat_id_telegram DROP NOT NULL"
                    ))
                    conn.commit()
                    print("   ✓ Done\n")
                except Exception as e:
                    if "does not exist" in str(e) or "already" in str(e).lower():
                        print(f"   ✓ Already optional\n")
                    else:
                        print(f"   ⚠️ Could not modify: {e}\n")

        print("="*80)
        print("✅ MIGRATION COMPLETE")
        print("="*80 + "\n")

        # Verify
        with Session(engine) as session:
            stmt = select(FiltroAlerta)
            filtros = session.exec(stmt).all()
            print(f"📊 FiltroAlerta table has {len(filtros)} records")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)

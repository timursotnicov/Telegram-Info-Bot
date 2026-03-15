"""Database migration system."""
import logging
import aiosqlite

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Migration 1: Add user_id to items and categories
    """
    ALTER TABLE items ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    """,
    """
    ALTER TABLE categories ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_items_user ON items(user_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id);
    """,
]

async def run_migrations(db: aiosqlite.Connection):
    """Run pending migrations."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    """)
    cursor = await db.execute("SELECT MAX(version) as v FROM schema_version")
    row = await cursor.fetchone()
    current = row[0] if row[0] is not None else 0

    for i, sql in enumerate(MIGRATIONS, start=1):
        if i > current:
            try:
                await db.execute(sql)
                await db.execute("INSERT INTO schema_version (version) VALUES (?)", (i,))
                await db.commit()
                logger.info("Migration %d applied", i)
            except Exception as e:
                # Column already exists or similar — skip gracefully
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    await db.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (i,))
                    await db.commit()
                    logger.info("Migration %d skipped (already applied): %s", i, e)
                else:
                    raise

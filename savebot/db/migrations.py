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
    # Migration 5: Add is_pinned column to items
    """
    ALTER TABLE items ADD COLUMN is_pinned BOOLEAN DEFAULT 0;
    """,
    # Migration 6: Add is_read column to items (1=read by default, links set to 0 on save)
    """
    ALTER TABLE items ADD COLUMN is_read BOOLEAN DEFAULT 1;
    """,
    # Migration 7: Add forward_url column for original post link
    """
    ALTER TABLE items ADD COLUMN forward_url TEXT;
    """,
    # Migration 8: Add user_note column for personal annotations
    """
    ALTER TABLE items ADD COLUMN user_note TEXT;
    """,
    # Migration 9: Collections tables
    """
    CREATE TABLE IF NOT EXISTS collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        emoji TEXT DEFAULT '📁',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS collection_items (
        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (collection_id, item_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_collection_items_coll ON collection_items(collection_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_collection_items_item ON collection_items(item_id);
    """,
    # Migration 13: Add daily_brief columns to user_preferences
    """
    ALTER TABLE user_preferences ADD COLUMN daily_brief_enabled INTEGER DEFAULT 0;
    """,
    """
    ALTER TABLE user_preferences ADD COLUMN daily_brief_time TEXT DEFAULT '09:00';
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

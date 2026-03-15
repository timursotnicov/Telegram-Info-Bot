"""Database schema and initialization."""

import aiosqlite

from savebot.db.migrations import run_migrations

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '📁',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('text', 'link', 'forward', 'file')),
    content_text TEXT NOT NULL,
    url TEXT,
    file_id TEXT,
    source TEXT,
    ai_summary TEXT,
    tg_message_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (item_id, tag)
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    content_text,
    ai_summary,
    content='items',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, content_text, ai_summary)
    VALUES (new.id, new.content_text, new.ai_summary);
END;

CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, content_text, ai_summary)
    VALUES ('delete', old.id, old.content_text, old.ai_summary);
END;

CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, content_text, ai_summary)
    VALUES ('delete', old.id, old.content_text, old.ai_summary);
    INSERT INTO items_fts(rowid, content_text, ai_summary)
    VALUES (new.id, new.content_text, new.ai_summary);
END;

CREATE TABLE IF NOT EXISTS pending_states (
    key TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    state_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    auto_save BOOLEAN DEFAULT 1,
    digest_enabled BOOLEAN DEFAULT 1,
    digest_day INTEGER DEFAULT 1,
    digest_time TEXT DEFAULT '10:00',
    language TEXT DEFAULT 'ru',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS digest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    items_included TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()
    await run_migrations(db)
    return db

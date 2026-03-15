"""Database schema and initialization."""

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    emoji TEXT DEFAULT '📁',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()
    return db

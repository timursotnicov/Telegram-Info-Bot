"""Persistent state store — replaces in-memory _pending dict."""
import json
import logging
import aiosqlite

logger = logging.getLogger(__name__)

async def get_state(db: aiosqlite.Connection, key: str) -> dict | None:
    cursor = await db.execute("SELECT data FROM pending_states WHERE key = ?", (key,))
    row = await cursor.fetchone()
    if not row:
        return None
    return json.loads(row[0] if isinstance(row[0], str) else row["data"])

async def set_state(db: aiosqlite.Connection, key: str, user_id: int, state_type: str, data: dict):
    await db.execute(
        "INSERT OR REPLACE INTO pending_states (key, user_id, state_type, data) VALUES (?, ?, ?, ?)",
        (key, user_id, state_type, json.dumps(data, ensure_ascii=False)),
    )
    await db.commit()

async def delete_state(db: aiosqlite.Connection, key: str):
    await db.execute("DELETE FROM pending_states WHERE key = ?", (key,))
    await db.commit()

async def cleanup_expired(db: aiosqlite.Connection, max_age_minutes: int = 60):
    await db.execute(
        "DELETE FROM pending_states WHERE created_at < datetime('now', ?)",
        (f"-{max_age_minutes} minutes",),
    )
    await db.commit()

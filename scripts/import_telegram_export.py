"""Import saved items from a Telegram HTML chat export into SaveBot SQLite.

The export does not contain Telegram file_id values, so media items are restored
as searchable text entries with their exported media path noted in content_text.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

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
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER NOT NULL DEFAULT 0,
    is_pinned BOOLEAN DEFAULT 0,
    is_read BOOLEAN DEFAULT 1,
    forward_url TEXT,
    user_note TEXT
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
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    daily_brief_enabled INTEGER DEFAULT 0,
    daily_brief_time TEXT DEFAULT '09:00'
);

CREATE TABLE IF NOT EXISTS digest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    items_included TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '📁',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_items_user ON items(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id);
CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category_id);
CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(url) WHERE url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pending_states_user ON pending_states(user_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_coll ON collection_items(collection_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_item ON collection_items(item_id);
"""


BOT_SAVE_RE = re.compile(r"✅\s*Сохранено\s+в\s+(.+?)(?:\s*/|\n|$)", re.S)
RELATED_MARKER = "🔗 Похожие записи:"
URL_RE = re.compile(r"https?://[^\s<>()]+", re.I)
HASHTAG_RE = re.compile(r"#([^\s#/]+(?:-[^\s#/]+)*)")


@dataclass
class TelegramMessage:
    message_id: int
    from_name: str
    created_at: str
    text: str
    text_html: str
    reply_to: int | None
    media_paths: list[str]
    source: str | None = None


@dataclass
class ImportedItem:
    tg_message_id: int
    created_at: str
    category_name: str
    category_emoji: str
    content_type: str
    content_text: str
    url: str | None
    source: str | None
    ai_summary: str
    tags: list[str]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag == "br":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line).strip()


def html_to_text(fragment: str) -> str:
    parser = TextExtractor()
    parser.feed(fragment)
    return parser.text()


def strip_tags(fragment: str) -> str:
    return html_to_text(fragment)


def extract_first_div(block: str, class_name: str) -> str:
    marker = f'<div class="{class_name}"'
    start = block.find(marker)
    if start == -1:
        return ""
    open_end = block.find(">", start)
    if open_end == -1:
        return ""

    depth = 1
    pos = open_end + 1
    while depth > 0:
        next_open = block.find("<div", pos)
        next_close = block.find("</div>", pos)
        if next_close == -1:
            return ""
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return block[open_end + 1 : next_close]
            pos = next_close + 6
    return ""


def clean_category_name(value: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", value).strip()
    emoji_chars = []
    while value:
        ch = value[0]
        if ch.isspace():
            value = value[1:]
            continue
        category = unicodedata.category(ch)
        if category.startswith("S") or category.startswith("M") or ch == "\u200d":
            emoji_chars.append(ch)
            value = value[1:]
            continue
        break
    name = value.strip() or "Разное"
    emoji = "".join(emoji_chars).strip() or "📁"
    return name, emoji


def parse_date(title: str) -> str:
    # Telegram export format: 15.03.2026 22:58:05 UTC+02:00
    raw = title.split(" UTC", 1)[0].strip()
    try:
        return datetime.strptime(raw, "%d.%m.%Y %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def parse_message_block(block: str) -> TelegramMessage | None:
    id_match = re.search(r'id="message(-?\d+)"', block)
    if not id_match or "message service" in block:
        return None

    from_match = re.search(r'<div class="from_name">\s*(.*?)\s*</div>', block, re.S)
    date_match = re.search(r'<div class="pull_right date details" title="([^"]+)"', block)
    text_html = extract_first_div(block, "text")
    reply_match = re.search(r"go_to_message(\d+)|GoToMessage\((\d+)\)", block)

    source = None
    forwarded = extract_first_div(block, "forwarded body")
    if forwarded:
        src_match = re.search(r'<div class="from_name">\s*(.*?)\s*(?:<span|\n|</div>)', forwarded, re.S)
        if src_match:
            source = strip_tags(src_match.group(1)).strip() or None

    media_paths = [
        unescape(path)
        for path in re.findall(
            r'href="((?:photos|files|video_files|stickers|images)/[^"]+)"',
            block,
        )
    ]

    return TelegramMessage(
        message_id=int(id_match.group(1)),
        from_name=strip_tags(from_match.group(1)).strip() if from_match else "",
        created_at=parse_date(date_match.group(1)) if date_match else parse_date(""),
        text=html_to_text(text_html),
        text_html=text_html,
        reply_to=int(next(g for g in reply_match.groups() if g)) if reply_match else None,
        media_paths=media_paths,
        source=source,
    )


def parse_export(export_dir: Path) -> list[TelegramMessage]:
    messages: list[TelegramMessage] = []
    for html_file in sorted(export_dir.glob("messages*.html")):
        html = html_file.read_text(encoding="utf-8")
        blocks = re.split(r"(?=\n\s*<div class=\"message )", html)
        for block in blocks:
            message = parse_message_block(block)
            if message:
                messages.append(message)
    return messages


def parse_saved_item(bot_message: TelegramMessage, source_message: TelegramMessage) -> ImportedItem | None:
    if "✅" not in bot_message.text or "Сохранено в" not in bot_message.text:
        return None

    save_match = BOT_SAVE_RE.search(bot_message.text)
    if not save_match:
        return None
    category_name, category_emoji = clean_category_name(save_match.group(1))

    em_match = re.search(r"<(?:em|i)>(.*?)</(?:em|i)>", bot_message.text_html, re.S)
    ai_summary = strip_tags(em_match.group(1)).strip() if em_match else ""

    tags_area = bot_message.text
    if RELATED_MARKER in tags_area:
        tags_area = tags_area.split(RELATED_MARKER, 1)[0]
    tags = []
    for tag in HASHTAG_RE.findall(tags_area):
        normalized = tag.strip().replace("-", "_")
        if normalized and normalized not in tags:
            tags.append(normalized)

    content_text = source_message.text.strip()
    if source_message.media_paths:
        media_note = "\n".join(f"[exported_media] {path}" for path in source_message.media_paths)
        content_text = f"{content_text}\n\n{media_note}".strip() if content_text else media_note

    if not content_text:
        content_text = ai_summary or f"Telegram message {source_message.message_id}"

    url_match = URL_RE.search(content_text)
    url = url_match.group(0).rstrip(".,)") if url_match else None
    content_type = "file" if source_message.media_paths else "link" if url else "forward" if source_message.source else "text"

    return ImportedItem(
        tg_message_id=source_message.message_id,
        created_at=source_message.created_at,
        category_name=category_name,
        category_emoji=category_emoji,
        content_type=content_type,
        content_text=content_text,
        url=url,
        source=source_message.source,
        ai_summary=ai_summary,
        tags=tags[:3],
    )


def extract_items(messages: list[TelegramMessage]) -> list[ImportedItem]:
    by_id = {message.message_id: message for message in messages}
    items: list[ImportedItem] = []
    seen_message_ids: set[int] = set()

    for message in messages:
        if message.reply_to is None:
            continue
        source = by_id.get(message.reply_to)
        if not source or source.message_id in seen_message_ids:
            continue
        item = parse_saved_item(message, source)
        if item:
            items.append(item)
            seen_message_ids.add(source.message_id)

    return items


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
        """
    )
    conn.commit()


def get_or_create_category(conn: sqlite3.Connection, user_id: int, name: str, emoji: str) -> int:
    row = conn.execute(
        "SELECT id FROM categories WHERE user_id = ? AND name = ?",
        (user_id, name),
    ).fetchone()
    if row:
        return int(row[0])
    cursor = conn.execute(
        "INSERT INTO categories (user_id, name, emoji) VALUES (?, ?, ?)",
        (user_id, name, emoji),
    )
    return int(cursor.lastrowid)


def insert_item(conn: sqlite3.Connection, user_id: int, item: ImportedItem) -> bool:
    existing = conn.execute(
        "SELECT id FROM items WHERE user_id = ? AND tg_message_id = ?",
        (user_id, item.tg_message_id),
    ).fetchone()
    if existing:
        return False

    if item.url:
        existing = conn.execute(
            "SELECT id FROM items WHERE user_id = ? AND url = ?",
            (user_id, item.url),
        ).fetchone()
        if existing:
            return False

    existing = conn.execute(
        "SELECT id FROM items WHERE user_id = ? AND content_text = ?",
        (user_id, item.content_text),
    ).fetchone()
    if existing:
        return False

    category_id = get_or_create_category(conn, user_id, item.category_name, item.category_emoji)
    cursor = conn.execute(
        """
        INSERT INTO items (
            user_id, category_id, content_type, content_text, url, source,
            ai_summary, tg_message_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            category_id,
            item.content_type,
            item.content_text,
            item.url,
            item.source,
            item.ai_summary,
            item.tg_message_id,
            item.created_at,
        ),
    )
    item_id = int(cursor.lastrowid)
    for tag in item.tags:
        conn.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )
    return True


def infer_user_id(conn: sqlite3.Connection) -> int | None:
    rows = conn.execute("SELECT DISTINCT user_id FROM items WHERE user_id != 0").fetchall()
    if len(rows) == 1:
        return int(rows[0][0])
    rows = conn.execute("SELECT DISTINCT user_id FROM categories WHERE user_id != 0").fetchall()
    if len(rows) == 1:
        return int(rows[0][0])
    return None


def import_items(db_path: Path, items: list[ImportedItem], user_id: int | None) -> tuple[int, int, int]:
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        if user_id is None:
            user_id = infer_user_id(conn)
        if user_id is None:
            raise SystemExit("Could not infer user_id. Pass --user-id.")

        imported = 0
        skipped = 0
        for item in items:
            if insert_item(conn, user_id, item):
                imported += 1
            else:
                skipped += 1
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM items WHERE user_id = ?", (user_id,)).fetchone()[0]
        return imported, skipped, int(total)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path, help="Telegram Desktop ChatExport_* directory")
    parser.add_argument("--db", type=Path, default=Path("savebot.db"), help="Target SQLite DB path")
    parser.add_argument("--seed-db", type=Path, help="Optional existing DB to copy before importing")
    parser.add_argument("--user-id", type=int, help="Telegram user ID owner for imported items")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing")
    args = parser.parse_args(argv)

    if not args.export_dir.exists():
        raise SystemExit(f"Export directory does not exist: {args.export_dir}")

    messages = parse_export(args.export_dir)
    items = extract_items(messages)

    if args.dry_run:
        print(f"messages={len(messages)} saved_items={len(items)}")
        by_category: dict[str, int] = {}
        for item in items:
            by_category[item.category_name] = by_category.get(item.category_name, 0) + 1
        for category, count in sorted(by_category.items(), key=lambda pair: pair[1], reverse=True):
            print(f"{count:4d} {category}")
        return 0

    if args.seed_db:
        if not args.seed_db.exists():
            raise SystemExit(f"Seed DB does not exist: {args.seed_db}")
        if args.db.exists():
            args.db.rename(args.db.with_suffix(args.db.suffix + ".before-import"))
        shutil.copy2(args.seed_db, args.db)

    imported, skipped, total = import_items(args.db, items, args.user_id)
    print(f"parsed={len(items)} imported={imported} skipped={skipped} total={total} db={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

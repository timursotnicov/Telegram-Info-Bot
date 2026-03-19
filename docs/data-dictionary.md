# Data Dictionary

Full schema reference for SaveBot database. Combines base schema (`savebot/db/models.py`) with all migrations (`savebot/db/migrations.py`).

---

## Tables

### categories

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER | AUTOINCREMENT | Primary key |
| user_id | INTEGER | 0 | Telegram user ID (owner) |
| name | TEXT | — | Category name (unique per user) |
| emoji | TEXT | '📁' | Display emoji |
| created_at | DATETIME | CURRENT_TIMESTAMP | When created |

**Constraints:** UNIQUE(user_id, name)
**Indexes:** idx_categories_user(user_id)

---

### items

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER | AUTOINCREMENT | Primary key |
| user_id | INTEGER | 0 | Telegram user ID (owner) |
| category_id | INTEGER | NULL | FK to categories(id), ON DELETE SET NULL |
| content_type | TEXT | — | One of: text, link, forward, file |
| content_text | TEXT | — | Main text content (original message, OCR, link+metadata) |
| url | TEXT | NULL | Extracted URL (for link type) |
| file_id | TEXT | NULL | Telegram file_id (for file type) |
| source | TEXT | NULL | Forward origin (channel title or user name) |
| ai_summary | TEXT | NULL | AI-generated summary (~200 chars max) |
| tg_message_id | INTEGER | NULL | Original Telegram message ID (for duplicate detection) |
| forward_url | TEXT | NULL | Original post link for channel forwards (e.g. https://t.me/channel/123) |
| is_pinned | BOOLEAN | 0 | Whether item is pinned by user |
| is_read | BOOLEAN | 1 | Read status (links set to 0 on save) |
| user_note | TEXT | NULL | User's personal annotation |
| created_at | DATETIME | CURRENT_TIMESTAMP | When saved |

**Constraints:** CHECK(content_type IN ('text', 'link', 'forward', 'file'))
**Indexes:** idx_items_user(user_id), idx_items_created(created_at DESC), idx_items_category(category_id), idx_items_url(url) WHERE url IS NOT NULL

---

### item_tags

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| item_id | INTEGER | — | FK to items(id), ON DELETE CASCADE |
| tag | TEXT | — | Tag name (normalized: hyphens replaced with underscores) |

**Constraints:** PRIMARY KEY (item_id, tag)
**Indexes:** idx_item_tags_tag(tag)

---

### items_fts (FTS5 virtual table)

| Column | Type | Description |
|--------|------|-------------|
| content_text | TEXT | Mirrors items.content_text |
| ai_summary | TEXT | Mirrors items.ai_summary |

Content table: items, content_rowid: id.
Kept in sync via triggers: items_ai (INSERT), items_ad (DELETE), items_au (UPDATE).

---

### pending_states

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| key | TEXT | — | Primary key (format: "{state_type}_{user_id}" or "{user_id}_{msg_id}") |
| user_id | INTEGER | — | Telegram user ID |
| state_type | TEXT | — | State kind (e.g. search_prompt, save, edit_tags, rename_cat) |
| data | TEXT | — | JSON-serialized state payload |
| created_at | DATETIME | CURRENT_TIMESTAMP | When state was created |

**Indexes:** idx_pending_states_user(user_id)

---

### user_preferences

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| user_id | INTEGER | — | Primary key, Telegram user ID |
| auto_save | BOOLEAN | 1 | Auto-save incoming content (1=yes, 0=manual confirm) |
| digest_enabled | BOOLEAN | 1 | Weekly digest enabled |
| digest_day | INTEGER | 1 | Day of week for digest (1=Monday) |
| digest_time | TEXT | '10:00' | Time for weekly digest (HH:MM) |
| language | TEXT | 'ru' | UI language |
| daily_brief_enabled | INTEGER | 0 | Daily brief enabled (1=yes) |
| daily_brief_time | TEXT | '09:00' | Time for daily brief (HH:MM) |
| created_at | DATETIME | CURRENT_TIMESTAMP | When preferences were created |

---

### digest_log

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER | AUTOINCREMENT | Primary key |
| user_id | INTEGER | — | Telegram user ID |
| items_included | TEXT | NULL | JSON array of item IDs included in digest |
| sent_at | DATETIME | CURRENT_TIMESTAMP | When digest was sent |

---

### collections

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER | AUTOINCREMENT | Primary key |
| user_id | INTEGER | — | Telegram user ID (owner) |
| name | TEXT | — | Collection name (unique per user) |
| emoji | TEXT | '📁' | Display emoji |
| created_at | DATETIME | CURRENT_TIMESTAMP | When created |

**Constraints:** UNIQUE(user_id, name)

---

### collection_items

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| collection_id | INTEGER | — | FK to collections(id), ON DELETE CASCADE |
| item_id | INTEGER | — | FK to items(id), ON DELETE CASCADE |
| added_at | DATETIME | CURRENT_TIMESTAMP | When item was added to collection |

**Constraints:** PRIMARY KEY (collection_id, item_id)
**Indexes:** idx_collection_items_coll(collection_id), idx_collection_items_item(item_id)

---

## Sample Items

### 1. Link item

```python
{
    "id": 42,
    "user_id": 123456,
    "category_id": 1,
    "content_type": "link",
    "content_text": "https://example.com/article\n\nTitle: How to Learn Python\nDescription: A beginner guide",
    "url": "https://example.com/article",
    "file_id": None,
    "source": None,
    "ai_summary": "Guide for Python beginners covering basics and best practices",
    "tg_message_id": 9001,
    "forward_url": None,
    "is_pinned": 0,
    "is_read": 0,
    "user_note": None,
    "created_at": "2026-03-15 14:30:00",
    "tags": ["python", "programming", "tutorial"]
}
```

### 2. Text item

```python
{
    "id": 43,
    "user_id": 123456,
    "category_id": 3,
    "content_type": "text",
    "content_text": "Remember to check quarterly reports before Friday meeting",
    "url": None,
    "file_id": None,
    "source": None,
    "ai_summary": "Reminder: review quarterly reports before Friday",
    "tg_message_id": 9002,
    "forward_url": None,
    "is_pinned": 1,
    "is_read": 1,
    "user_note": "Ask Maria for latest numbers",
    "created_at": "2026-03-18 09:15:00",
    "tags": ["work", "reports"]
}
```

### 3. Forward item

```python
{
    "id": 44,
    "user_id": 123456,
    "category_id": 1,
    "content_type": "forward",
    "content_text": "New GPT-5 model released with 10x context window and native tool use",
    "url": None,
    "file_id": None,
    "source": "AI News Channel",
    "ai_summary": "GPT-5 launched with larger context and built-in tool support",
    "tg_message_id": 9003,
    "forward_url": "https://t.me/ainews/4567",
    "is_pinned": 0,
    "is_read": 1,
    "user_note": None,
    "created_at": "2026-03-19 20:45:00",
    "tags": ["ai", "gpt", "news"]
}
```

---

## Business Rules

1. **Tag normalization:** Hyphens in tags are replaced with underscores on save (`tag.replace("-", "_")` in `queries.save_item` and `queries.update_item_tags`).

2. **Tag truncation in callbacks:** Tags used in callback_data are truncated to 20 characters (`_truncate_tag()` in browse.py) to stay under the 64-byte Telegram limit.

3. **Allowed content types:** `content_type` must be one of: `text`, `link`, `forward`, `file`. Enforced by CHECK constraint in the database.

4. **FTS5 index scope:** The full-text search index (`items_fts`) covers only `content_text` and `ai_summary`. Tags and other fields are not searchable via FTS.

5. **AI summary length:** AI summaries are generated as short descriptions, roughly 200 characters max.

6. **Duplicate detection order:** `find_duplicate()` checks in this priority:
   1. `forward_url` (most specific for channel forwards)
   2. `tg_message_id` (message-level dedup)
   3. `url` (link-level dedup)
   4. `content_text` (text-level dedup, least specific)

7. **Default categories:** 7 preset categories are created for each new user on first save via `ensure_default_categories()`:
   - Технологии (💻), Финансы (💰), Здоровье (🏋️), Обучение (📚), Работа (🏢), Творчество (🎨), Разное (📥)

8. **AI classifier constraint:** The AI classifier picks ONLY from the user's existing categories. It never creates new categories. If the AI suggests a category name that doesn't exist, the save flow falls back to "Разное".

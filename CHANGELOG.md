# Changelog

All notable changes to SaveBot are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.7.0] - 2026-03-20

### Added
- 7 default categories (Технологии, Финансы, Здоровье, Обучение, Работа, Творчество, Разное) — seeded for new users
- Post-save category buttons — 7 category buttons shown after auto-save for instant re-categorization
- `get_category_by_name()` query for exact category lookup
- Enhanced duplicate detection — checks forward_url and tg_message_id before URL and content
- Data dictionary (`docs/data-dictionary.md`) with full merged schema, sample items, and business rules
- Function index TOC in queries.py docstring for faster agent navigation
- 22 new tests (181 total) covering default categories, duplicate detection, save flow, removed features

### Changed
- AI classifier now picks ONLY from existing categories, never creates new ones
- Save flow uses `get_category_by_name` + "Разное" fallback instead of `get_or_create_category`
- Quick capture (`!text`) saves to "Разное" instead of "Inbox"
- Browse "More" menu simplified — removed Channels and Forgotten buttons
- Browse categories footer — removed Tags button, kept only "Ещё"
- `/ask` command temporarily disabled (stub reply)
- Removed ForceReply in search flow — fixes persistent keyboard disappearing

### Removed
- `/ask` from bot commands menu
- "🏷 Теги", "📨 Каналы", "🕸 Забытые записи" navigation buttons

## [0.6.0] - 2026-03-16

### Added
- Daily Brief — configurable daily summary of recent saves
- Daily Brief scheduler job and settings UI toggle
- Daily Brief DB migration and query functions

### Changed
- Comprehensive unit test suite — 103 new tests (31 to 134 total)

## [0.5.0] - 2026-03-16

### Added
- Collections — browse, add-to, create collections from item view
- Collections DB migration and CRUD functions
- Related Items button in item view
- Multi-strategy related items lookup (tags, category, FTS)

### Fixed
- Collection context_id passthrough and related context preservation
- IntegrityError on duplicate collection items
- Replaced monolithic get_related_items with focused get_similar_items_fts

## [0.4.0] - 2026-03-16

### Added
- Quick capture with `!` prefix — saves to Inbox without AI classification
- Annotations on saved items
- Improved `/ask` command with better answer synthesis

### Changed
- Optimized all AI prompts for small free models
- Fixed system role bug (gemma does not support separate system role)

## [0.3.0] - 2026-03-16

### Added
- UX overhaul — button-driven interface with persistent keyboard
- Quick delete from list view with inline confirmation
- Search via keyboard button
- Wait messages during AI processing

### Fixed
- State dispatcher falsy check — empty dict `{}` treated as no state
- AI classifier system role error with fallback on 400
- Forward links and AI specificity improvements
- Tag editing and state dispatcher fixes
- Post-delete context loss in item view
- HTML angle bracket escaping in usage messages
- Frozen Message object workaround for keyboard search
- Tag hyphen normalization (replaced with underscores)

## [0.2.0] - 2026-03-15

### Added
- Bot menu commands and redesigned `/start`
- `/clear` and `/clearall` commands
- pytest test suite (16 tests) and inline query mode
- Knowledge map (`/map`) and forgotten items (`/forgotten`)

### Fixed
- AI model fallback chain for 429 rate limits
- Switched to gemma-3-27b model with HTML-escaped AI output
- aiogram.exceptions import path fix

## [0.1.0] - 2026-03-15

### Added
- Initial bot: auto-save with AI categorization
- Browse by category, search, `/ask` AI Q&A
- Tag system, pinned items, read list
- SQLite database with FTS5 full-text search
- OpenRouter AI integration with model fallback chain
- Oracle Cloud deploy script with systemd service

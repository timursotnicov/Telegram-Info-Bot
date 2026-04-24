# Verification Plan
## Feature: Navigation Redesign

## Build & Types
- [ ] `python -c "import savebot.bot"` passes (all imports resolve)

## Tests
- [ ] `python -m pytest tests/ -v` all pass

## Spec Checks
- [ ] File `savebot/handlers/cleanup.py` exists and has `router` attribute
- [ ] File `savebot/services/ai_cleanup.py` exists and has `analyze_categories` function
- [ ] `MAIN_KEYBOARD` in manage.py contains "Все записи" (not "Категории")
- [ ] `BUTTON_TEXTS` in menu.py contains "⚙️ Настройки"
- [ ] `BUTTON_TEXTS` in menu.py contains backward compat "📂 Категории"
- [ ] `_categories_markup` in browse_core.py uses `browse_cat:` (not `cm:`)
- [ ] `_text_list_with_buttons` function exists in browse_core.py
- [ ] `_format_item_list_entry` function exists in browse_core.py
- [ ] No `bm:hub` handler in browse.py
- [ ] No `_more_markup` in browse_core.py
- [ ] No `_show_collections` in browse_core.py
- [ ] `settings_cleanup` callback in settings.py or cleanup.py
- [ ] `EXPECTED_ROUTER_ORDER` includes "cleanup"
- [ ] Stub response for /tags command exists

## Human Checks
- [ ] Send a message to bot → verify new keyboard appears (4 buttons)
- [ ] Tap "📂 Все записи" → see category list
- [ ] Tap a category → see item list directly (no sub-menu)
- [ ] Item list shows text format (title, date, tags) with number buttons
- [ ] Tap "🔍 Поиск" → search → results in text format
- [ ] Tap "⚙️ Настройки" → see settings with "🧹 Умная уборка" button

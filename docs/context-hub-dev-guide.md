# Context Hub — руководство для разработки

## Что такое Context Hub

Context Hub — это open-source инструмент (лицензия MIT) для курирования и доставки документации
AI-агентам (Claude, Cursor, Copilot и др.). Помогает агентам работать с актуальными доками
вместо устаревших данных из обучающей выборки.

## Зачем нам это

Telegram-Info-Bot использует несколько внешних API:
- **OpenRouter API** — для классификации, поиска, OCR
- **aiogram v3** — Telegram Bot Framework
- **aiosqlite** — async SQLite
- **APScheduler** — планировщик задач

Context Hub позволяет подгружать актуальную документацию по этим API при работе с AI-агентами.

## Как использовать при разработке

### 1. Установка CLI

```bash
npm install -g @anthropic-ai/context-hub
```

### 2. Поиск релевантных доков

```bash
# Найти доки по OpenRouter API
chub search "openrouter chat completions"

# Найти доки по aiogram v3
chub search "aiogram dispatcher router"

# Найти доки по SQLite FTS5
chub search "sqlite fts5 full text search"
```

### 3. Подгрузка документации

```bash
# Скачать конкретный пакет документации
chub fetch <package-name>
```

### 4. Использование с Claude Code

При работе в Claude Code, Context Hub автоматически предоставляет контекст.
Просто убедитесь что нужные пакеты документации установлены.

## Полезные сценарии

| Задача | Что подгрузить |
|--------|---------------|
| Изменить AI-промпты | OpenRouter API docs, модели Gemma/Qwen |
| Добавить хендлер | aiogram v3 routers, filters, middleware |
| Оптимизировать поиск | SQLite FTS5, query syntax |
| Настроить деплой | systemd, webhook vs polling |

## Лицензия MIT — что это значит

- Можно использовать бесплатно, включая коммерческие проекты
- Можно копировать, модифицировать, распространять
- Нужно сохранить текст лицензии и copyright
- Автор не несёт ответственности за работу кода

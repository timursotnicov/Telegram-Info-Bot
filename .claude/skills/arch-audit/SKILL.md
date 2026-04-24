---
name: arch-audit
description: |
  Multi-perspective architecture audit for SaveBot Telegram bot — finds AI classification issues,
  reliability risks, scalability bottlenecks, and hidden technical debt.
  Use when bot behavior seems off, AI answers are wrong, or you suspect hidden problems.
  Triggers on "audit architecture", "find problems", "what's wrong with the bot", "why is AI bad".
  Do NOT use for fixing issues (use arch-solver) or researching solutions (use deep-research).
user_invocable: true
invocation: /arch-audit
---

# Arch Audit — SaveBot Architecture Scanner

Scan SaveBot from 5 perspectives to find problems you don't know about.

## Before You Start

Read these files first:
1. `ARCHITECTURE.md` — system design, DB schema, router order
2. `savebot/bot.py` — entry point, router registration
3. `savebot/config.py` — env vars, AI model config
4. `CLAUDE.md` — project rules and gotchas

## The 5 Perspectives

For each finding: **file:line**, **impact (HIGH/MED/LOW)**, **effort to fix**, **concrete evidence**.

### Perspective 1: AI Quality

Where does AI classification/search lose quality?

- Trace a saved message through ai_classifier.py. What happens with ambiguous content?
- Does the fallback chain (gemma → trinity → gemma-12b → qwen3) degrade quality?
- Are AI prompts optimized? Are few-shot examples relevant to real user content?
- Test /ask with edge cases: empty DB, single item, very long query
- Does ai_search.py synthesize answers correctly? Do source buttons point to right items?
- Is system prompt merged into user message correctly for all models?
- Quick capture (! prefix) bypasses AI — items saved without category/tags. Is that tracked?

### Perspective 2: Data Integrity

Where can data be lost or corrupted?

- SQLite with aiosqlite — what happens during concurrent writes?
- Are migrations idempotent? What if migration 8 runs twice?
- FTS5 index (items_fts) — is it kept in sync with items table?
- Callback data truncation (20 chars for tags) — can this cause duplicate or wrong tag matching?
- Collection items — is there orphan cleanup when items are deleted?
- State store (pending_states) — what happens with expired states?
- Daily backup cron — is it actually running? When was last backup?

### Perspective 3: Scalability

What breaks with 10x more users or 100x more items?

- SQLite single-file DB — concurrent access bottleneck?
- queries.py has ~70 functions — are queries using indexes?
- Browse handler (1445 lines) — does pagination work for 10K+ items?
- FTS search — performance with 100K+ items?
- Scheduler runs hourly — what if digest generation takes >1 hour?
- OpenRouter rate limits — are 429 errors handled across all services?
- Inline query — does it timeout with large result sets?

### Perspective 4: Reliability

What are the single points of failure?

- OpenRouter API down → all AI features broken. Is there a graceful fallback?
- Server (Oracle Cloud single VM) — no redundancy. Recovery plan?
- Bot polling mode — what happens after TelegramConflictError?
- Scheduler — does it recover after crash? Are jobs idempotent?
- Error middleware — does it catch all exceptions? Does it notify the user?
- Link preview (link_preview.py) — timeouts on slow URLs?
- OCR service (Gemini Flash) — separate API, separate failure mode

### Perspective 5: Hidden Debt

Anti-patterns and forgotten code.

- Dead code: unused handlers, unreachable callbacks, orphaned query functions?
- Config values that should be tunable but are hardcoded (timeouts, limits, batch sizes)?
- Implicit assumptions (e.g., "single user bot" but allowed_users supports multiple)?
- Missing tests for critical paths (save flow, delete cascade, AI fallback)?
- Security: user_id validation in every handler? Can user A see user B's items?
- TODO/FIXME/HACK comments in code?
- Callback data convention violations (>64 bytes, wrong prefix)?
- State management — are all states cleaned up properly?

## Output Format

```
═══ ARCH AUDIT ═════════════════════════════════
Project: SaveBot | Files scanned: N
═════════════════════════════════════════════════

## Perspective 1: AI Quality
[HIGH] ai_classifier.py:45 — Fallback model "trinity" returns different
       JSON format than gemma, causing parse errors in 30% of fallback cases.
       → Suggest: normalize response parsing across all models

[MED]  ai_search.py:120 — /ask synthesis prompt hardcodes max 5 items
       but user may have 100+ relevant items. Quality degrades.
       → Suggest: pre-rank items by relevance before sending to AI

...

═══ SUMMARY ═════════════════════════════════════
HIGH findings: N (action required)
MED findings:  N (should fix)
LOW findings:  N (nice to have)
═════════════════════════════════════════════════
```

## Persistence

After completing the audit, save to `.claude/skills/arch-audit/data/audits.jsonl`:
```json
{"timestamp": "2026-03-19", "project": "savebot", "findings_high": 3, "findings_med": 5, "findings_low": 2, "top_finding": "AI fallback chain format mismatch"}
```

Read previous audits first — note which findings are NEW vs RECURRING.

## Gotchas

- Don't just list theoretical problems. Every finding must have a **file:line** reference
- "Could be better" is not a finding. "X causes Y failure when Z" IS a finding
- Don't audit what works. If a query function has tests and passes — skip it
- Unknown unknowns (Perspective 5) are the most valuable. Spend extra time there
- Remember: bot runs on server, NEVER test locally (polling conflicts)
- Read the .conventions/ gold standards to check for convention violations

# 003: Callback Data 64-Byte Limit

- **Date:** 2026-03
- **Status:** Accepted

## Context

Telegram enforces a hard 64-byte limit on `callback_data`. Exceeding it causes `TelegramBadRequest` crashes at runtime with no warning at build time.

## Decision

- Use short prefixes (2-3 chars + colon): `vi:`, `va:`, `vl:`, `bm:`, etc.
- Use numeric IDs for categories, items, and collections -- never full names.
- Truncate tag names to 20 characters via `_truncate_tag()`.
- For complex flows needing more context, use the state store instead of cramming data into callbacks.

## Consequences

- Every new callback pattern must be checked against the 64-byte limit.
- Tag-based callbacks may collide if two tags share the same 20-char prefix (acceptable risk, very rare).
- Full callback conventions are documented in `.conventions/gold-standards/callback-pattern.md`.

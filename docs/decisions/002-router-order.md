# 002: Router Registration Order

- **Date:** 2026-03
- **Status:** Accepted

## Context

aiogram 3.x processes handlers in the order routers are registered. Some handlers overlap (e.g., free-text messages match both state dispatcher and save catch-all). Wrong order causes messages to be swallowed by the wrong handler.

## Decision

Router registration order in `bot.py`: **settings -> manage -> menu -> browse -> inline -> save**.

- `menu` must come before `browse` because the state dispatcher in menu catches pending text inputs.
- `save` must be last because it is the catch-all for unmatched messages (auto-save flow).

## Consequences

- New routers must be inserted at the correct position, never appended blindly.
- Adding a new handler that matches free text requires checking it does not conflict with state dispatcher or save catch-all.

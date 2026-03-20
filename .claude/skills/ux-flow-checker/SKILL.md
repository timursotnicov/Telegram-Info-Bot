---
name: ux-flow-checker
description: |
  Static analysis of handler code to build a navigation map — which buttons lead where,
  how many clicks to reach any item, detect dead ends without back buttons.
  Use when checking UX flows, building navigation map, finding dead ends, counting clicks.
  Triggers on "check UX", "navigation map", "dead ends", "how many clicks", "unreachable screens".
  Do NOT use for code refactoring (use browse-refactor), AI prompt tuning (use ai-classify-debug),
  or full audits (use bot-audit).
user_invocable: true
invocation: /ux-flow-checker
---

# UX Flow Checker — Navigation Map Builder

Static analysis of Telegram bot handlers → navigation graph → UX warnings.

## Before You Start

Read these files to understand context:
1. `savebot/handlers/browse.py` — main navigation (1445 lines)
2. `savebot/handlers/menu.py` — state_dispatcher, keyboard buttons
3. `.conventions/gold-standards/callback-pattern.md` — callback prefix conventions

## Run the Script

```bash
python .claude/skills/ux-flow-checker/scripts/ux_flow_graph.py savebot/handlers/
```

Output goes to `.claude/skills/ux-flow-checker/data/`:
- `flow_graph.json` — full navigation graph (nodes + edges)
- `flow_warnings.json` — dead ends, orphans, deep paths

## Analyze Results

### Warning Types

| Severity | Type | Meaning |
|----------|------|---------|
| HIGH | Dead end | Handler has no outgoing edges and no back button |
| MED | Deep path | More than 4 clicks from root to reach this screen |
| LOW | Orphan | No incoming edges — unreachable from any button |

### What to Do

- **Dead ends:** Add a back button or navigation link
- **Deep paths:** Add shortcut from a higher-level screen
- **Orphans:** Either add a button that leads here, or remove the handler

## Interpreting the Graph

Each node has:
- `id` — callback prefix (e.g., "vi:", "bm:cats")
- `handler` — file:line where it's registered
- `type` — "callback", "command", or "keyboard_button"

Each edge has:
- `from` — handler that generates this callback_data
- `to` — callback prefix it generates
- `button_text` — text on the button (if extractable)

## Gotchas

- `_extract_list_context` borrows navigation context from the current keyboard, not from callback_data. The script marks these handlers but can't fully trace their "back" paths.
- State-based flows (edit_tags, rename_cat, new_collection) are invisible to callback parsing — they go through `state_dispatcher` in menu.py.
- Dynamic callbacks with variables (f-strings) are parsed by prefix only — everything before the first `{`.
- Some handlers have multiple decorators (both `F.data == "bm:colls"` and `Command("collections")`) — the script creates separate nodes for each entry point.

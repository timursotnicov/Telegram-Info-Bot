---
name: bot-audit
description: |
  Full bot audit -- launches UX flow analysis, AI classification bench, and code health check
  in parallel, then compiles a unified report with prioritized findings.
  Use when you want a complete health check, need to find what to fix next, or before a major release.
  Triggers on "full audit", "check everything", "what needs fixing", "bot health check", "bot-audit".
  Do NOT use for a single focused check (use ux-flow-checker, ai-classify-debug, or browse-refactor),
  deployment (use deploy-savebot), or adding features (use new-handler).
user_invocable: true
invocation: /bot-audit
---

# Bot Audit -- Full SaveBot Health Check

Launches 3 specialized agents in parallel, each self-verifies before reporting, then compiles a unified report.

## Before You Start

1. Read `CLAUDE.md` for project context
2. Check if OPENROUTER_API_KEY is set (needed for AI agent; if missing, AI agent skips live tests)

## Run the Audit

Launch **3 Agent tool calls in a single message** (parallel):

### Agent 1: UX Flow Analysis

Prompt for UX agent:
```
Run the UX flow analysis script and analyze results.

1. Run: python .claude/skills/ux-flow-checker/scripts/ux_flow_graph.py savebot/handlers/
2. Read .claude/skills/ux-flow-checker/data/flow_warnings.json
3. For each warning, verify it's a real issue (not a false positive from shared helper functions like _show_list, _show_item_view)
4. Return ONLY verified findings as JSON array:
   [{"severity": "HIGH|MED|LOW", "file": "...", "line": N, "description": "...", "suggestion": "..."}]

Self-check before returning:
- Every finding has file:line
- No theoretical findings without evidence
- Filter out false positives from _show_list/_show_item_view (these generate buttons dynamically)
```

### Agent 2: AI Classification Quality

Prompt for AI agent:
```
Check AI classification quality.

1. Check if OPENROUTER_API_KEY is set in environment
2. If YES: run python .claude/skills/ai-classify-debug/scripts/classify_bench.py
   Read .claude/skills/ai-classify-debug/data/bench_results.jsonl for results
3. If NO: analyze savebot/services/ai_classifier.py SYSTEM_PROMPT for structural issues
   (missing examples, ambiguous rules, potential model compatibility problems)
4. Also check savebot/services/ai_search.py for similar prompt issues
5. Return findings as JSON array:
   [{"severity": "HIGH|MED|LOW", "file": "...", "line": N, "description": "...", "suggestion": "..."}]

Self-check before returning:
- Every finding has file:line
- Accuracy stats included if bench was run
```

### Agent 3: Code Health

Prompt for Code agent:
```
Analyze code health of the SaveBot handlers.

1. Run: python .claude/skills/browse-refactor/scripts/browse_analyzer.py savebot/handlers/browse.py
2. Read .claude/skills/browse-refactor/data/browse_sections.json for section sizes
3. Scan all handler files for:
   - Functions longer than 80 lines
   - TODO/FIXME/HACK comments
   - Callback data patterns that could exceed 64 bytes
4. Return findings as JSON array:
   [{"severity": "HIGH|MED|LOW", "file": "...", "line": N, "description": "...", "suggestion": "..."}]

Self-check before returning:
- Every finding has file:line
- Severity justified (HIGH = breaks functionality, MED = degrades UX, LOW = code smell)
```

## After All Agents Return

1. **Collect** all findings from 3 agents
2. **Deduplicate** by file:line (keep higher severity if duplicated)
3. **Sort** by severity: HIGH first, then MED, then LOW
4. **Format** the unified report (see template below)
5. **Save** summary to `data/audits.jsonl`
6. **Compare** with previous audits if history exists

## Report Template

```
==================================================
  BOT AUDIT REPORT -- SaveBot
  Date: YYYY-MM-DD | Agents: N/3 completed
==================================================

## UX Issues (from ux-flow-checker)
[HIGH] browse.py:1202 -- description
       -> Fix: suggestion

## AI Quality (from ai-classify-debug)
[MED]  ai_classifier.py:45 -- description
       -> Fix: suggestion

## Code Health (from browse-refactor)
[HIGH] browse.py -- 1445 lines, largest handler
       -> Fix: split into 5 modules

==================================================
  SUMMARY: HIGH=N MED=N LOW=N
  Top priority: most critical finding
==================================================
```

## If an Agent Fails

- Note which agent was skipped and why
- Compile report from remaining agents
- Never block the full audit because one agent failed

## Persistence

After each audit, append to `data/audits.jsonl`:
```json
{"timestamp": "ISO", "ux_findings": N, "ai_findings": N, "code_findings": N, "high": N, "med": N, "low": N}
```

Compare with previous entries to show trends (new vs recurring findings).

## Gotchas

- Never run the bot locally during audit -- all analysis is static (code reading, script execution)
- UX flow script has false positives for handlers that use shared helper functions (_show_list, _show_item_view) -- filter these out
- AI bench requires OPENROUTER_API_KEY -- skip live tests if missing, analyze prompt structure instead
- browse_analyzer creates data/ dir automatically if missing
- All scripts use ASCII output (Windows cp1252 compatible)

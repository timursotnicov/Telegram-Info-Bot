---
name: arch-solver
description: |
  Find and solve architectural problems in SaveBot — combines arch-audit findings with
  deep-research to produce actionable solution roadmaps. Use when you have known issues
  and need researched solutions, or want a full audit-to-solution cycle.
  Triggers on "solve problems", "fix the architecture", "find and fix", "improvement plan".
  Do NOT use for just auditing (use arch-audit) or just researching (use deep-research).
user_invocable: true
invocation: /arch-solver
---

# Arch Solver — Audit → Research → Solve for SaveBot

Full cycle: find architectural problems, research solutions, build a roadmap.

## Phase 1: Get Findings

Either:
- **Run fresh audit:** Follow `/arch-audit` methodology — scan from 5 perspectives
- **Use existing audit:** Read the last entry from `.claude/skills/arch-audit/data/audits.jsonl`

Output: prioritized list of HIGH/MED findings.

## Phase 2: Select Top Problems

Pick the **top 3** HIGH-impact findings. For each, define:

```
PROBLEM: [1-sentence description]
EVIDENCE: [file:line, metric, or observed behavior]
IMPACT: [what this costs in reliability/UX/data integrity]
RESEARCH QUESTION: [what to search for]
```

## Phase 3: Research Solutions

For each problem, apply `/deep-research` methodology:

1. Formulate 3-5 search queries from different angles
2. Search and fetch relevant sources
3. Identify 2-3 candidate solutions

For each candidate solution:

```
SOLUTION: [name]
SOURCE: [URL/docs/repo]
HOW IT WORKS: [1-2 sentences]
FEASIBILITY: [can we implement this in SaveBot? what changes needed?]
EXPECTED IMPACT: [reliability +X%, UX improvement, data safety]
EFFORT: [hours/days to implement]
RISK: [what could go wrong]
```

## Phase 4: Multi-Perspective Evaluation

For each top solution, evaluate from 3 positions:

| Perspective | Questions |
|-------------|-----------|
| **Engineer** | Is it technically sound? Does it fit aiogram/aiosqlite? Complexity? |
| **User** | Will the bot feel better to use? Faster? More reliable? |
| **Operations** | Easy to deploy? Does it break the single-server setup? Monitoring? |

Score each: STRONG / ACCEPTABLE / WEAK

Only recommend solutions that are ACCEPTABLE or better on ALL 3 perspectives.

## Phase 5: Build Roadmap

Organize solutions by effort and impact:

```
═══ SOLUTION ROADMAP ═══════════════════════════
Project: SaveBot | Problems: N | Solutions: N
═════════════════════════════════════════════════

## Quick Wins (< 1 day, HIGH impact)
1. [solution] — [problem it solves]
   Files: [list]
   Test: [how to verify]
   Deploy: commit → push → SSH restart

## Medium Efforts (1-3 days)
2. [solution] — [problem it solves]
   Files: [list]
   Test: [how to verify]
   Migration needed: [yes/no]

## Strategic Changes (> 3 days)
3. [solution] — [problem it solves]
   Design needed: [yes/no]
   Dependencies: [what must be done first]

## NOT Recommended (researched but rejected)
- [solution] — rejected because: [reason]

═══ EXPECTED IMPACT ════════════════════════════
Reliability: [current state] → [expected after quick wins]
UX: [current pain points] → [expected improvements]
═════════════════════════════════════════════════
```

## Phase 6: Save

Append to `.claude/skills/arch-solver/data/solutions.jsonl`:
```json
{"timestamp": "2026-03-19", "project": "savebot", "problems_analyzed": 3, "solutions_found": 7, "quick_wins": 2, "top_solution": "add retry with backoff to OpenRouter calls"}
```

## Gotchas

- Don't propose solutions without evidence. "We should use X" needs a source or benchmark
- Quick wins first. Don't plan a 2-week refactor when a config change could help
- One change at a time. Multiple changes = can't attribute improvement
- Remember the deploy flow: code change → tests → commit → push → SSH deploy → verify logs
- All solutions must work with: Python 3.12, aiogram 3.26, aiosqlite, single SQLite file
- Don't propose switching to PostgreSQL or Redis unless the problem truly requires it
- Free OpenRouter models have limitations — don't assume paid API features

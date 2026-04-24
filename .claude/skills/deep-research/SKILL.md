---
name: deep-research
description: |
  Thorough web research on any topic — searches from multiple angles, fetches sources,
  synthesizes findings into a structured report. Use when you need to find solutions,
  compare approaches, or understand a domain deeply.
  Triggers on "research this", "find solutions for", "what approaches exist", "deep research on".
  Do NOT use for code analysis (use arch-audit) or implementing solutions (use writing-plans).
user_invocable: true
invocation: /deep-research
---

# Deep Research — Multi-Angle Investigation

Systematic web research: search → fetch → analyze → synthesize → report.

## Step 1: Define the Question

Clarify exactly what we're researching. Break into sub-questions if needed.

Example: "How to handle OpenRouter rate limits in aiogram bot" →
- Sub-Q1: What are OpenRouter rate limit policies for free models?
- Sub-Q2: How do other aiogram bots handle API rate limiting?
- Sub-Q3: What retry/backoff patterns work best for Telegram bots?

## Step 2: Multi-Angle Search

For each sub-question, formulate 2-3 search queries from different angles:

| Angle | Query Pattern | Example |
|-------|--------------|---------|
| Technical | "[technology] best practices [year]" | "aiogram 3 error handling best practices 2025" |
| Academic | "[problem] research paper [domain]" | "SQLite concurrent access async Python" |
| Practical | "[tool/library] [use case] tutorial" | "aiosqlite connection pooling tutorial" |
| Community | "[problem] solution github/stackoverflow" | "aiogram rate limit handler middleware" |
| Ecosystem | "[framework] plugins/extensions for [problem]" | "aiogram middleware retry backoff" |

Use WebSearch for each query. Collect top 3-5 results per query.

## Step 3: Deep Fetch

For the most promising results (max 10 URLs):
- Use WebFetch to get full content
- Extract key findings, code examples, metrics
- Note: author, date, credibility

Skip: paywalled content, marketing fluff, outdated (>2 years) unless foundational.

## Step 4: Synthesize

Group findings by theme. For each theme:

```
### Theme: [name]

**What:** [1-2 sentence summary]
**Sources:** [list of 2-3 sources with URLs]
**Approach:** [how this solves the problem]
**Pros:** [advantages]
**Cons:** [disadvantages, complexity, cost]
**Relevance to SaveBot:** [HIGH/MEDIUM/LOW] — [why]
```

## Step 5: Report

```
═══ DEEP RESEARCH REPORT ══════════════════════
Topic: [research question]
Date: [date] | Sources: N | Searches: N
═════════════════════════════════════════════════

## Key Findings (top 3)
1. [most impactful finding]
2. [second finding]
3. [third finding]

## Themes
[grouped findings from Step 4]

## Recommended Actions
- [concrete action 1] — effort: [LOW/MED/HIGH]
- [concrete action 2] — effort: [LOW/MED/HIGH]

## Sources
[numbered list of all sources with URLs]

## Research Gaps
[what we couldn't find / needs more investigation]
═════════════════════════════════════════════════
```

## Step 6: Save

Append to `.claude/skills/deep-research/data/research-log.jsonl`:
```json
{"timestamp": "2026-03-19", "topic": "aiogram rate limiting", "sources_count": 12, "themes_count": 4, "top_finding": "exponential backoff with jitter prevents thundering herd"}
```

## Gotchas

- Don't stop at first answer. The THIRD page of results often has the best content
- Beware of AI-generated SEO content — check author credibility
- "State of the art" changes fast — prefer sources from last 12 months
- If 3+ sources agree on something, it's likely reliable. 1 source = flag as unverified
- Search in English first (more results), then add Russian queries if needed
- Save ALL source URLs — you'll need them later for reference
- For aiogram-specific questions, check aiogram GitHub issues and discussions first
- For OpenRouter, check their docs/changelog — free model policies change often

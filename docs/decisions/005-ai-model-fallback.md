# 005: AI Model Fallback Chain

- **Date:** 2026-03
- **Status:** Accepted

## Context

The bot uses free-tier models via OpenRouter. Free models have rate limits and occasional downtime. A single model would make the bot unreliable.

## Decision

Implement a fallback chain. If the primary model fails, try the next one:

1. `gemma-3-27b-it:free` (primary)
2. `google/gemini-2.5-flash-preview` (fast fallback)
3. `gemma-3-12b-it:free` (smaller Gemma)
4. `qwen/qwen3-32b:free` (last resort)

## Consequences

- All models in the chain must work without system role (see ADR-001).
- Adding or removing models requires updating the fallback list in `savebot/services/ai_search.py`.
- Response quality may vary between models; the primary model is preferred for consistency.

# 001: Gemma System Role Workaround

- **Date:** 2026-03
- **Status:** Accepted

## Context

The primary AI model (gemma-3-27b-it via OpenRouter) does not support the `system` role in chat completions. Sending a system message causes errors or is silently ignored.

## Decision

All system prompts are merged into the first `user` message before sending to the API. The system instructions are prepended to the user content as a single combined message.

## Consequences

- Every AI service function must merge system text into user message before calling OpenRouter.
- If switching to a model that supports system role, this merging logic can be removed.
- Prompt formatting must account for both system instructions and user content in one message.

---
name: ai-classify-debug
description: |
  Debug and improve AI classification quality -- runs test cases against OpenRouter API,
  compares expected vs actual categories/tags, iterates on the prompt with regression tracking.
  Use when AI picks wrong category, classification is bad, or you want to improve the AI prompt.
  Triggers on "AI picks wrong category", "classification is bad", "improve AI prompt", "test classifier".
  Do NOT use for search quality (ai_search.py is different), code refactoring (use browse-refactor),
  UX flow issues (use ux-flow-checker), or full audits (use bot-audit).
user_invocable: true
invocation: /ai-classify-debug
---

# AI Classify Debug

## Overview

This skill helps you debug and improve the AI classification prompt in `savebot/services/ai_classifier.py`. It works by running a set of test cases against the OpenRouter API, comparing actual results with expected categories and tags, then helping you iterate on the prompt without breaking existing behavior.

The main tool is `classify_bench.py` -- a standalone script that reads test cases from `data/test_cases.jsonl`, calls the API, and produces a pass/fail report.

## Before You Start

1. Check that `OPENROUTER_API_KEY` is set in your environment or `.env` file:
   ```bash
   echo $OPENROUTER_API_KEY
   ```
   If it is missing, stop and ask the user to provide it.

2. The bench script does NOT import from savebot -- it is fully standalone and only needs `aiohttp`.

## Adding Test Cases

Each line in `data/test_cases.jsonl` is one test case in JSON format:

```json
{"text": "content to classify", "categories": [{"name": "Cat1", "emoji": "E"}], "existing_tags": ["tag1"], "expected_category": "Cat1", "expected_tags": ["t1", "t2"], "note": "why this case matters"}
```

Fields:
- `text` -- the content to classify (what the user would send to the bot)
- `categories` -- list of available categories (same format as `get_all_categories` returns)
- `existing_tags` -- list of existing tags to pass to the prompt
- `expected_category` -- the correct category name
- `expected_tags` -- tags you expect the AI to produce (at least partial overlap counts as pass)
- `note` -- human-readable explanation of why this test case exists

When adding new cases, always include the 7 default categories unless testing custom ones.

## Running the Bench

```bash
# Dry run -- shows test cases without calling the API
python .claude/skills/ai-classify-debug/scripts/classify_bench.py --dry-run

# Full run with default model
python .claude/skills/ai-classify-debug/scripts/classify_bench.py

# Specify a model
python .claude/skills/ai-classify-debug/scripts/classify_bench.py --model google/gemma-3-27b-it:free
```

Output:
- Console table with PASS/FAIL for each case
- Summary line with total pass rate
- Results appended to `data/bench_results.jsonl` (one run per line)

## Iterating on the Prompt

Follow this loop:

1. Identify a failing case (wrong category or missing tags)
2. Make ONE change to `SYSTEM_PROMPT` in `savebot/services/ai_classifier.py`
3. Copy the updated prompt into `classify_bench.py` (it has its own copy for standalone use)
4. Re-run the bench
5. Compare results -- did the failing case pass? Did any passing cases break?
6. If regression, revert and try a different approach
7. Once all cases pass, update both files and commit

Keep changes small. One rule change at a time.

## Gotchas

- **gemma model does NOT support system role** -- the prompt is merged into the user message, not sent as a system message. The bench script does the same thing.
- **Tag normalization** -- hyphens are replaced with underscores (`tag.replace("-", "_")`). The bench script applies this too.
- **Rate limits** -- the script waits 2 seconds between API calls. If you get 429 errors, increase the delay.
- **Windows encoding** -- the script uses only ASCII in print statements to avoid cp1252 encoding errors.

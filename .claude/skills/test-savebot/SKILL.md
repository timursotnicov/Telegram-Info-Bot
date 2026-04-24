---
name: test-savebot
description: |
  Run SaveBot test suite with pytest. Shows results, coverage summary, and failing tests.
  Use when testing code changes. Do NOT use for deployment (use /deploy-savebot).
---

# Test SaveBot

## Steps

### 1. Run full test suite
```bash
cd "C:\Users\Timmy\Claude Projects\Telegram-Info-Bot"
python -m pytest tests/ -v --tb=short 2>&1
```

### 2. Analyze results
- Count passed/failed/skipped
- For any failures: show the test name, file, and error message
- Suggest fix if the failure is obvious

### 3. Report
```
Tests: X passed, Y failed, Z skipped
Coverage: [list test files and what they cover]
```

If all pass: "All tests pass. Safe to deploy."
If any fail: show failures and suggest fixes.

## Test structure
```
tests/
  conftest.py          — in-memory SQLite fixture
  test_queries.py      — DB query functions (largest suite)
  test_state_store.py  — State management
  test_connections.py  — Related items ranking
  test_digest.py       — Digest and daily brief
  test_link_preview.py — URL extraction
  test_ai_classifier.py — AI classification (mocked)
  test_ai_search.py    — AI search (mocked)
```

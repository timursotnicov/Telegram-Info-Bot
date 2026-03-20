"""AI classification benchmark script.

Reads test cases from data/test_cases.jsonl, calls OpenRouter API,
compares expected vs actual categories/tags, outputs results.

Usage:
    python classify_bench.py --dry-run        # print cases, no API calls
    python classify_bench.py                  # run all cases
    python classify_bench.py --model google/gemma-3-27b-it:free
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# The SYSTEM_PROMPT below is copied from savebot/services/ai_classifier.py.
# Keep them in sync when iterating on the prompt.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Pick the BEST matching category from the list below. Respond with ONLY valid JSON, no markdown.

You MUST choose one from this list. Do NOT create new categories.
If nothing fits well, use "Raznoye" (the misc category).

Rules:
1. Tags: 1-3, lowercase, underscores (e.g. "machine_learning"). Match existing tags when possible.
2. Summary: one sentence, same language as content. Capture the KEY idea, not just the topic.
3. Emoji: pick ONE emoji that represents the category topic, not the content mood.
4. URL/link -> categorize by what the link is about.
5. Forwarded message -> categorize by message topic, ignore who sent it.
6. Very short content (< 10 words) -> still categorize by topic. Use tags to add context.

JSON format:
{"category": "Name", "emoji": "X", "tags": ["tag1", "tag2"], "summary": "Short description"}
"""

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-3-27b-it:free"
DELAY_BETWEEN_CALLS = 2  # seconds


def get_data_dir() -> Path:
    """Return the data/ directory next to this script's parent."""
    return Path(__file__).resolve().parent.parent / "data"


def load_test_cases(path: Path) -> list[dict]:
    """Load test cases from a JSONL file."""
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping line {line_num}: {e}")
    return cases


async def call_openrouter(
    text: str,
    categories: list[dict],
    existing_tags: list[str],
    model: str,
    api_key: str,
) -> dict | None:
    """Call OpenRouter API and return parsed classification result."""
    import aiohttp

    categories_str = ", ".join(
        f"{c.get('emoji', '')} {c['name']}" for c in categories
    ) or "No categories yet"

    tags_str = ", ".join(existing_tags[:20]) or "No tags yet"

    user_prompt = (
        f"Content:\n{text[:2000]}\n\n"
        f"Existing categories: {categories_str}\n"
        f"Frequently used tags: {tags_str}"
    )

    # Merge system prompt into user message (gemma has no system role)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"  [ERR] API returned {resp.status}: {body[:200]}")
                    return None
                data = await resp.json()

        raw = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        result = json.loads(raw)
        # Normalize tags (hyphens -> underscores)
        tags = [t.replace("-", "_") for t in result.get("tags", [])[:3]]
        return {
            "category": result.get("category", ""),
            "emoji": result.get("emoji", ""),
            "tags": tags,
            "summary": result.get("summary", ""),
        }
    except Exception as e:
        print(f"  [ERR] {type(e).__name__}: {e}")
        return None


def evaluate_result(expected: dict, actual: dict | None) -> dict:
    """Compare expected vs actual and return evaluation dict."""
    if actual is None:
        return {"cat_match": False, "tag_overlap": 0, "status": "ERROR"}

    cat_match = actual["category"] == expected["expected_category"]

    expected_tags = set(expected.get("expected_tags", []))
    actual_tags = set(actual.get("tags", []))
    tag_overlap = len(expected_tags & actual_tags)

    # Pass if category matches and at least one tag overlaps (or no expected tags)
    tag_ok = tag_overlap > 0 or len(expected_tags) == 0
    status = "PASS" if (cat_match and tag_ok) else "FAIL"

    return {
        "cat_match": cat_match,
        "tag_overlap": tag_overlap,
        "tag_expected": list(expected_tags),
        "tag_actual": list(actual_tags),
        "status": status,
    }


async def run_bench(cases: list[dict], model: str, api_key: str) -> list[dict]:
    """Run all test cases and return results."""
    results = []
    for i, case in enumerate(cases):
        text_preview = case["text"][:60].encode("ascii", "replace").decode()
        print(f"\n[{i+1}/{len(cases)}] {text_preview}...")

        actual = await call_openrouter(
            case["text"],
            case.get("categories", []),
            case.get("existing_tags", []),
            model,
            api_key,
        )

        ev = evaluate_result(case, actual)

        cat_actual = actual["category"] if actual else "N/A"
        cat_expected = case["expected_category"]
        cat_icon = "OK" if ev["cat_match"] else "XX"

        print(f"  Category: {cat_expected} -> {cat_actual} [{cat_icon}]")
        if actual:
            tags_str = ", ".join(actual.get("tags", []))
            print(f"  Tags: [{tags_str}]  overlap={ev['tag_overlap']}")
        print(f"  Result: {ev['status']}")

        results.append({
            "case_index": i,
            "note": case.get("note", ""),
            "expected_category": cat_expected,
            "actual_category": cat_actual,
            "expected_tags": ev.get("tag_expected", []),
            "actual_tags": ev.get("tag_actual", []),
            "cat_match": ev["cat_match"],
            "tag_overlap": ev["tag_overlap"],
            "status": ev["status"],
        })

        # Rate limit delay (skip after last case)
        if i < len(cases) - 1:
            await asyncio.sleep(DELAY_BETWEEN_CALLS)

    return results


def print_summary(results: list[dict], model: str) -> None:
    """Print final summary table."""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    print("\n" + "=" * 60)
    print(f"Model: {model}")
    print(f"Total: {total}  |  PASS: {passed}  |  FAIL: {failed}  |  ERROR: {errors}")
    pct = (passed / total * 100) if total > 0 else 0
    print(f"Pass rate: {pct:.0f}%")
    print("=" * 60)

    if failed > 0 or errors > 0:
        print("\nFailing cases:")
        for r in results:
            if r["status"] != "PASS":
                note = r.get("note", "").encode("ascii", "replace").decode()
                print(f"  [{r['status']}] #{r['case_index']+1}: {note}")
                print(f"         expected={r['expected_category']} actual={r['actual_category']}")


def save_results(results: list[dict], model: str, data_dir: Path) -> None:
    """Append run results to bench_results.jsonl."""
    out_path = data_dir / "bench_results.jsonl"
    run_record = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "results": results,
    }
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(run_record, ensure_ascii=False) + "\n")
    print(f"\nResults saved to {out_path}")


def dry_run(cases: list[dict]) -> None:
    """Print test cases without calling the API."""
    print(f"Loaded {len(cases)} test case(s):\n")
    for i, case in enumerate(cases):
        text_preview = case["text"][:80].encode("ascii", "replace").decode()
        note = case.get("note", "").encode("ascii", "replace").decode()
        cat = case.get("expected_category", "?").encode("ascii", "replace").decode()
        tags = case.get("expected_tags", [])
        tags_ascii = ", ".join(t.encode("ascii", "replace").decode() for t in tags)
        print(f"  #{i+1}: {text_preview}")
        print(f"       -> category={cat}  tags=[{tags_ascii}]")
        print(f"       note: {note}")
        print()


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI classification benchmark")
    parser.add_argument("--dry-run", action="store_true", help="Print cases, no API calls")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model ID")
    args = parser.parse_args()

    data_dir = get_data_dir()
    cases_path = data_dir / "test_cases.jsonl"

    if not cases_path.exists():
        print(f"[ERR] Test cases file not found: {cases_path}")
        sys.exit(1)

    cases = load_test_cases(cases_path)
    if not cases:
        print("[ERR] No test cases loaded")
        sys.exit(1)

    if args.dry_run:
        dry_run(cases)
        return

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        # Try loading from .env in project root
        env_path = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not api_key:
        print("[ERR] OPENROUTER_API_KEY not set. Set it in environment or .env file.")
        sys.exit(1)

    print(f"Running {len(cases)} test case(s) with model={args.model}")
    results = await run_bench(cases, args.model, api_key)
    print_summary(results, args.model)
    save_results(results, args.model, data_dir)


if __name__ == "__main__":
    asyncio.run(main())

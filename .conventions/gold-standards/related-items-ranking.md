# Related Items Ranking Pattern

Multi-tier fallback strategy for finding related content.
Used in `savebot/services/connections.py` → `find_related_items()`.

## Tiers (in priority order)

1. **Shared tags** — items sharing 1+ tags, ranked by shared tag count (most overlap first)
   - Query: `get_items_with_shared_tags()` in queries.py
   - Strongest signal: explicit user-assigned metadata

2. **Same category** — items in the same category, ordered by recency
   - Query: `get_items_in_same_category()` in queries.py
   - Medium signal: AI-assigned grouping

3. **FTS5 similarity** — full-text search by first 3 words of ai_summary
   - Query: `get_similar_items_fts()` in queries.py
   - Weakest signal: content similarity via indexed text

## Rules

- Each tier only runs if previous tiers didn't fill `top_k` results
- `seen_ids` set prevents duplicates across tiers
- The source item is always excluded
- All results are user-isolated (`user_id` in every query)
- Results have tags attached via `_attach_tags()`

## Adding New Tiers

To add a new ranking signal:
1. Add a focused query function in `queries.py` (single responsibility)
2. Add the tier to `connections.py` `find_related_items()` with dedup via `seen_ids`
3. Place it in the correct priority position

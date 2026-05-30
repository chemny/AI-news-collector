# Collection Report · 2026-05-31

Window: 2026-05-30T09:00:00+08:00 to 2026-05-31T09:00:00+08:00

## Summary

| Metric | Count |
|---|---:|
| Fetched | 120 |
| Normalized | 112 |
| In window | 80 |
| New | 52 |
| Duplicate today | 15 |
| Duplicate recent | 13 |
| Quality skipped | 8 |
| Out of window | 32 |
| Skipped | 40 |
| Duration seconds | 45.2 |

## Sources

| Source | Fetched | Normalized | In window | New | Duplicate today | Duplicate recent | Quality skipped | Out of window | Skipped | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| aihot_selected | 50 | 46 | 42 | 24 | 8 | 10 | 4 | 0 | 4 | ok |
| news_aggregator | 70 | 66 | 38 | 28 | 7 | 3 | 4 | 28 | 32 | ok |

## Notes

- Only `status = new` items flow into curation, briefings, and topic mining.
- Duplicate records are kept in SQLite for audit and threshold tuning.

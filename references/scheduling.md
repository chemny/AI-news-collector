# Scheduling

Collection is not a standalone periodic job in the daily self-media workflow.

The collector should run immediately before the workflow that needs fresh material. If the user wants a report at 10:00 or 11:00, the workflow should start by collecting the previous 24 hours at that time.

## Default Trigger

Use this as the first step of the daily-report workflow:

```bash
python3 scripts/collect.py \
  --config examples/sources.yaml \
  --mode daily
```

This run collects:

- AIHOT selected/daily signals
- local `source_registry.yaml` RSS sources through `news_aggregator`
- X builders from `builder_source_profiles.yaml`
- public supplement sources such as HN, GitHub, arXiv, newsletters, and user OPML

## Manual Refresh

Use the same command when the user asks to refresh the source pool manually.

Single-source diagnostics are still allowed:

```bash
python3 scripts/collect.py \
  --config examples/sources.yaml \
  --mode daily \
  --source x_builders
```

Single-source runs are diagnostics. They should not be treated as the daily report workflow.

## When To Use Automation

Create an automation only for the report workflow itself, not for collection alone.

Correct:

```text
10:00 daily-report workflow
  1. collect past 24 hours
  2. topic mining
  3. scoring
  4. draft generation
  5. review/publish
```

Avoid:

```text
09:00 collect
10:00 generate report from stale cache
```

Also avoid hourly or six-hour collector-only jobs unless the user explicitly wants a continuously warmed cache.

## Backfill

Backfill should be explicit:

```bash
python3 scripts/collect.py \
  --config examples/sources.yaml \
  --mode backfill \
  --days 7
```

Backfill must write each day into its own `daily_bucket`. Do not merge seven days into one bucket.

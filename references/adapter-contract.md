# Adapter Contract

Adapters fetch data from third-party sources. They should be simple, deterministic, and safe.

## Interface

Every adapter module should expose:

```python
def fetch(config: dict, window_start: datetime, window_end: datetime) -> list[dict]:
    ...
```

Return a list of dictionaries. Each dictionary can be either:

- already close to source-card fields, or
- raw payload with enough fields for `normalize.py`.

Adapters should not write directly to final SQLite tables.

## Required Raw Fields

Adapters should try to provide:

- `title`
- `url`
- `source_name`
- `published_at`
- `summary` or `content`
- `author`
- `category`
- `tags`
- `heat`

Missing optional fields are acceptable. Missing `title` or `url` usually means the item should be skipped.

## Current Adapters

### follow_builders

Reads public GitHub raw feed files:

- `feed-x.json`
- `feed-podcasts.json`
- `feed-blogs.json`

No user API key is needed when reading the central feed.

### x_builder_monitor

Reads builder X timelines through Nitter RSS using a local builder profile list.

Required config:

- `profiles_path`: YAML or JSON file with `builders`.
- `nitter_instances`: list of Nitter base URLs, such as `https://nitter.net`.

The adapter should provide:

- `author`
- `author_handle`
- `published_at`
- `url`
- `summary` / `content`
- `is_repost`
- `original_handle` when the item is a repost

This adapter is the preferred V1 path for X builder content. It does not provide stable engagement metrics.

### aihot

Calls `https://aihot.virxact.com/api/public/*`.

Always send a browser User-Agent header.

Default collection should use selected items with a 24-hour `since` window.

### news_aggregator

Self-contained V1 collector inspired by `news-aggregator-skill`.

V1 enables a small stable public source set:

- `github`
- `hackernews`
- `ai_newsletters`
- `arxiv`
- `aihot`
- `user`

Avoid fragile private-cookie sources in V1. Do not require users to install the upstream `news-aggregator-skill`.

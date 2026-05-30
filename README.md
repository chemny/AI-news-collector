# AI News Collector

Local-first media source collection skill for AI news, creator workflows, daily briefings, deduplication, and topic candidate generation.

Designed to be portable across Codex, Claude Code, and OpenClaw. The repository root is the skill root; `SKILL.md` lives at the top level.

## What It Does

AI News Collector turns public feeds, external curated signals, and X builder timelines into a local SQLite source pool.

It supports:

- strict past-24-hour collection
- raw payload preservation
- normalized content cards
- same-day and recent-day deduplication
- quality-based primary item selection
- reference source tracking
- AI daily briefing output
- topic candidate generation for creator workflows

## Architecture

The SQLite database is organized as a pipeline:

| Layer | Table | Purpose |
|---|---|---|
| Raw capture | `raw_source_records` | Store external data exactly as captured. |
| Normalized cards | `source_items` | Clean and structure content for downstream use. |
| Deduplication | `item_duplicates` | Record duplicate relationships and evidence. |
| Display cards | `event_clusters` | Keep one primary item and attach duplicate/similar sources as references. |
| Topic pool | `topic_candidates` | Convert information into creator-ready topic ideas. |
| Run audit | `collection_runs` | Track run windows, counts, errors, config hash, and processing versions. |
| Source config | `sources` | Snapshot configured sources. |
| Builder stats | `builder_activity_stats` | Track X builder account posting volume and collection health. |

See [`references/sqlite-schema.md`](references/sqlite-schema.md) for field-level details.

## Installation

Clone or copy this repository into your agent skills directory.

Common locations:

```text
~/.agents/skills/AI-news-collector
~/.codex/skills/AI-news-collector
```

Install the optional Python dependency:

```bash
pip install -r requirements.txt
```

Python 3.11+ is recommended.

## Quick Start

From the repository root:

```bash
python3 scripts/workflow.py --config examples/sources.yaml --mode full
```

This runs:

1. collection
2. normalization
3. deduplication
4. curation
5. briefing generation

Outputs are written under `./data` by default when using `examples/sources.yaml`.

Useful commands:

```bash
python3 scripts/collect.py --config examples/sources.yaml --mode daily
python3 scripts/curate.py --config examples/sources.yaml
python3 scripts/briefing.py --config examples/sources.yaml
python3 scripts/report_builder_activity.py --db ./data/media_sources.sqlite --days 7
```

## Configuration

Start from [`examples/sources.yaml`](examples/sources.yaml).

The example config uses relative paths:

```yaml
project:
  data_dir: ./data
  database_path: ./data/media_sources.sqlite
```

Recommended source roles:

| Source | Role |
|---|---|
| `aihot_selected` | External curated signal. Useful for discovery and coverage checks. |
| `news_aggregator` | Local owned/candidate web and RSS source collector. |
| `x_builders` | X builder monitoring through public RSS/Nitter-style endpoints. |

AIHOT is an external curated signal, not the local source of truth. For controllability, migrate stable sources into `examples/source_registry.yaml` or your own project registry.

## Platform Compatibility

Static compatibility review:

- Codex: supported by standard root-level `SKILL.md`.
- Claude Code: expected to work as a root-level skill directory.
- OpenClaw: expected to work as a self-contained skill directory.

Only Codex-style local execution has been exercised in this repository preparation. Claude Code and OpenClaw should be verified in their own runtimes before claiming tested support.

## Attribution

This skill includes integration ideas and public-source notes inspired by:

- AIHOT-related interfaces, ideas, and selected content references from [KKKKhazix/khazix-skills](https://github.com/KKKKhazix/khazix-skills)
- follow-builders
- news aggregator style feed collection

See `vendor/*/source-notes.md`. Users do not need to install those upstream skills separately.

## Limitations

- X collection depends on public RSS/Nitter-style endpoints and may be unstable.
- Some providers may omit per-item publish times; strict 24-hour filtering may skip those rows.
- Local title/summary generation is conservative and extractive by default.
- No API keys are required by the default example config.

## License

MIT.

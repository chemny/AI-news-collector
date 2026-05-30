# Deduplication Rules

The collector deduplicates twice:

1. Same-day dedupe within the current `daily_bucket`.
2. Recent-day dedupe against the previous N daily buckets, default 2 days.

## Required Time Window

Default daily collection only accepts items from the past 24 hours.

In daily mode, if `published_at` is missing or cannot be parsed, skip the item. The daily briefing contract is strict: 24 hours means 24 hours.

## Canonical URL

Canonicalize URLs before comparing:

- Lowercase scheme and host.
- Remove fragment.
- Remove common tracking parameters:
  - `utm_source`
  - `utm_medium`
  - `utm_campaign`
  - `utm_term`
  - `utm_content`
  - `spm`
  - `from`
  - `ref`
  - `fbclid`
  - `gclid`
- Strip trailing slash except root path.

## Title Normalization

Normalize titles by:

- Lowercasing.
- Converting full-width spaces to normal spaces.
- Removing repeated whitespace.
- Removing common punctuation.
- Removing source suffixes such as ` - Reuters` when clearly added by an aggregator.

## Resolution Flow

Daily dedupe is resolved after all valid current-window items are inserted.

1. Insert all valid current-window items as daily candidates.
2. Reset current-day duplicate statuses so the day can be re-resolved deterministically.
3. Build same-day duplicate groups using canonical URL, content hash, and normalized title similarity >= 0.92.
4. Pick one same-day representative per group using `item_quality_score`.
5. Mark the other same-day group members as `duplicate_today`.
6. Compare current-day winners with the recent-day window.
7. Mark repeated recent-day items as `duplicate_recent` to avoid resurfacing the same event.
8. Otherwise keep the item as `new`.

Same-day duplicate resolution must be quality-based, not insertion-order-based.

`item_quality_score` currently favors:

- primary/first-hand sources
- official sources
- longer and more complete content
- useful summaries
- higher source reliability and source priority
- available engagement metrics
- Chinese-ready fields
- durable sources such as blogs, papers, GitHub repos, and news pages

Short X posts are useful as signals, but should not beat fuller official or media sources only because they were collected earlier.

## Duplicate Records

Always write duplicate relationships to `item_duplicates`.

Do not discard duplicates silently. Keeping duplicate rows helps debug noisy sources and tune dedupe thresholds.

Each duplicate relationship should record the decision evidence:

- `duplicate_type`: `same_day` or `recent_days`.
- `match_method`: `exact` or `fuzzy_title`.
- `matched_field`: `canonical_url`, `content_hash`, or `normalized_title`.
- `dedupe_rule`: stable rule name, such as `same_day_canonical_url` or `recent_days_title_similarity`.
- `similarity_score`: actual score used for the decision.
- `threshold`: threshold required by the rule.
- `window_days`: `0` for same-day rules, otherwise the recent-day lookup window.
- `processing_version`: dedupe rule version.

## Daily Briefing Eligibility

Only items with `status = 'new'` are eligible for topic mining and daily briefing.

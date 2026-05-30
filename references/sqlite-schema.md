# SQLite Schema

SQLite is the source of truth for collected material.

Default path:

```text
media-workflow/data/media_sources.sqlite
```

## Tables

```sql
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  adapter TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  schedule TEXT,
  source_type TEXT,
  platform TEXT,
  provider TEXT,
  role TEXT NOT NULL DEFAULT 'collector',
  priority REAL NOT NULL DEFAULT 1,
  reliability REAL NOT NULL DEFAULT 0.5,
  config_hash TEXT,
  config_json TEXT,
  last_seen_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL,
  source_name TEXT,
  selected_sources_json TEXT NOT NULL DEFAULT '[]',
  timezone TEXT,
  config_hash TEXT,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  daily_bucket TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_seconds REAL,
  status TEXT NOT NULL,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  normalized_count INTEGER NOT NULL DEFAULT 0,
  in_window_count INTEGER NOT NULL DEFAULT 0,
  quality_skipped_count INTEGER NOT NULL DEFAULT 0,
  out_of_window_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  duplicate_today_count INTEGER NOT NULL DEFAULT 0,
  duplicate_recent_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  source_stats_json TEXT NOT NULL DEFAULT '{}',
  processing_versions_json TEXT NOT NULL DEFAULT '{}',
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS source_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_uid TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  title_zh TEXT,
  title_source TEXT NOT NULL DEFAULT 'raw',
  title_quality_flags_json TEXT NOT NULL DEFAULT '[]',
  normalized_title TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  platform TEXT NOT NULL,
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  author TEXT,
  author_handle TEXT,
  published_at TEXT,
  collected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  summary TEXT,
  summary_zh TEXT,
  summary_source TEXT NOT NULL DEFAULT 'raw',
  summary_quality_flags_json TEXT NOT NULL DEFAULT '[]',
  content TEXT,
  category TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  language TEXT NOT NULL DEFAULT 'unknown',
  heat TEXT,
  like_count INTEGER,
  comment_count INTEGER,
  repost_count INTEGER,
  favorite_count INTEGER,
  view_count INTEGER,
  quote_count INTEGER,
  reply_count INTEGER,
  engagement_score REAL NOT NULL DEFAULT 0,
  platform_engagement_percentile REAL,
  engagement_velocity_score REAL NOT NULL DEFAULT 0,
  freshness_score REAL NOT NULL DEFAULT 0,
  collector_rank_score REAL NOT NULL DEFAULT 0,
  engagement_raw_json TEXT NOT NULL DEFAULT '{}',
  source_tags_json TEXT NOT NULL DEFAULT '[]',
  entity_tags_json TEXT NOT NULL DEFAULT '[]',
  topic_tags_json TEXT NOT NULL DEFAULT '[]',
  audience_tags_json TEXT NOT NULL DEFAULT '[]',
  platform_hint_json TEXT NOT NULL DEFAULT '[]',
  tag_confidence_json TEXT NOT NULL DEFAULT '{}',
  source_reliability REAL NOT NULL DEFAULT 0.5,
  source_priority REAL NOT NULL DEFAULT 1,
  author_followers INTEGER,
  author_verified INTEGER,
  author_profile_json TEXT NOT NULL DEFAULT '{}',
  is_official_source INTEGER NOT NULL DEFAULT 0,
  is_primary_source INTEGER NOT NULL DEFAULT 0,
  content_type TEXT,
  media_urls_json TEXT NOT NULL DEFAULT '[]',
  related_urls_json TEXT NOT NULL DEFAULT '[]',
  raw_metrics_at TEXT,
  provider TEXT,
  is_repost INTEGER NOT NULL DEFAULT 0,
  original_author TEXT,
  original_handle TEXT,
  raw_record_uid TEXT,
  raw_source TEXT NOT NULL,
  dedupe_key TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  daily_bucket TEXT NOT NULL,
  status TEXT NOT NULL,
  translation_status TEXT NOT NULL DEFAULT 'not_needed',
  mapping_status TEXT NOT NULL DEFAULT 'ok',
  missing_fields_json TEXT NOT NULL DEFAULT '[]',
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  processing_version TEXT NOT NULL DEFAULT 'source-items-v3',
  ai_processing_model TEXT,
  ai_processing_version TEXT
);

CREATE TABLE IF NOT EXISTS item_duplicates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_uid TEXT NOT NULL,
  duplicate_of_uid TEXT NOT NULL,
  duplicate_type TEXT NOT NULL,
  match_method TEXT NOT NULL DEFAULT 'unknown',
  matched_field TEXT,
  match_value TEXT,
  dedupe_rule TEXT,
  similarity_score REAL,
  threshold REAL,
  window_days INTEGER,
  processing_version TEXT NOT NULL DEFAULT 'dedupe-v2',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS builder_activity_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  daily_bucket TEXT NOT NULL,
  source_name TEXT NOT NULL,
  builder_id TEXT,
  builder_name TEXT,
  handle TEXT NOT NULL,
  company_id TEXT,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  normalized_count INTEGER NOT NULL DEFAULT 0,
  in_window_count INTEGER NOT NULL DEFAULT 0,
  quality_skipped_count INTEGER NOT NULL DEFAULT 0,
  out_of_window_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  duplicate_today_count INTEGER NOT NULL DEFAULT 0,
  duplicate_recent_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  fetch_success_rate REAL,
  in_window_rate REAL,
  duplicate_rate REAL,
  suggested_max_items INTEGER,
  processing_version TEXT NOT NULL DEFAULT 'builder-activity-v2',
  oldest_published_at TEXT,
  newest_published_at TEXT,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_clusters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cluster_uid TEXT NOT NULL UNIQUE,
  daily_bucket TEXT NOT NULL,
  primary_item_uid TEXT,
  title TEXT NOT NULL,
  dimension_id TEXT NOT NULL,
  dimension_label TEXT NOT NULL,
  dimension_icon TEXT,
  summary TEXT,
  why_it_matters TEXT,
  item_uids_json TEXT NOT NULL DEFAULT '[]',
  reference_items_json TEXT NOT NULL DEFAULT '[]',
  source_names_json TEXT NOT NULL DEFAULT '[]',
  source_urls_json TEXT NOT NULL DEFAULT '[]',
  source_count INTEGER NOT NULL DEFAULT 1,
  cross_source_count INTEGER NOT NULL DEFAULT 1,
  cluster_score REAL NOT NULL DEFAULT 0,
  rank INTEGER NOT NULL DEFAULT 0,
  display_mode TEXT NOT NULL DEFAULT 'primary_with_references',
  tags_json TEXT NOT NULL DEFAULT '[]',
  platform_hints_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_uid TEXT NOT NULL UNIQUE,
  cluster_uid TEXT NOT NULL,
  daily_bucket TEXT NOT NULL,
  title TEXT NOT NULL,
  source_title TEXT,
  angle TEXT,
  topic_type TEXT,
  core_question TEXT,
  target_audience_json TEXT NOT NULL DEFAULT '[]',
  dimension_id TEXT NOT NULL,
  topic_score REAL NOT NULL DEFAULT 0,
  score_breakdown_json TEXT NOT NULL DEFAULT '{}',
  platform_fit_json TEXT NOT NULL DEFAULT '{}',
  recommended_platforms_json TEXT NOT NULL DEFAULT '[]',
  source_item_uid TEXT,
  reference_items_json TEXT NOT NULL DEFAULT '[]',
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'candidate',
  processing_version TEXT NOT NULL DEFAULT 'topic-candidates-v2',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_items_bucket_status
  ON source_items(daily_bucket, status);

CREATE INDEX IF NOT EXISTS idx_source_items_canonical_url
  ON source_items(canonical_url);

CREATE INDEX IF NOT EXISTS idx_source_items_dedupe_key
  ON source_items(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_source_items_published_at
  ON source_items(published_at);

CREATE INDEX IF NOT EXISTS idx_source_items_engagement_score
  ON source_items(engagement_score);

CREATE INDEX IF NOT EXISTS idx_source_items_collector_rank_score
  ON source_items(collector_rank_score);

CREATE INDEX IF NOT EXISTS idx_event_clusters_bucket_rank
  ON event_clusters(daily_bucket, rank);

CREATE INDEX IF NOT EXISTS idx_topic_candidates_bucket_score
  ON topic_candidates(daily_bucket, topic_score);

CREATE VIRTUAL TABLE IF NOT EXISTS source_items_fts USING fts5(
  title,
  title_zh,
  summary,
  summary_zh,
  content,
  source_name,
  content='source_items',
  content_rowid='id'
);
```

## FTS Maintenance

When inserting a row into `source_items`, also insert:

```sql
INSERT INTO source_items_fts(rowid, title, title_zh, summary, summary_zh, content, source_name)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

When updating a row, delete then reinsert the FTS row.

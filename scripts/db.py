import sqlite3
from pathlib import Path


SCHEMA = """
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

CREATE TABLE IF NOT EXISTS raw_source_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_uid TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  daily_bucket TEXT NOT NULL,
  collector TEXT NOT NULL,
  adapter TEXT NOT NULL,
  source_name TEXT,
  raw_source_type TEXT,
  raw_platform TEXT,
  raw_source_id TEXT,
  raw_item_id TEXT,
  raw_title TEXT,
  raw_summary TEXT,
  raw_content TEXT,
  raw_url TEXT,
  raw_published_at TEXT,
  raw_updated_at TEXT,
  raw_created_at TEXT,
  raw_collected_window_start TEXT,
  raw_collected_window_end TEXT,
  raw_author TEXT,
  raw_author_handle TEXT,
  raw_author_id TEXT,
  raw_language TEXT,
  raw_category TEXT,
  raw_content_type TEXT,
  raw_tags_json TEXT NOT NULL DEFAULT '[]',
  raw_media_urls_json TEXT NOT NULL DEFAULT '[]',
  raw_related_urls_json TEXT NOT NULL DEFAULT '[]',
  raw_like_count INTEGER,
  raw_comment_count INTEGER,
  raw_repost_count INTEGER,
  raw_favorite_count INTEGER,
  raw_view_count INTEGER,
  raw_quote_count INTEGER,
  raw_reply_count INTEGER,
  raw_share_count INTEGER,
  raw_bookmark_count INTEGER,
  raw_impression_count INTEGER,
  raw_play_count INTEGER,
  raw_download_count INTEGER,
  raw_star_count INTEGER,
  raw_fork_count INTEGER,
  raw_author_followers INTEGER,
  raw_author_verified INTEGER,
  raw_engagement_json TEXT NOT NULL DEFAULT '{}',
  raw_metrics_at TEXT,
  raw_fetch_status TEXT,
  raw_fetch_error TEXT,
  raw_http_status INTEGER,
  raw_provider TEXT,
  raw_provider_url TEXT,
  raw_payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  processing_status TEXT NOT NULL DEFAULT 'raw',
  created_at TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_raw_source_records_bucket_collector
  ON raw_source_records(daily_bucket, collector);

CREATE INDEX IF NOT EXISTS idx_raw_source_records_payload_hash
  ON raw_source_records(payload_hash);

CREATE INDEX IF NOT EXISTS idx_builder_activity_bucket_handle
  ON builder_activity_stats(daily_bucket, handle);

CREATE INDEX IF NOT EXISTS idx_builder_activity_handle_created
  ON builder_activity_stats(handle, created_at);

CREATE INDEX IF NOT EXISTS idx_event_clusters_bucket_rank
  ON event_clusters(daily_bucket, rank);

CREATE INDEX IF NOT EXISTS idx_event_clusters_bucket_dimension
  ON event_clusters(daily_bucket, dimension_id);

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
"""


ITEM_COLUMNS = [
    "item_uid",
    "title",
    "title_zh",
    "title_source",
    "title_quality_flags_json",
    "normalized_title",
    "source_name",
    "source_type",
    "platform",
    "url",
    "canonical_url",
    "author",
    "author_handle",
    "published_at",
    "collected_at",
    "updated_at",
    "summary",
    "summary_zh",
    "summary_source",
    "summary_quality_flags_json",
    "content",
    "category",
    "tags_json",
    "language",
    "heat",
    "like_count",
    "comment_count",
    "repost_count",
    "favorite_count",
    "view_count",
    "quote_count",
    "reply_count",
    "engagement_score",
    "platform_engagement_percentile",
    "engagement_velocity_score",
    "freshness_score",
    "collector_rank_score",
    "engagement_raw_json",
    "source_tags_json",
    "entity_tags_json",
    "topic_tags_json",
    "audience_tags_json",
    "platform_hint_json",
    "tag_confidence_json",
    "source_reliability",
    "source_priority",
    "author_followers",
    "author_verified",
    "author_profile_json",
    "is_official_source",
    "is_primary_source",
    "content_type",
    "media_urls_json",
    "related_urls_json",
    "raw_metrics_at",
    "provider",
    "is_repost",
    "original_author",
    "original_handle",
    "raw_record_uid",
    "raw_source",
    "dedupe_key",
    "content_hash",
    "daily_bucket",
    "status",
    "translation_status",
    "mapping_status",
    "missing_fields_json",
    "quality_flags_json",
    "processing_version",
    "ai_processing_model",
    "ai_processing_version",
]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate_sources(conn)
    migrate_collection_runs(conn)
    migrate_raw_source_records(conn)
    migrate_source_items(conn)
    migrate_item_duplicates(conn)
    migrate_event_clusters(conn)
    migrate_topic_candidates(conn)
    migrate_builder_activity_stats(conn)
    conn.commit()


def migrate_sources(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(sources)").fetchall()
    }
    migrations = {
        "source_type": "ALTER TABLE sources ADD COLUMN source_type TEXT",
        "platform": "ALTER TABLE sources ADD COLUMN platform TEXT",
        "provider": "ALTER TABLE sources ADD COLUMN provider TEXT",
        "role": "ALTER TABLE sources ADD COLUMN role TEXT NOT NULL DEFAULT 'collector'",
        "priority": "ALTER TABLE sources ADD COLUMN priority REAL NOT NULL DEFAULT 1",
        "reliability": "ALTER TABLE sources ADD COLUMN reliability REAL NOT NULL DEFAULT 0.5",
        "config_hash": "ALTER TABLE sources ADD COLUMN config_hash TEXT",
        "last_seen_at": "ALTER TABLE sources ADD COLUMN last_seen_at TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def migrate_collection_runs(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(collection_runs)").fetchall()
    }
    migrations = {
        "selected_sources_json": "ALTER TABLE collection_runs ADD COLUMN selected_sources_json TEXT NOT NULL DEFAULT '[]'",
        "timezone": "ALTER TABLE collection_runs ADD COLUMN timezone TEXT",
        "config_hash": "ALTER TABLE collection_runs ADD COLUMN config_hash TEXT",
        "duration_seconds": "ALTER TABLE collection_runs ADD COLUMN duration_seconds REAL",
        "normalized_count": "ALTER TABLE collection_runs ADD COLUMN normalized_count INTEGER NOT NULL DEFAULT 0",
        "in_window_count": "ALTER TABLE collection_runs ADD COLUMN in_window_count INTEGER NOT NULL DEFAULT 0",
        "quality_skipped_count": "ALTER TABLE collection_runs ADD COLUMN quality_skipped_count INTEGER NOT NULL DEFAULT 0",
        "out_of_window_count": "ALTER TABLE collection_runs ADD COLUMN out_of_window_count INTEGER NOT NULL DEFAULT 0",
        "source_stats_json": "ALTER TABLE collection_runs ADD COLUMN source_stats_json TEXT NOT NULL DEFAULT '{}'",
        "processing_versions_json": "ALTER TABLE collection_runs ADD COLUMN processing_versions_json TEXT NOT NULL DEFAULT '{}'",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def migrate_raw_source_records(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(raw_source_records)").fetchall()
    }
    migrations = {
        "raw_source_type": "ALTER TABLE raw_source_records ADD COLUMN raw_source_type TEXT",
        "raw_platform": "ALTER TABLE raw_source_records ADD COLUMN raw_platform TEXT",
        "raw_source_id": "ALTER TABLE raw_source_records ADD COLUMN raw_source_id TEXT",
        "raw_item_id": "ALTER TABLE raw_source_records ADD COLUMN raw_item_id TEXT",
        "raw_updated_at": "ALTER TABLE raw_source_records ADD COLUMN raw_updated_at TEXT",
        "raw_created_at": "ALTER TABLE raw_source_records ADD COLUMN raw_created_at TEXT",
        "raw_collected_window_start": "ALTER TABLE raw_source_records ADD COLUMN raw_collected_window_start TEXT",
        "raw_collected_window_end": "ALTER TABLE raw_source_records ADD COLUMN raw_collected_window_end TEXT",
        "raw_author_handle": "ALTER TABLE raw_source_records ADD COLUMN raw_author_handle TEXT",
        "raw_author_id": "ALTER TABLE raw_source_records ADD COLUMN raw_author_id TEXT",
        "raw_language": "ALTER TABLE raw_source_records ADD COLUMN raw_language TEXT",
        "raw_category": "ALTER TABLE raw_source_records ADD COLUMN raw_category TEXT",
        "raw_content_type": "ALTER TABLE raw_source_records ADD COLUMN raw_content_type TEXT",
        "raw_tags_json": "ALTER TABLE raw_source_records ADD COLUMN raw_tags_json TEXT NOT NULL DEFAULT '[]'",
        "raw_media_urls_json": "ALTER TABLE raw_source_records ADD COLUMN raw_media_urls_json TEXT NOT NULL DEFAULT '[]'",
        "raw_related_urls_json": "ALTER TABLE raw_source_records ADD COLUMN raw_related_urls_json TEXT NOT NULL DEFAULT '[]'",
        "raw_like_count": "ALTER TABLE raw_source_records ADD COLUMN raw_like_count INTEGER",
        "raw_comment_count": "ALTER TABLE raw_source_records ADD COLUMN raw_comment_count INTEGER",
        "raw_repost_count": "ALTER TABLE raw_source_records ADD COLUMN raw_repost_count INTEGER",
        "raw_favorite_count": "ALTER TABLE raw_source_records ADD COLUMN raw_favorite_count INTEGER",
        "raw_view_count": "ALTER TABLE raw_source_records ADD COLUMN raw_view_count INTEGER",
        "raw_quote_count": "ALTER TABLE raw_source_records ADD COLUMN raw_quote_count INTEGER",
        "raw_reply_count": "ALTER TABLE raw_source_records ADD COLUMN raw_reply_count INTEGER",
        "raw_share_count": "ALTER TABLE raw_source_records ADD COLUMN raw_share_count INTEGER",
        "raw_bookmark_count": "ALTER TABLE raw_source_records ADD COLUMN raw_bookmark_count INTEGER",
        "raw_impression_count": "ALTER TABLE raw_source_records ADD COLUMN raw_impression_count INTEGER",
        "raw_play_count": "ALTER TABLE raw_source_records ADD COLUMN raw_play_count INTEGER",
        "raw_download_count": "ALTER TABLE raw_source_records ADD COLUMN raw_download_count INTEGER",
        "raw_star_count": "ALTER TABLE raw_source_records ADD COLUMN raw_star_count INTEGER",
        "raw_fork_count": "ALTER TABLE raw_source_records ADD COLUMN raw_fork_count INTEGER",
        "raw_author_followers": "ALTER TABLE raw_source_records ADD COLUMN raw_author_followers INTEGER",
        "raw_author_verified": "ALTER TABLE raw_source_records ADD COLUMN raw_author_verified INTEGER",
        "raw_engagement_json": "ALTER TABLE raw_source_records ADD COLUMN raw_engagement_json TEXT NOT NULL DEFAULT '{}'",
        "raw_metrics_at": "ALTER TABLE raw_source_records ADD COLUMN raw_metrics_at TEXT",
        "raw_fetch_status": "ALTER TABLE raw_source_records ADD COLUMN raw_fetch_status TEXT",
        "raw_fetch_error": "ALTER TABLE raw_source_records ADD COLUMN raw_fetch_error TEXT",
        "raw_http_status": "ALTER TABLE raw_source_records ADD COLUMN raw_http_status INTEGER",
        "raw_provider": "ALTER TABLE raw_source_records ADD COLUMN raw_provider TEXT",
        "raw_provider_url": "ALTER TABLE raw_source_records ADD COLUMN raw_provider_url TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def migrate_source_items(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(source_items)").fetchall()
    }
    migrations = {
        "like_count": "ALTER TABLE source_items ADD COLUMN like_count INTEGER",
        "comment_count": "ALTER TABLE source_items ADD COLUMN comment_count INTEGER",
        "repost_count": "ALTER TABLE source_items ADD COLUMN repost_count INTEGER",
        "favorite_count": "ALTER TABLE source_items ADD COLUMN favorite_count INTEGER",
        "view_count": "ALTER TABLE source_items ADD COLUMN view_count INTEGER",
        "quote_count": "ALTER TABLE source_items ADD COLUMN quote_count INTEGER",
        "reply_count": "ALTER TABLE source_items ADD COLUMN reply_count INTEGER",
        "engagement_score": "ALTER TABLE source_items ADD COLUMN engagement_score REAL NOT NULL DEFAULT 0",
        "platform_engagement_percentile": "ALTER TABLE source_items ADD COLUMN platform_engagement_percentile REAL",
        "engagement_velocity_score": "ALTER TABLE source_items ADD COLUMN engagement_velocity_score REAL NOT NULL DEFAULT 0",
        "freshness_score": "ALTER TABLE source_items ADD COLUMN freshness_score REAL NOT NULL DEFAULT 0",
        "collector_rank_score": "ALTER TABLE source_items ADD COLUMN collector_rank_score REAL NOT NULL DEFAULT 0",
        "engagement_raw_json": "ALTER TABLE source_items ADD COLUMN engagement_raw_json TEXT NOT NULL DEFAULT '{}'",
        "source_tags_json": "ALTER TABLE source_items ADD COLUMN source_tags_json TEXT NOT NULL DEFAULT '[]'",
        "entity_tags_json": "ALTER TABLE source_items ADD COLUMN entity_tags_json TEXT NOT NULL DEFAULT '[]'",
        "topic_tags_json": "ALTER TABLE source_items ADD COLUMN topic_tags_json TEXT NOT NULL DEFAULT '[]'",
        "audience_tags_json": "ALTER TABLE source_items ADD COLUMN audience_tags_json TEXT NOT NULL DEFAULT '[]'",
        "platform_hint_json": "ALTER TABLE source_items ADD COLUMN platform_hint_json TEXT NOT NULL DEFAULT '[]'",
        "tag_confidence_json": "ALTER TABLE source_items ADD COLUMN tag_confidence_json TEXT NOT NULL DEFAULT '{}'",
        "source_reliability": "ALTER TABLE source_items ADD COLUMN source_reliability REAL NOT NULL DEFAULT 0.5",
        "source_priority": "ALTER TABLE source_items ADD COLUMN source_priority REAL NOT NULL DEFAULT 1",
        "author_followers": "ALTER TABLE source_items ADD COLUMN author_followers INTEGER",
        "author_verified": "ALTER TABLE source_items ADD COLUMN author_verified INTEGER",
        "author_profile_json": "ALTER TABLE source_items ADD COLUMN author_profile_json TEXT NOT NULL DEFAULT '{}'",
        "is_official_source": "ALTER TABLE source_items ADD COLUMN is_official_source INTEGER NOT NULL DEFAULT 0",
        "is_primary_source": "ALTER TABLE source_items ADD COLUMN is_primary_source INTEGER NOT NULL DEFAULT 0",
        "content_type": "ALTER TABLE source_items ADD COLUMN content_type TEXT",
        "media_urls_json": "ALTER TABLE source_items ADD COLUMN media_urls_json TEXT NOT NULL DEFAULT '[]'",
        "related_urls_json": "ALTER TABLE source_items ADD COLUMN related_urls_json TEXT NOT NULL DEFAULT '[]'",
        "raw_metrics_at": "ALTER TABLE source_items ADD COLUMN raw_metrics_at TEXT",
        "author_handle": "ALTER TABLE source_items ADD COLUMN author_handle TEXT",
        "provider": "ALTER TABLE source_items ADD COLUMN provider TEXT",
        "is_repost": "ALTER TABLE source_items ADD COLUMN is_repost INTEGER NOT NULL DEFAULT 0",
        "original_author": "ALTER TABLE source_items ADD COLUMN original_author TEXT",
        "original_handle": "ALTER TABLE source_items ADD COLUMN original_handle TEXT",
        "raw_record_uid": "ALTER TABLE source_items ADD COLUMN raw_record_uid TEXT",
        "title_source": "ALTER TABLE source_items ADD COLUMN title_source TEXT NOT NULL DEFAULT 'raw'",
        "title_quality_flags_json": "ALTER TABLE source_items ADD COLUMN title_quality_flags_json TEXT NOT NULL DEFAULT '[]'",
        "summary_source": "ALTER TABLE source_items ADD COLUMN summary_source TEXT NOT NULL DEFAULT 'raw'",
        "summary_quality_flags_json": "ALTER TABLE source_items ADD COLUMN summary_quality_flags_json TEXT NOT NULL DEFAULT '[]'",
        "mapping_status": "ALTER TABLE source_items ADD COLUMN mapping_status TEXT NOT NULL DEFAULT 'ok'",
        "missing_fields_json": "ALTER TABLE source_items ADD COLUMN missing_fields_json TEXT NOT NULL DEFAULT '[]'",
        "quality_flags_json": "ALTER TABLE source_items ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '[]'",
        "processing_version": "ALTER TABLE source_items ADD COLUMN processing_version TEXT NOT NULL DEFAULT 'source-items-v3'",
        "ai_processing_model": "ALTER TABLE source_items ADD COLUMN ai_processing_model TEXT",
        "ai_processing_version": "ALTER TABLE source_items ADD COLUMN ai_processing_version TEXT",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    obsolete_columns = {
        "raw_payload_json",
        "why_it_matters",
        "risk_notes_json",
        "target_platforms_json",
    }
    if obsolete_columns & existing:
        rebuild_source_items_without_obsolete_columns(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_bucket_status ON source_items(daily_bucket, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_canonical_url ON source_items(canonical_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_dedupe_key ON source_items(dedupe_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_published_at ON source_items(published_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_engagement_score ON source_items(engagement_score)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_collector_rank_score ON source_items(collector_rank_score)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_items_raw_record_uid ON source_items(raw_record_uid)"
    )


def rebuild_source_items_without_obsolete_columns(conn: sqlite3.Connection) -> None:
    """Rebuild source_items when older DBs still carry raw/editorial fields."""
    current_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(source_items)").fetchall()
    ]
    copy_columns = [column for column in ITEM_COLUMNS if column in current_columns]
    conn.execute("DROP TABLE IF EXISTS source_items_fts")
    conn.execute("ALTER TABLE source_items RENAME TO source_items_legacy")
    conn.executescript(
        """
        CREATE TABLE source_items (
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
        """
    )
    select_columns = ", ".join(copy_columns)
    conn.execute(
        f"""
        INSERT OR IGNORE INTO source_items ({select_columns})
        SELECT {select_columns}
        FROM source_items_legacy
        """
    )
    conn.execute("DROP TABLE source_items_legacy")
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS source_items_fts USING fts5(
          title,
          title_zh,
          summary,
          summary_zh,
          content,
          source_name,
          content='source_items',
          content_rowid='id'
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO source_items_fts(rowid, title, title_zh, summary, summary_zh, content, source_name)
        SELECT id, COALESCE(title, ''), COALESCE(title_zh, ''), COALESCE(summary, ''),
               COALESCE(summary_zh, ''), COALESCE(content, ''), COALESCE(source_name, '')
        FROM source_items
        """
    )


def migrate_item_duplicates(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(item_duplicates)").fetchall()
    }
    migrations = {
        "match_method": "ALTER TABLE item_duplicates ADD COLUMN match_method TEXT NOT NULL DEFAULT 'unknown'",
        "matched_field": "ALTER TABLE item_duplicates ADD COLUMN matched_field TEXT",
        "match_value": "ALTER TABLE item_duplicates ADD COLUMN match_value TEXT",
        "dedupe_rule": "ALTER TABLE item_duplicates ADD COLUMN dedupe_rule TEXT",
        "threshold": "ALTER TABLE item_duplicates ADD COLUMN threshold REAL",
        "window_days": "ALTER TABLE item_duplicates ADD COLUMN window_days INTEGER",
        "processing_version": "ALTER TABLE item_duplicates ADD COLUMN processing_version TEXT NOT NULL DEFAULT 'dedupe-v2'",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)
    conn.execute(
        """
        DELETE FROM item_duplicates
        WHERE rowid NOT IN (
          SELECT MIN(rowid)
          FROM item_duplicates
          GROUP BY item_uid, duplicate_of_uid, duplicate_type
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_item_duplicates_unique_relation
        ON item_duplicates(item_uid, duplicate_of_uid, duplicate_type)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_item_duplicates_duplicate_of
        ON item_duplicates(duplicate_of_uid, duplicate_type)
        """
    )


def migrate_event_clusters(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(event_clusters)").fetchall()
    }
    migrations = {
        "primary_item_uid": "ALTER TABLE event_clusters ADD COLUMN primary_item_uid TEXT",
        "reference_items_json": "ALTER TABLE event_clusters ADD COLUMN reference_items_json TEXT NOT NULL DEFAULT '[]'",
        "display_mode": "ALTER TABLE event_clusters ADD COLUMN display_mode TEXT NOT NULL DEFAULT 'primary_with_references'",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def migrate_topic_candidates(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(topic_candidates)").fetchall()
    }
    migrations = {
        "source_title": "ALTER TABLE topic_candidates ADD COLUMN source_title TEXT",
        "topic_type": "ALTER TABLE topic_candidates ADD COLUMN topic_type TEXT",
        "core_question": "ALTER TABLE topic_candidates ADD COLUMN core_question TEXT",
        "target_audience_json": "ALTER TABLE topic_candidates ADD COLUMN target_audience_json TEXT NOT NULL DEFAULT '[]'",
        "score_breakdown_json": "ALTER TABLE topic_candidates ADD COLUMN score_breakdown_json TEXT NOT NULL DEFAULT '{}'",
        "recommended_platforms_json": "ALTER TABLE topic_candidates ADD COLUMN recommended_platforms_json TEXT NOT NULL DEFAULT '[]'",
        "source_item_uid": "ALTER TABLE topic_candidates ADD COLUMN source_item_uid TEXT",
        "reference_items_json": "ALTER TABLE topic_candidates ADD COLUMN reference_items_json TEXT NOT NULL DEFAULT '[]'",
        "processing_version": "ALTER TABLE topic_candidates ADD COLUMN processing_version TEXT NOT NULL DEFAULT 'topic-candidates-v2'",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def migrate_builder_activity_stats(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(builder_activity_stats)").fetchall()
    }
    migrations = {
        "fetch_success_rate": "ALTER TABLE builder_activity_stats ADD COLUMN fetch_success_rate REAL",
        "in_window_rate": "ALTER TABLE builder_activity_stats ADD COLUMN in_window_rate REAL",
        "duplicate_rate": "ALTER TABLE builder_activity_stats ADD COLUMN duplicate_rate REAL",
        "suggested_max_items": "ALTER TABLE builder_activity_stats ADD COLUMN suggested_max_items INTEGER",
        "processing_version": "ALTER TABLE builder_activity_stats ADD COLUMN processing_version TEXT NOT NULL DEFAULT 'builder-activity-v2'",
    }
    for column, statement in migrations.items():
        if column not in existing:
            conn.execute(statement)


def insert_raw_record(conn: sqlite3.Connection, record: dict) -> str:
    columns = [
        "raw_uid",
        "run_id",
        "daily_bucket",
        "collector",
        "adapter",
        "source_name",
        "raw_source_type",
        "raw_platform",
        "raw_source_id",
        "raw_item_id",
        "raw_title",
        "raw_summary",
        "raw_content",
        "raw_url",
        "raw_published_at",
        "raw_updated_at",
        "raw_created_at",
        "raw_collected_window_start",
        "raw_collected_window_end",
        "raw_author",
        "raw_author_handle",
        "raw_author_id",
        "raw_language",
        "raw_category",
        "raw_content_type",
        "raw_tags_json",
        "raw_media_urls_json",
        "raw_related_urls_json",
        "raw_like_count",
        "raw_comment_count",
        "raw_repost_count",
        "raw_favorite_count",
        "raw_view_count",
        "raw_quote_count",
        "raw_reply_count",
        "raw_share_count",
        "raw_bookmark_count",
        "raw_impression_count",
        "raw_play_count",
        "raw_download_count",
        "raw_star_count",
        "raw_fork_count",
        "raw_author_followers",
        "raw_author_verified",
        "raw_engagement_json",
        "raw_metrics_at",
        "raw_fetch_status",
        "raw_fetch_error",
        "raw_http_status",
        "raw_provider",
        "raw_provider_url",
        "raw_payload_json",
        "payload_hash",
        "fetched_at",
        "processing_status",
        "created_at",
    ]
    placeholders = ", ".join("?" for _ in columns)
    values = [record.get(column) for column in columns]
    conn.execute(
        f"INSERT OR IGNORE INTO raw_source_records ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    return record["raw_uid"]


def insert_item(conn: sqlite3.Connection, item: dict) -> None:
    placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
    columns = ", ".join(ITEM_COLUMNS)
    values = [item.get(column) for column in ITEM_COLUMNS]
    conn.execute(
        f"INSERT OR IGNORE INTO source_items ({columns}) VALUES ({placeholders})",
        values,
    )
    row = conn.execute(
        "SELECT id FROM source_items WHERE item_uid = ?", (item["item_uid"],)
    ).fetchone()
    if row:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_items_fts(rowid, title, title_zh, summary, summary_zh, content, source_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                item.get("title") or "",
                item.get("title_zh") or "",
                item.get("summary") or "",
                item.get("summary_zh") or "",
                item.get("content") or "",
                item.get("source_name") or "",
            ),
        )


def insert_duplicate(conn: sqlite3.Connection, item: dict, duplicate: dict) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO item_duplicates(
          item_uid, duplicate_of_uid, duplicate_type, match_method, matched_field,
          match_value, dedupe_rule, similarity_score, threshold, window_days,
          processing_version, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["item_uid"],
            duplicate["duplicate_of_uid"],
            duplicate["duplicate_type"],
            duplicate.get("match_method", "unknown"),
            duplicate.get("matched_field"),
            duplicate.get("match_value"),
            duplicate.get("dedupe_rule"),
            duplicate.get("similarity_score"),
            duplicate.get("threshold"),
            duplicate.get("window_days"),
            duplicate.get("processing_version", "dedupe-v2"),
            item["collected_at"],
        ),
    )


def insert_builder_activity_stats(conn: sqlite3.Connection, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO builder_activity_stats(
          run_id, daily_bucket, source_name, builder_id, builder_name, handle,
          company_id, fetched_count, normalized_count, in_window_count,
          quality_skipped_count, out_of_window_count, new_count,
          duplicate_today_count, duplicate_recent_count, skipped_count,
          fetch_success_rate, in_window_rate, duplicate_rate, suggested_max_items,
          processing_version,
          oldest_published_at, newest_published_at, window_start, window_end,
          created_at
        )
        VALUES (
          :run_id, :daily_bucket, :source_name, :builder_id, :builder_name, :handle,
          :company_id, :fetched_count, :normalized_count, :in_window_count,
          :quality_skipped_count, :out_of_window_count, :new_count,
          :duplicate_today_count, :duplicate_recent_count, :skipped_count,
          :fetch_success_rate, :in_window_rate, :duplicate_rate, :suggested_max_items,
          :processing_version,
          :oldest_published_at, :newest_published_at, :window_start, :window_end,
          :created_at
        )
        """,
        rows,
    )


def replace_event_clusters(conn: sqlite3.Connection, daily_bucket: str, clusters: list[dict]) -> None:
    conn.execute("DELETE FROM topic_candidates WHERE daily_bucket = ?", (daily_bucket,))
    conn.execute("DELETE FROM event_clusters WHERE daily_bucket = ?", (daily_bucket,))
    if not clusters:
        return
    conn.executemany(
        """
        INSERT INTO event_clusters(
          cluster_uid, daily_bucket, primary_item_uid, title, dimension_id, dimension_label,
          dimension_icon, summary, why_it_matters, item_uids_json,
          reference_items_json, source_names_json, source_urls_json, source_count, cross_source_count,
          cluster_score, rank, display_mode, tags_json, platform_hints_json, created_at, updated_at
        )
        VALUES (
          :cluster_uid, :daily_bucket, :primary_item_uid, :title, :dimension_id, :dimension_label,
          :dimension_icon, :summary, :why_it_matters, :item_uids_json,
          :reference_items_json, :source_names_json, :source_urls_json, :source_count, :cross_source_count,
          :cluster_score, :rank, :display_mode, :tags_json, :platform_hints_json, :created_at, :updated_at
        )
        """,
        clusters,
    )


def replace_topic_candidates(conn: sqlite3.Connection, daily_bucket: str, candidates: list[dict]) -> None:
    conn.execute("DELETE FROM topic_candidates WHERE daily_bucket = ?", (daily_bucket,))
    if not candidates:
        return
    conn.executemany(
        """
        INSERT INTO topic_candidates(
          candidate_uid, cluster_uid, daily_bucket, title, source_title,
          angle, topic_type, core_question, target_audience_json, dimension_id,
          topic_score, score_breakdown_json, platform_fit_json, recommended_platforms_json,
          source_item_uid, reference_items_json, reason, status, processing_version,
          created_at, updated_at
        )
        VALUES (
          :candidate_uid, :cluster_uid, :daily_bucket, :title, :source_title,
          :angle, :topic_type, :core_question, :target_audience_json, :dimension_id,
          :topic_score, :score_breakdown_json, :platform_fit_json, :recommended_platforms_json,
          :source_item_uid, :reference_items_json, :reason, :status, :processing_version,
          :created_at, :updated_at
        )
        """,
        candidates,
    )


def upsert_sources(conn: sqlite3.Connection, sources: dict, seen_at: str) -> None:
    for name, source in sources.items():
        config_json = source.get("config_json")
        config_hash = source.get("config_hash")
        conn.execute(
            """
            INSERT INTO sources(
              name, adapter, enabled, schedule, source_type, platform, provider,
              role, priority, reliability, config_hash, config_json,
              last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              adapter = excluded.adapter,
              enabled = excluded.enabled,
              schedule = excluded.schedule,
              source_type = excluded.source_type,
              platform = excluded.platform,
              provider = excluded.provider,
              role = excluded.role,
              priority = excluded.priority,
              reliability = excluded.reliability,
              config_hash = excluded.config_hash,
              config_json = excluded.config_json,
              last_seen_at = excluded.last_seen_at,
              updated_at = excluded.updated_at
            """,
            (
                name,
                source.get("adapter"),
                int(bool(source.get("enabled", True))),
                source.get("schedule"),
                source.get("source_type"),
                source.get("platform"),
                source.get("provider"),
                source.get("role", "collector"),
                float(source.get("priority") or 1),
                float(source.get("reliability") or 0.5),
                config_hash,
                config_json,
                seen_at,
                seen_at,
                seen_at,
            ),
        )


def create_run(conn: sqlite3.Connection, run: dict) -> None:
    conn.execute(
        """
        INSERT INTO collection_runs(
          run_id, mode, source_name, selected_sources_json, timezone, config_hash,
          window_start, window_end, daily_bucket, started_at, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run["run_id"],
            run["mode"],
            run.get("source_name"),
            run.get("selected_sources_json", "[]"),
            run.get("timezone"),
            run.get("config_hash"),
            run["window_start"],
            run["window_end"],
            run["daily_bucket"],
            run["started_at"],
            "running",
        ),
    )
    conn.commit()


def finish_run(conn: sqlite3.Connection, run_id: str, stats: dict) -> None:
    conn.execute(
        """
        UPDATE collection_runs
        SET finished_at = ?, duration_seconds = ?, status = ?,
            fetched_count = ?, normalized_count = ?, in_window_count = ?,
            quality_skipped_count = ?, out_of_window_count = ?, inserted_count = ?,
            duplicate_today_count = ?, duplicate_recent_count = ?,
            skipped_count = ?, source_stats_json = ?, processing_versions_json = ?,
            error_message = ?
        WHERE run_id = ?
        """,
        (
            stats.get("finished_at"),
            stats.get("duration_seconds"),
            stats.get("status", "ok"),
            stats.get("fetched_count", 0),
            stats.get("normalized_count", 0),
            stats.get("in_window_count", 0),
            stats.get("quality_skipped_count", 0),
            stats.get("out_of_window_count", 0),
            stats.get("inserted_count", 0),
            stats.get("duplicate_today_count", 0),
            stats.get("duplicate_recent_count", 0),
            stats.get("skipped_count", 0),
            stats.get("source_stats_json", "{}"),
            stats.get("processing_versions_json", "{}"),
            stats.get("error_message"),
            run_id,
        ),
    )
    conn.commit()

#!/usr/bin/env python3
import argparse
import hashlib
import importlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    yaml = None

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from db import connect, create_run, finish_run, init_db, insert_builder_activity_stats, insert_item, insert_raw_record, upsert_sources
from dedupe import resolve_duplicate_groups
from normalize import (
    AI_PROCESSING_VERSION,
    PROCESSING_VERSION,
    as_json_dict,
    as_json_list,
    calculate_collector_rank_score,
    calculate_freshness_score,
    calculate_velocity_score,
    extract_metrics,
    first_count,
    normalize_item,
    parse_iso,
)
from report import write_report


def load_config(path: str | None) -> dict:
    if path and Path(path).exists():
        text = Path(path).read_text(encoding="utf-8")
        if path.endswith((".yaml", ".yml")):
            if yaml is not None:
                return yaml.safe_load(text)
            return load_simple_yaml(text)
        return json.loads(text)

    return {
        "project": {
            "data_dir": str(Path.cwd() / "media-workflow/data"),
            "database_path": str(Path.cwd() / "media-workflow/data/media_sources.sqlite"),
            "timezone": "Asia/Shanghai",
        },
        "collection": {
            "default_window_hours": 24,
            "dedupe_recent_days": 2,
            "write_raw_files": True,
            "raw_dir": str(Path.cwd() / "media-workflow/data/raw"),
            "report_dir": str(Path.cwd() / "media-workflow/data/reports"),
        },
        "sources": {
            "aihot_selected": {
                "enabled": True,
                "adapter": "aihot",
                "mode": "selected",
                "take": 100,
            },
            "follow_builders": {
                "enabled": True,
                "adapter": "follow_builders",
                "feeds": ["x", "podcasts", "blogs"],
            },
        },
    }


def parse_scalar(value: str):
    value = value.strip()
    if value in ("", "null", "Null", "NULL"):
        return None
    if value in ("true", "True", "TRUE"):
        return True
    if value in ("false", "False", "FALSE"):
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def load_simple_yaml(text: str) -> dict:
    """Small YAML subset parser for examples/sources.yaml when PyYAML is absent."""
    root = {}
    stack = [(-1, root)]
    raw_lines = text.splitlines()

    for index, raw_line in enumerate(raw_lines):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            value = parse_scalar(line[2:])
            if isinstance(parent, list):
                parent.append(value)
            continue

        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            node = {}
            for lookahead in raw_lines[index + 1 :]:
                if not lookahead.strip() or lookahead.lstrip().startswith("#"):
                    continue
                next_indent = len(lookahead) - len(lookahead.lstrip(" "))
                if next_indent > indent and lookahead.strip().startswith("- "):
                    node = []
                break
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = parse_scalar(value)
    return root


def get_window(config: dict, args) -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(config.get("project", {}).get("timezone", "Asia/Shanghai"))
    end = datetime.now(tz)
    hours = int(config.get("collection", {}).get("default_window_hours", 24))
    if args.date:
        bucket_date = datetime.fromisoformat(args.date).date()
        start = datetime(bucket_date.year, bucket_date.month, bucket_date.day, tzinfo=tz)
        end = start + timedelta(days=1)
    else:
        start = end - timedelta(hours=hours)
    return start, end, end.astimezone(tz).date().isoformat() if not args.date else args.date


def should_keep_by_time(item: dict, window_start: datetime, window_end: datetime) -> bool:
    published_at = parse_iso(item.get("published_at"))
    if not published_at:
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=window_end.tzinfo)
    return window_start <= published_at.astimezone(window_end.tzinfo) <= window_end


def source_snapshot(name: str, source: dict) -> dict:
    config_json = json.dumps(source, ensure_ascii=False, sort_keys=True)
    adapter = source.get("adapter")
    return {
        "adapter": adapter,
        "enabled": source.get("enabled", True),
        "schedule": source.get("schedule"),
        "source_type": infer_config_source_type(source),
        "platform": infer_config_platform(source),
        "provider": infer_config_provider(adapter),
        "role": infer_config_role(name, source),
        "priority": source.get("priority") or source.get("source_priority") or 1,
        "reliability": source.get("reliability") or source.get("source_reliability") or 0.5,
        "config_hash": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
        "config_json": config_json,
    }


def infer_config_source_type(source: dict) -> str:
    if source.get("source_type"):
        return source["source_type"]
    adapter = source.get("adapter")
    if adapter == "aihot":
        return "external_api"
    if adapter == "x_builder_monitor":
        return "x"
    if adapter == "news_aggregator":
        return "registry_aggregator"
    return adapter or "unknown"


def infer_config_platform(source: dict) -> str:
    if source.get("platform"):
        return source["platform"]
    adapter = source.get("adapter")
    if adapter == "x_builder_monitor":
        return "x"
    if adapter == "aihot":
        return "external_api"
    if adapter == "news_aggregator":
        return "mixed"
    return "other"


def infer_config_provider(adapter: str | None) -> str | None:
    if adapter == "aihot":
        return "AIHOT"
    if adapter == "x_builder_monitor":
        return "nitter/rss"
    return adapter


def infer_config_role(name: str, source: dict) -> str:
    if source.get("role"):
        return source["role"]
    if source.get("adapter") == "aihot":
        return "external_curated_signal"
    if name == "news_aggregator":
        return "owned_aggregator"
    return "collector"


def write_raw(raw_dir: str, source_name: str, daily_bucket: str, records: list[dict]) -> str:
    out_dir = Path(raw_dir) / source_name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{daily_bucket}.{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def run_source(conn, run_id: str, name: str, source_config: dict, config: dict, window_start, window_end, daily_bucket: str, collected_at: str) -> dict:
    stats = {
        "fetched": 0,
        "normalized": 0,
        "in_window": 0,
        "quality_skipped": 0,
        "out_of_window": 0,
        "new": 0,
        "duplicate_today": 0,
        "duplicate_recent": 0,
        "skipped": 0,
        "status": "ok",
    }
    adapter_name = source_config.get("adapter")
    builder_stats = {}
    try:
        module = importlib.import_module(f"adapters.{adapter_name}")
        raw_records = module.fetch(source_config, window_start, window_end)
        stats["fetched"] = len(raw_records)
        if config.get("collection", {}).get("write_raw_files", True):
            write_raw(config["collection"]["raw_dir"], name, daily_bucket, raw_records)

        for raw in raw_records:
            raw = dict(raw)
            raw_record_uid = insert_raw_capture(
                conn, raw, run_id, name, adapter_name, daily_bucket, collected_at, window_start, window_end
            )
            raw["_raw_record_uid"] = raw_record_uid
            builder_key = get_builder_key(raw) if adapter_name == "x_builder_monitor" else None
            builder_row = None
            if builder_key:
                builder_row = builder_stats.setdefault(
                    builder_key,
                    new_builder_stats_row(raw, run_id, daily_bucket, name, window_start, window_end, collected_at),
                )
                builder_row["fetched_count"] += 1
                track_builder_published_at(builder_row, raw.get("published_at"))
            item = normalize_item(raw, adapter_name, collected_at, daily_bucket)
            if not item:
                stats["skipped"] += 1
                stats["quality_skipped"] += 1
                if builder_row:
                    builder_row["quality_skipped_count"] += 1
                    builder_row["skipped_count"] += 1
                continue
            stats["normalized"] += 1
            if builder_row:
                builder_row["normalized_count"] += 1
            if not should_keep_by_time(item, window_start, window_end):
                item["status"] = "skipped"
                stats["skipped"] += 1
                stats["out_of_window"] += 1
                if builder_row:
                    builder_row["out_of_window_count"] += 1
                    builder_row["skipped_count"] += 1
                insert_item(conn, item)
                continue
            stats["in_window"] += 1
            if builder_row:
                builder_row["in_window_count"] += 1

            insert_item(conn, item)
            stats["new"] += 1
            if builder_row:
                builder_row["new_count"] += 1
        insert_builder_activity_stats(conn, list(builder_stats.values()))
        conn.commit()
    except Exception as exc:
        stats["status"] = f"error: {exc}"
    return stats


def insert_raw_capture(
    conn,
    raw: dict,
    run_id: str,
    collector: str,
    adapter: str,
    daily_bucket: str,
    fetched_at: str,
    window_start,
    window_end,
) -> str:
    payload_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    raw_uid_seed = f"{daily_bucket}:{collector}:{adapter}:{raw.get('url') or raw.get('link') or raw.get('sourceUrl') or ''}:{payload_hash}"
    raw_uid = "raw_" + hashlib.sha256(raw_uid_seed.encode("utf-8")).hexdigest()[:24]
    source_name = raw.get("source_name") or raw.get("source") or raw.get("sourceName") or collector
    metrics = extract_metrics(raw)
    raw_engagement = as_json_dict(raw.get("engagement_raw") or raw.get("metrics") or raw.get("stats") or raw.get("engagement"))
    if raw.get("heat") is not None:
        raw_engagement.setdefault("heat", raw.get("heat"))
    raw_platform = raw.get("platform")
    raw_content = raw.get("content") or raw.get("transcript")
    raw_summary = raw.get("summary") or raw.get("description") or raw.get("text")
    if raw_platform in {"x", "twitter"} and raw_summary == raw_content:
        raw_summary = None
    raw_author = raw.get("author") or raw.get("builder") or raw.get("sourceName") or raw.get("source_name")
    if not raw_author and adapter == "aihot" and raw.get("source") != "AIHOT":
        raw_author = raw.get("source")
    record = {
        "raw_uid": raw_uid,
        "run_id": run_id,
        "daily_bucket": daily_bucket,
        "collector": collector,
        "adapter": adapter,
        "source_name": source_name,
        "raw_source_type": raw.get("source_type") or raw.get("sourceType"),
        "raw_platform": raw_platform,
        "raw_source_id": raw.get("source_id") or raw.get("sourceId") or raw.get("channel_id") or raw.get("channelId"),
        "raw_item_id": raw.get("item_id") or raw.get("itemId") or raw.get("id") or raw.get("objectID") or raw.get("tweet_id") or raw.get("status_id"),
        "raw_title": raw.get("title"),
        "raw_summary": raw_summary,
        "raw_content": raw_content,
        "raw_url": raw.get("url") or raw.get("sourceUrl") or raw.get("link"),
        "raw_published_at": raw.get("published_at") or raw.get("publishedAt") or raw.get("time"),
        "raw_updated_at": raw.get("updated_at") or raw.get("updatedAt") or raw.get("modified_at") or raw.get("modifiedAt"),
        "raw_created_at": raw.get("created_at") or raw.get("createdAt"),
        "raw_collected_window_start": window_start.isoformat(),
        "raw_collected_window_end": window_end.isoformat(),
        "raw_author": raw_author,
        "raw_author_handle": raw.get("author_handle") or raw.get("handle"),
        "raw_author_id": raw.get("author_id") or raw.get("authorId") or raw.get("user_id") or raw.get("userId"),
        "raw_language": raw.get("language") or raw.get("lang"),
        "raw_category": raw.get("category"),
        "raw_content_type": raw.get("content_type") or raw.get("contentType") or raw.get("type"),
        "raw_tags_json": json.dumps(as_json_list(raw.get("tags") or raw.get("topics") or raw.get("categories") or raw.get("source_tags")), ensure_ascii=False),
        "raw_media_urls_json": json.dumps(as_json_list(raw.get("media_urls") or raw.get("media") or raw.get("images") or raw.get("image") or raw.get("thumbnail")), ensure_ascii=False),
        "raw_related_urls_json": json.dumps(as_json_list(raw.get("related_urls") or raw.get("links") or raw.get("references")), ensure_ascii=False),
        "raw_like_count": metrics.get("like_count"),
        "raw_comment_count": metrics.get("comment_count"),
        "raw_repost_count": metrics.get("repost_count"),
        "raw_favorite_count": metrics.get("favorite_count"),
        "raw_view_count": metrics.get("view_count"),
        "raw_quote_count": metrics.get("quote_count"),
        "raw_reply_count": metrics.get("reply_count"),
        "raw_share_count": first_count(raw, ["share_count", "shares", "shareCount"]),
        "raw_bookmark_count": first_count(raw, ["bookmark_count", "bookmarks", "bookmarkCount"]),
        "raw_impression_count": first_count(raw, ["impression_count", "impressions", "impressionCount"]),
        "raw_play_count": first_count(raw, ["play_count", "plays", "playCount"]),
        "raw_download_count": first_count(raw, ["download_count", "downloads", "downloadCount"]),
        "raw_star_count": first_count(raw, ["star_count", "stars", "stargazers_count", "stargazersCount"]),
        "raw_fork_count": first_count(raw, ["fork_count", "forks", "forks_count", "forksCount"]),
        "raw_author_followers": metrics.get("author_followers"),
        "raw_author_verified": int(bool(raw.get("author_verified") or raw.get("verified"))) if ("author_verified" in raw or "verified" in raw) else None,
        "raw_engagement_json": json.dumps(raw_engagement, ensure_ascii=False),
        "raw_metrics_at": raw.get("raw_metrics_at") or raw.get("metrics_at") or fetched_at,
        "raw_fetch_status": raw.get("fetch_status") or raw.get("status") or "ok",
        "raw_fetch_error": raw.get("fetch_error") or raw.get("error"),
        "raw_http_status": raw.get("http_status") or raw.get("status_code") or raw.get("statusCode"),
        "raw_provider": raw.get("provider") or raw.get("source_provider") or ("AIHOT" if adapter == "aihot" else None),
        "raw_provider_url": raw.get("provider_url") or raw.get("feed_url") or raw.get("api_url"),
        "raw_payload_json": payload_json,
        "payload_hash": payload_hash,
        "fetched_at": fetched_at,
        "processing_status": "raw",
        "created_at": fetched_at,
    }
    return insert_raw_record(conn, record)


def get_builder_key(raw: dict) -> str | None:
    handle = raw.get("author_handle") or raw.get("handle")
    if handle:
        return str(handle).lower().lstrip("@")
    return raw.get("builder_id")


def new_builder_stats_row(raw: dict, run_id: str, daily_bucket: str, source_name: str, window_start, window_end, created_at: str) -> dict:
    return {
        "run_id": run_id,
        "daily_bucket": daily_bucket,
        "source_name": source_name,
        "builder_id": raw.get("builder_id"),
        "builder_name": raw.get("author") or raw.get("builder") or raw.get("source_name"),
        "handle": str(raw.get("author_handle") or raw.get("handle") or "").lower().lstrip("@"),
        "company_id": raw.get("company_id"),
        "fetched_count": 0,
        "normalized_count": 0,
        "in_window_count": 0,
        "quality_skipped_count": 0,
        "out_of_window_count": 0,
        "new_count": 0,
        "duplicate_today_count": 0,
        "duplicate_recent_count": 0,
        "skipped_count": 0,
        "fetch_success_rate": None,
        "in_window_rate": None,
        "duplicate_rate": None,
        "suggested_max_items": None,
        "processing_version": "builder-activity-v2",
        "oldest_published_at": None,
        "newest_published_at": None,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "created_at": created_at,
    }


def track_builder_published_at(row: dict, published_at: str | None) -> None:
    parsed = parse_iso(published_at)
    if not parsed:
        return
    value = parsed.isoformat()
    if row["oldest_published_at"] is None or value < row["oldest_published_at"]:
        row["oldest_published_at"] = value
    if row["newest_published_at"] is None or value > row["newest_published_at"]:
        row["newest_published_at"] = value


def collect(args) -> None:
    config = load_config(args.config)
    db_path = config.get("project", {}).get("database_path")
    conn = connect(db_path)
    init_db(conn)

    window_start, window_end, daily_bucket = get_window(config, args)
    collected_at = datetime.now(ZoneInfo(config.get("project", {}).get("timezone", "Asia/Shanghai"))).isoformat()
    upsert_sources(
        conn,
        {
            name: source_snapshot(name, source)
            for name, source in config.get("sources", {}).items()
        },
        collected_at,
    )
    conn.commit()
    selected_sources = {
        name: source
        for name, source in config.get("sources", {}).items()
        if source.get("enabled", True) and (args.source in (None, "all", name))
    }
    run_id = f"run_{daily_bucket}_{uuid.uuid4().hex[:10]}"
    config_hash = hashlib.sha256(
        json.dumps(selected_sources, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    timezone_name = config.get("project", {}).get("timezone", "Asia/Shanghai")
    create_run(
        conn,
        {
            "run_id": run_id,
            "mode": args.mode,
            "source_name": args.source or "all",
            "selected_sources_json": json.dumps(list(selected_sources.keys()), ensure_ascii=False),
            "timezone": timezone_name,
            "config_hash": config_hash,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "daily_bucket": daily_bucket,
            "started_at": collected_at,
        },
    )

    aggregate = {
        "fetched_count": 0,
        "normalized_count": 0,
        "in_window_count": 0,
        "quality_skipped_count": 0,
        "out_of_window_count": 0,
        "inserted_count": 0,
        "duplicate_today_count": 0,
        "duplicate_recent_count": 0,
        "skipped_count": 0,
        "source_stats": {},
    }
    for name, source_config in selected_sources.items():
        stats = run_source(conn, run_id, name, source_config, config, window_start, window_end, daily_bucket, collected_at)
        aggregate["source_stats"][name] = stats
        aggregate["fetched_count"] += stats["fetched"]
        aggregate["normalized_count"] += stats["normalized"]
        aggregate["in_window_count"] += stats["in_window"]
        aggregate["quality_skipped_count"] += stats["quality_skipped"]
        aggregate["out_of_window_count"] += stats["out_of_window"]
        aggregate["inserted_count"] += stats["new"]
        aggregate["skipped_count"] += stats["skipped"]

    resolve_duplicate_groups(
        conn,
        daily_bucket,
        int(config.get("collection", {}).get("dedupe_recent_days", 2)),
    )
    refresh_source_stats_after_dedupe(conn, run_id, aggregate["source_stats"])
    refresh_builder_activity_after_dedupe(conn, run_id)
    aggregate["inserted_count"] = sum(source.get("new", 0) for source in aggregate["source_stats"].values())
    aggregate["duplicate_today_count"] = sum(source.get("duplicate_today", 0) for source in aggregate["source_stats"].values())
    aggregate["duplicate_recent_count"] = sum(source.get("duplicate_recent", 0) for source in aggregate["source_stats"].values())
    finished_at = datetime.now(ZoneInfo(config.get("project", {}).get("timezone", "Asia/Shanghai")))
    aggregate["finished_at"] = finished_at.isoformat()
    aggregate["duration_seconds"] = round((finished_at - datetime.fromisoformat(collected_at)).total_seconds(), 3)
    aggregate["source_stats_json"] = json.dumps(aggregate["source_stats"], ensure_ascii=False, sort_keys=True)
    aggregate["processing_versions_json"] = json.dumps(
        {
            "source_items": PROCESSING_VERSION,
            "title_summary": AI_PROCESSING_VERSION,
            "dedupe": "dedupe-v2",
            "topic_candidates": "topic-candidates-v2",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    source_errors = [
        f"{name}: {source.get('status')}"
        for name, source in aggregate["source_stats"].items()
        if source.get("status") != "ok"
    ]
    aggregate["status"] = "partial_error" if source_errors else "ok"
    if source_errors:
        aggregate["error_message"] = "; ".join(source_errors)
    update_collector_scores(conn, daily_bucket, window_start, window_end)
    finish_run(conn, run_id, aggregate)
    report_path = write_report(
        config["collection"]["report_dir"],
        daily_bucket,
        window_start.isoformat(),
        window_end.isoformat(),
        aggregate,
        args.source or "all",
    )
    raw_source_filter = None
    if args.source not in (None, "all"):
        raw_source_filter = sorted({source.get("adapter") for source in selected_sources.values() if source.get("adapter")})
    write_markdown_export(
        conn,
        config["collection"]["report_dir"],
        daily_bucket,
        window_start,
        window_end,
        args.source or "all",
        raw_source_filter,
    )
    print(json.dumps({"run_id": run_id, "database": db_path, "report": report_path, **aggregate}, ensure_ascii=False, indent=2))


def refresh_source_stats_after_dedupe(conn, run_id: str, source_stats: dict) -> None:
    rows = conn.execute(
        """
        SELECT r.collector, si.status, COUNT(*) AS count
        FROM source_items si
        JOIN raw_source_records r ON r.raw_uid = si.raw_record_uid
        WHERE r.run_id = ?
        GROUP BY r.collector, si.status
        """,
        (run_id,),
    ).fetchall()
    for stats in source_stats.values():
        stats["new"] = 0
        stats["duplicate_today"] = 0
        stats["duplicate_recent"] = 0
    status_map = {
        "new": "new",
        "duplicate_today": "duplicate_today",
        "duplicate_recent": "duplicate_recent",
    }
    for row in rows:
        stats = source_stats.get(row["collector"])
        if not stats:
            continue
        key = status_map.get(row["status"])
        if key:
            stats[key] = int(row["count"] or 0)


def refresh_builder_activity_after_dedupe(conn, run_id: str) -> None:
    rows = conn.execute(
        """
        SELECT
          r.collector,
          LOWER(LTRIM(COALESCE(r.raw_author_handle, ''), '@')) AS handle,
          si.status,
          COUNT(*) AS count
        FROM source_items si
        JOIN raw_source_records r ON r.raw_uid = si.raw_record_uid
        WHERE r.run_id = ?
          AND COALESCE(r.raw_author_handle, '') != ''
        GROUP BY r.collector, handle, si.status
        """,
        (run_id,),
    ).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault((row["collector"], row["handle"]), {})[row["status"]] = int(row["count"] or 0)
    for (collector, handle), counts in grouped.items():
        conn.execute(
            """
            UPDATE builder_activity_stats
            SET new_count = ?,
                duplicate_today_count = ?,
                duplicate_recent_count = ?,
                skipped_count = quality_skipped_count + out_of_window_count + ?,
                fetch_success_rate = CASE
                  WHEN fetched_count > 0 THEN ROUND(CAST(normalized_count AS REAL) / fetched_count, 4)
                  ELSE NULL
                END,
                in_window_rate = CASE
                  WHEN normalized_count > 0 THEN ROUND(CAST(in_window_count AS REAL) / normalized_count, 4)
                  ELSE NULL
                END,
                duplicate_rate = CASE
                  WHEN in_window_count > 0 THEN ROUND(CAST(? AS REAL) / in_window_count, 4)
                  ELSE NULL
                END,
                suggested_max_items = CASE
                  WHEN in_window_count <= 3 THEN 5
                  WHEN in_window_count <= 6 THEN 8
                  ELSE 10
                END,
                processing_version = 'builder-activity-v2'
            WHERE run_id = ? AND source_name = ? AND handle = ?
            """,
            (
                counts.get("new", 0),
                counts.get("duplicate_today", 0),
                counts.get("duplicate_recent", 0),
                counts.get("duplicate_today", 0) + counts.get("duplicate_recent", 0),
                counts.get("duplicate_today", 0) + counts.get("duplicate_recent", 0),
                run_id,
                collector,
                handle,
            ),
        )
    conn.commit()


def write_markdown_export(
    conn,
    report_dir: str,
    daily_bucket: str,
    window_start=None,
    window_end=None,
    report_scope: str = "all",
    raw_source_filter: list[str] | None = None,
) -> str:
    suffix = "all_new_items" if report_scope in ("", "all", None) else f"{report_scope}.new_items"
    path = Path(report_dir) / f"{daily_bucket}.{suffix}.md"
    raw_source_clause = ""
    params = [daily_bucket]
    if raw_source_filter:
        placeholders = ",".join("?" for _ in raw_source_filter)
        raw_source_clause = f" AND raw_source IN ({placeholders})"
        params.extend(raw_source_filter)
    rows = conn.execute(
        f"""
        SELECT
          COALESCE(title_zh, title) AS title_display,
          source_name,
          published_at,
          COALESCE(summary_zh, summary, '') AS summary_display,
          engagement_score,
          platform_engagement_percentile,
          engagement_velocity_score,
          source_priority,
          collector_rank_score,
          topic_tags_json,
          url,
          translation_status
        FROM source_items
        WHERE daily_bucket = ? AND status = 'new'
          {raw_source_clause}
        ORDER BY collector_rank_score DESC, published_at DESC
        """,
        params,
    ).fetchall()
    if window_start and window_end:
        rows = [row for row in rows if _row_in_window(row["published_at"], window_start, window_end)]

    lines = [
        f"# New Source Items · {daily_bucket}",
        "",
        "| 标题 | 来源 | 发布时间 | 摘要 | 排序分 | 热度分 | 平台百分位 | 速度分 | 来源权重 | 主题标签 | 翻译状态 | 链接 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row["title_display"]),
                    _md(row["source_name"]),
                    _md(row["published_at"] or ""),
                    _md(row["summary_display"]),
                    _md(row["collector_rank_score"]),
                    _md(row["engagement_score"]),
                    _md(row["platform_engagement_percentile"]),
                    _md(row["engagement_velocity_score"]),
                    _md(row["source_priority"]),
                    _md(_display_json_list(row["topic_tags_json"])),
                    _md(row["translation_status"]),
                    _md(row["url"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def update_collector_scores(conn, daily_bucket: str, window_start=None, window_end=None) -> None:
    rows = conn.execute(
        """
        SELECT
          item_uid, platform, engagement_score, engagement_velocity_score,
          source_priority, source_reliability, freshness_score, published_at, collected_at,
          like_count, comment_count, repost_count, favorite_count, view_count, quote_count, reply_count
        FROM source_items
        WHERE daily_bucket = ? AND status = 'new'
        """,
        (daily_bucket,),
    ).fetchall()
    by_platform: dict[str, list] = {}
    for row in rows:
        if window_start and window_end and not _row_in_window(row["published_at"], window_start, window_end):
            continue
        by_platform.setdefault(row["platform"] or "other", []).append(row)

    for platform_rows in by_platform.values():
        metric_rows = [row for row in platform_rows if _has_engagement_metrics(row)]
        scores = [float(row["engagement_score"] or 0) for row in metric_rows]
        all_zero = not scores or all(score <= 0 for score in scores)
        sorted_scores = sorted(scores)
        denominator = max(len(sorted_scores) - 1, 1)
        for row in platform_rows:
            if all_zero or not _has_engagement_metrics(row):
                percentile = 0.5
            else:
                score = float(row["engagement_score"] or 0)
                matching_indexes = [index for index, item_score in enumerate(sorted_scores) if item_score == score]
                if matching_indexes:
                    percentile = round((matching_indexes[0] + matching_indexes[-1]) / 2 / denominator, 4)
                else:
                    rank_index = max(index for index, item_score in enumerate(sorted_scores) if item_score <= score)
                    percentile = round(rank_index / denominator, 4)
            engagement_score = float(row["engagement_score"] or 0)
            freshness_score = calculate_freshness_score(row["published_at"], row["collected_at"])
            engagement_velocity_score = calculate_velocity_score(engagement_score, row["published_at"], row["collected_at"])
            collector_rank_score = calculate_collector_rank_score(
                percentile,
                engagement_velocity_score,
                float(row["source_priority"] or 1),
                float(row["source_reliability"] or 0.5),
                freshness_score,
            )
            conn.execute(
                """
                UPDATE source_items
                SET platform_engagement_percentile = ?,
                    engagement_velocity_score = ?,
                    freshness_score = ?,
                    collector_rank_score = ?
                WHERE item_uid = ?
                """,
                (percentile, engagement_velocity_score, freshness_score, collector_rank_score, row["item_uid"]),
            )
    conn.commit()


def _row_in_window(published_at: str, window_start, window_end) -> bool:
    parsed = parse_iso(published_at)
    if not parsed:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=window_end.tzinfo)
    return window_start <= parsed.astimezone(window_end.tzinfo) <= window_end


def _has_engagement_metrics(row) -> bool:
    return any(
        row[key] is not None
        for key in (
            "like_count",
            "comment_count",
            "repost_count",
            "favorite_count",
            "view_count",
            "quote_count",
            "reply_count",
        )
    )


def _md(value: str) -> str:
    if value is None:
        value = ""
    value = str(value).replace("\n", "<br>")
    return value.replace("|", "\\|")


def _display_json_list(value: str) -> str:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, list):
        return ""
    return ", ".join(str(item) for item in data[:5])


def list_sources(args) -> None:
    config = load_config(args.config)
    for name, source in config.get("sources", {}).items():
        print(f"{name}\tadapter={source.get('adapter')}\tenabled={source.get('enabled', True)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--mode", choices=["daily", "backfill", "report", "list-sources"], default="daily")
    parser.add_argument("--source", default=None)
    parser.add_argument("--date")
    parser.add_argument("--days", type=int, default=1)
    args = parser.parse_args()

    if args.mode == "list-sources":
        list_sources(args)
        return
    if args.mode == "backfill":
        for offset in range(args.days - 1, -1, -1):
            target = datetime.now().date() - timedelta(days=offset)
            args.date = target.isoformat()
            collect(args)
        return
    if args.mode == "report":
        config = load_config(args.config)
        conn = connect(config.get("project", {}).get("database_path"))
        init_db(conn)
        target_date = args.date or datetime.now(ZoneInfo(config.get("project", {}).get("timezone", "Asia/Shanghai"))).date().isoformat()
        path = write_markdown_export(conn, config["collection"]["report_dir"], target_date)
        print(json.dumps({"date": target_date, "report": path}, ensure_ascii=False, indent=2))
        return
    collect(args)


if __name__ == "__main__":
    main()

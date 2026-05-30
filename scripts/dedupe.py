from difflib import SequenceMatcher


def title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def find_duplicate(conn, item: dict, recent_days: int = 2) -> dict | None:
    same_day = conn.execute(
        """
        SELECT item_uid, normalized_title, canonical_url, content_hash
        FROM source_items
        WHERE daily_bucket = ?
          AND status = 'new'
          AND (canonical_url = ? OR content_hash = ?)
        LIMIT 1
        """,
        (item["daily_bucket"], item["canonical_url"], item["content_hash"]),
    ).fetchone()
    if same_day:
        matched_field = (
            "canonical_url"
            if same_day["canonical_url"] == item["canonical_url"]
            else "content_hash"
        )
        return {
            "duplicate_of_uid": same_day["item_uid"],
            "duplicate_type": "same_day",
            "match_method": "exact",
            "matched_field": matched_field,
            "match_value": item[matched_field],
            "dedupe_rule": f"same_day_{matched_field}",
            "similarity_score": 1.0,
            "threshold": 1.0,
            "window_days": 0,
            "status": "duplicate_today",
        }

    recent = conn.execute(
        """
        SELECT item_uid, normalized_title, canonical_url, content_hash
        FROM source_items
        WHERE daily_bucket < ?
          AND daily_bucket >= date(?, ?)
          AND status = 'new'
          AND (canonical_url = ? OR content_hash = ?)
        ORDER BY daily_bucket DESC
        LIMIT 1
        """,
        (
            item["daily_bucket"],
            item["daily_bucket"],
            f"-{recent_days} days",
            item["canonical_url"],
            item["content_hash"],
        ),
    ).fetchone()
    if recent:
        matched_field = (
            "canonical_url"
            if recent["canonical_url"] == item["canonical_url"]
            else "content_hash"
        )
        return {
            "duplicate_of_uid": recent["item_uid"],
            "duplicate_type": "recent_days",
            "match_method": "exact",
            "matched_field": matched_field,
            "match_value": item[matched_field],
            "dedupe_rule": f"recent_days_{matched_field}",
            "similarity_score": 1.0,
            "threshold": 1.0,
            "window_days": recent_days,
            "status": "duplicate_recent",
        }

    candidates = conn.execute(
        """
        SELECT item_uid, normalized_title, daily_bucket
        FROM source_items
        WHERE daily_bucket >= date(?, ?)
          AND daily_bucket <= ?
          AND status = 'new'
        """,
        (item["daily_bucket"], f"-{recent_days} days", item["daily_bucket"]),
    ).fetchall()
    best = None
    for row in candidates:
        score = title_similarity(item["normalized_title"], row["normalized_title"])
        if score >= 0.92 and (best is None or score > best["similarity_score"]):
            best = {
                "duplicate_of_uid": row["item_uid"],
                "duplicate_type": "same_day"
                if row["daily_bucket"] == item["daily_bucket"]
                else "recent_days",
                "match_method": "fuzzy_title",
                "matched_field": "normalized_title",
                "match_value": item["normalized_title"],
                "dedupe_rule": "same_day_title_similarity"
                if row["daily_bucket"] == item["daily_bucket"]
                else "recent_days_title_similarity",
                "similarity_score": score,
                "threshold": 0.92,
                "window_days": 0
                if row["daily_bucket"] == item["daily_bucket"]
                else recent_days,
                "status": "duplicate_today"
                if row["daily_bucket"] == item["daily_bucket"]
                else "duplicate_recent",
            }
    return best


def resolve_duplicate_groups(conn, daily_bucket: str, recent_days: int = 2) -> dict:
    """Resolve duplicates after daily candidates are inserted.

    Same-day duplicates are grouped first and the best representative is kept
    as `new`. Recent-day duplicates still suppress the current-day item to
    avoid repeating an already surfaced event.
    """
    reset_current_day_duplicate_status(conn, daily_bucket)
    same_day_stats = resolve_same_day_duplicates(conn, daily_bucket)
    recent_stats = resolve_recent_duplicates(conn, daily_bucket, recent_days)
    return {
        "new": count_new_items(conn, daily_bucket),
        "duplicate_today": same_day_stats["duplicate_today"],
        "duplicate_recent": recent_stats["duplicate_recent"],
    }


def reset_current_day_duplicate_status(conn, daily_bucket: str) -> None:
    conn.execute(
        """
        UPDATE source_items
        SET status = 'new'
        WHERE daily_bucket = ?
          AND status IN ('duplicate_today', 'duplicate_recent')
        """,
        (daily_bucket,),
    )
    conn.execute(
        """
        DELETE FROM item_duplicates
        WHERE item_uid IN (
          SELECT item_uid FROM source_items WHERE daily_bucket = ?
        )
        """,
        (daily_bucket,),
    )


def resolve_same_day_duplicates(conn, daily_bucket: str) -> dict:
    rows = conn.execute(
        """
        SELECT *
        FROM source_items
        WHERE daily_bucket = ? AND status = 'new'
        """,
        (daily_bucket,),
    ).fetchall()
    groups = build_same_day_groups(rows)
    duplicate_count = 0
    for group in groups:
        if len(group) <= 1:
            continue
        winner = choose_best_item(group)
        for row in group:
            if row["item_uid"] == winner["item_uid"]:
                continue
            duplicate = make_duplicate_record(row, winner, "same_day", 0)
            mark_duplicate(conn, row, duplicate, "duplicate_today")
            duplicate_count += 1
    return {"duplicate_today": duplicate_count}


def resolve_recent_duplicates(conn, daily_bucket: str, recent_days: int) -> dict:
    current_rows = conn.execute(
        """
        SELECT *
        FROM source_items
        WHERE daily_bucket = ? AND status = 'new'
        """,
        (daily_bucket,),
    ).fetchall()
    previous_rows = conn.execute(
        """
        SELECT *
        FROM source_items
        WHERE daily_bucket < ?
          AND daily_bucket >= date(?, ?)
          AND status = 'new'
        """,
        (daily_bucket, daily_bucket, f"-{recent_days} days"),
    ).fetchall()
    duplicate_count = 0
    for row in current_rows:
        best_match = None
        for candidate in previous_rows:
            duplicate = make_duplicate_record(row, candidate, "recent_days", recent_days)
            if not duplicate:
                continue
            if best_match is None or duplicate["similarity_score"] > best_match["similarity_score"]:
                best_match = duplicate
        if best_match:
            mark_duplicate(conn, row, best_match, "duplicate_recent")
            duplicate_count += 1
    return {"duplicate_recent": duplicate_count}


def build_same_day_groups(rows) -> list[list]:
    parent = {row["item_uid"]: row["item_uid"] for row in rows}
    by_uid = {row["item_uid"]: row for row in rows}

    def find(uid):
        while parent[uid] != uid:
            parent[uid] = parent[parent[uid]]
            uid = parent[uid]
        return uid

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if make_duplicate_record(left, right, "same_day", 0):
                union(left["item_uid"], right["item_uid"])

    groups = {}
    for uid in parent:
        groups.setdefault(find(uid), []).append(by_uid[uid])
    return list(groups.values())


def choose_best_item(rows):
    return max(rows, key=item_quality_score)


def item_quality_score(row) -> float:
    content_len = len(row["content"] or "")
    summary_len = len(row["summary_zh"] or row["summary"] or "")
    has_metrics = any(
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
    source_type = (row["source_type"] or "").lower()
    platform = (row["platform"] or "").lower()
    score = 0.0
    score += 30.0 if row["is_primary_source"] else 0.0
    score += 20.0 if row["is_official_source"] else 0.0
    score += min(content_len / 1200.0, 1.0) * 25.0
    score += min(summary_len / 180.0, 1.0) * 10.0
    score += float(row["source_reliability"] or 0.5) * 20.0
    score += min(float(row["source_priority"] or 1.0), 3.0) * 5.0
    score += 8.0 if has_metrics else 0.0
    score += 5.0 if (row["language"] in {"zh", "mixed"} or row["summary_zh"] or row["title_zh"]) else 0.0
    score += 5.0 if source_type in {"blog", "paper", "github", "news"} else 0.0
    score -= 8.0 if platform == "x" and content_len < 280 else 0.0
    return round(score, 4)


def make_duplicate_record(item, candidate, duplicate_type: str, window_days: int) -> dict | None:
    if item["canonical_url"] and item["canonical_url"] == candidate["canonical_url"]:
        return {
            "duplicate_of_uid": candidate["item_uid"],
            "duplicate_type": duplicate_type,
            "match_method": "exact",
            "matched_field": "canonical_url",
            "match_value": item["canonical_url"],
            "dedupe_rule": f"{duplicate_type}_canonical_url",
            "similarity_score": 1.0,
            "threshold": 1.0,
            "window_days": window_days,
            "processing_version": "dedupe-v2",
        }
    if item["content_hash"] and item["content_hash"] == candidate["content_hash"]:
        return {
            "duplicate_of_uid": candidate["item_uid"],
            "duplicate_type": duplicate_type,
            "match_method": "exact",
            "matched_field": "content_hash",
            "match_value": item["content_hash"],
            "dedupe_rule": f"{duplicate_type}_content_hash",
            "similarity_score": 1.0,
            "threshold": 1.0,
            "window_days": window_days,
            "processing_version": "dedupe-v2",
        }
    score = title_similarity(item["normalized_title"], candidate["normalized_title"])
    if score >= 0.92:
        return {
            "duplicate_of_uid": candidate["item_uid"],
            "duplicate_type": duplicate_type,
            "match_method": "fuzzy_title",
            "matched_field": "normalized_title",
            "match_value": item["normalized_title"],
            "dedupe_rule": f"{duplicate_type}_title_similarity",
            "similarity_score": score,
            "threshold": 0.92,
            "window_days": window_days,
            "processing_version": "dedupe-v2",
        }
    return None


def mark_duplicate(conn, item, duplicate: dict, status: str) -> None:
    conn.execute(
        "UPDATE source_items SET status = ? WHERE item_uid = ?",
        (status, item["item_uid"]),
    )
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


def count_new_items(conn, daily_bucket: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM source_items WHERE daily_bucket = ? AND status = 'new'",
        (daily_bucket,),
    ).fetchone()
    return int(row["count"] or 0)

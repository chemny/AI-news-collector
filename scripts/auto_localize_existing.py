#!/usr/bin/env python3
import argparse
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from localize import localize_record
from normalize import clean_inline_text, clean_summary_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--status", default="new")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    translation_clause = (
        "AND translation_status IN ('needs_translation', 'auto_zh')"
        if args.force
        else "AND translation_status = 'needs_translation'"
    )
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT item_uid, title, summary, content, source_type
        FROM source_items
        WHERE daily_bucket = ?
          AND status = ?
          {translation_clause}
        ORDER BY published_at DESC
        """,
        (args.date, args.status),
    ).fetchall()

    updated = 0
    skipped = 0
    for row in rows:
        raw = {"content": row["content"], "auto_localize": True}
        title_zh, summary_zh, translation_status = localize_record(raw, row["title"], row["summary"] or row["content"])
        title_zh = clean_inline_text(title_zh)
        summary_zh = clean_summary_text(summary_zh, row["source_type"], 150)
        if not title_zh or not summary_zh or translation_status == "needs_translation":
            skipped += 1
            continue
        conn.execute(
            """
            UPDATE source_items
            SET title_zh = ?,
                summary_zh = ?,
                translation_status = ?,
                updated_at = datetime('now')
            WHERE item_uid = ?
            """,
            (title_zh, summary_zh, translation_status, row["item_uid"]),
        )
        fts_row = conn.execute(
            "SELECT id, title, title_zh, summary, summary_zh, content, source_name FROM source_items WHERE item_uid = ?",
            (row["item_uid"],),
        ).fetchone()
        if fts_row:
            conn.execute(
                """
                INSERT OR REPLACE INTO source_items_fts(rowid, title, title_zh, summary, summary_zh, content, source_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                fts_row,
            )
        updated += 1
    conn.commit()
    print({"matched": len(rows), "updated": updated, "skipped": skipped})


if __name__ == "__main__":
    main()

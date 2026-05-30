#!/usr/bin/env python3
import argparse
import json
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT item_uid, title, summary, source_name, url
        FROM source_items
        WHERE daily_bucket = ?
          AND status = 'new'
          AND translation_status = 'needs_translation'
        ORDER BY published_at DESC
        """,
        (args.date,),
    ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


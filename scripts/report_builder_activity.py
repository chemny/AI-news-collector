#!/usr/bin/env python3
import argparse
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          handle,
          COALESCE(builder_name, handle) AS builder_name,
          COUNT(*) AS run_count,
          ROUND(AVG(fetched_count), 2) AS avg_fetched,
          ROUND(AVG(in_window_count), 2) AS avg_in_window,
          MAX(in_window_count) AS max_in_window,
          ROUND(AVG(new_count), 2) AS avg_new,
          ROUND(AVG(duplicate_today_count + duplicate_recent_count), 2) AS avg_duplicate,
          ROUND(AVG(out_of_window_count), 2) AS avg_out_of_window,
          ROUND(AVG(quality_skipped_count), 2) AS avg_quality_skipped,
          ROUND(AVG(fetch_success_rate), 4) AS avg_fetch_success_rate,
          ROUND(AVG(in_window_rate), 4) AS avg_in_window_rate,
          ROUND(AVG(duplicate_rate), 4) AS avg_duplicate_rate,
          COALESCE(MAX(suggested_max_items), CASE
            WHEN MAX(in_window_count) <= 3 THEN 5
            WHEN MAX(in_window_count) <= 6 THEN 8
            ELSE 10
          END) AS suggested_max_items
        FROM builder_activity_stats
        WHERE created_at >= datetime('now', '-' || ? || ' days')
        GROUP BY handle
        ORDER BY avg_in_window DESC, max_in_window DESC, avg_new DESC
        LIMIT ?
        """,
        (args.days, args.limit),
    ).fetchall()

    print("| Handle | Name | Runs | Avg fetched | Avg in-window | Max in-window | Avg new | Avg dup | Avg old | Avg low-quality | Fetch success | In-window rate | Dup rate | Suggested max |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| @{row['handle']} | {row['builder_name']} | {row['run_count']} | "
            f"{row['avg_fetched']} | {row['avg_in_window']} | {row['max_in_window']} | "
            f"{row['avg_new']} | {row['avg_duplicate']} | {row['avg_out_of_window']} | "
            f"{row['avg_quality_skipped']} | {row['avg_fetch_success_rate']} | "
            f"{row['avg_in_window_rate']} | {row['avg_duplicate_rate']} | "
            f"{row['suggested_max_items']} |"
        )


if __name__ == "__main__":
    main()

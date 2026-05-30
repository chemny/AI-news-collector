#!/usr/bin/env python3
import argparse
import json
import sqlite3
from pathlib import Path
import re


def clean_inline_text(value):
    if value is None:
        return None
    value = re.sub(
        "["
        "\U0001F1E6-\U0001F1FF"
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FAFF"
        "\U00002700-\U000027BF"
        "\U00002600-\U000026FF"
        "]+",
        "",
        str(value),
    )
    value = re.sub(r"\s+", " ", str(value)).strip()
    value = re.sub(r"https?[:：]//\S+", "", value)
    value = re.sub(r"www\.\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > 150:
        value = value[:149].rstrip("，,；;：: ") + "…"
    return value or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--translations", required=True)
    args = parser.parse_args()

    translations = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    conn = sqlite3.connect(args.db)
    for item in translations:
        conn.execute(
            """
            UPDATE source_items
            SET title_zh = ?,
                summary_zh = ?,
                translation_status = 'translated',
                updated_at = datetime('now')
            WHERE item_uid = ?
            """,
            (
                clean_inline_text(item.get("title_zh")),
                clean_inline_text(item.get("summary_zh")),
                item["item_uid"],
            ),
        )
        row = conn.execute(
            "SELECT id, title, title_zh, summary, summary_zh, content, source_name FROM source_items WHERE item_uid = ?",
            (item["item_uid"],),
        ).fetchone()
        if row:
            conn.execute(
                """
                INSERT OR REPLACE INTO source_items_fts(rowid, title, title_zh, summary, summary_zh, content, source_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
    conn.commit()
    print(json.dumps({"updated": len(translations)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

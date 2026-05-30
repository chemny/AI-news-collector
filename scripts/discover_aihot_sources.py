#!/usr/bin/env python3
import argparse
import re
import sqlite3
from collections import defaultdict
from urllib.parse import urlparse


KNOWN_RSS_HINTS = {
    "developers.googleblog.com": "https://developers.googleblog.com/feeds/posts/default",
    "huggingface.co": "https://huggingface.co/blog/feed.xml",
    "simonwillison.net": "https://simonwillison.net/atom/everything/",
    "techcrunch.com": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "www.ithome.com": "https://www.ithome.com/rss/",
    "www.marktechpost.com": "https://www.marktechpost.com/feed/",
    "arstechnica.com": "https://feeds.arstechnica.com/arstechnica/technology-lab",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
          source_name,
          COUNT(*) AS item_count,
          MIN(published_at) AS first_seen,
          MAX(published_at) AS last_seen,
          GROUP_CONCAT(DISTINCT platform) AS platforms,
          GROUP_CONCAT(DISTINCT source_type) AS source_types
        FROM source_items
        WHERE raw_source = 'aihot'
        GROUP BY source_name
        HAVING COUNT(*) >= ?
        ORDER BY item_count DESC, source_name
        LIMIT ?
        """,
        (args.min_count, args.limit),
    ).fetchall()

    print("| Source | Count | Kind | Domain/Handle | Suggested status | RSS hint | First seen | Last seen |")
    print("|---|---:|---|---|---|---|---|---|")
    for row in rows:
        samples = conn.execute(
            """
            SELECT url
            FROM source_items
            WHERE raw_source = 'aihot' AND source_name = ? AND COALESCE(url, '') <> ''
            ORDER BY published_at DESC
            LIMIT 5
            """,
            (row["source_name"],),
        ).fetchall()
        urls = [sample["url"] for sample in samples]
        kind, identity, status, rss_hint = classify(row["source_name"], urls)
        print(
            "| "
            + " | ".join(
                [
                    md(row["source_name"]),
                    str(row["item_count"]),
                    kind,
                    md(identity),
                    status,
                    md(rss_hint or ""),
                    md(row["first_seen"] or ""),
                    md(row["last_seen"] or ""),
                ]
            )
            + " |"
        )


def classify(source_name: str, urls: list[str]) -> tuple[str, str, str, str | None]:
    x_handle = extract_x_handle(source_name, urls)
    if x_handle:
        return "x", f"@{x_handle}", "move_to_builder_profiles", None

    domains = [urlparse(url).netloc.lower() for url in urls if url]
    domain_counts = defaultdict(int)
    for domain in domains:
        domain_counts[domain] += 1
    domain = max(domain_counts.items(), key=lambda item: item[1])[0] if domain_counts else ""
    if not domain:
        return "unknown", "", "manual_review", None

    rss_hint = KNOWN_RSS_HINTS.get(domain)
    if rss_hint:
        return "rss", domain, "owned_or_verify", rss_hint
    if any(marker in source_name for marker in ("RSS", "Blog", "博客", "News", "官网", "Research")):
        return "web", domain, "verify", None
    return "web", domain, "manual_review", None


def extract_x_handle(source_name: str, urls: list[str]) -> str | None:
    match = re.search(r"@\s*([A-Za-z0-9_]+)", source_name)
    if match:
        return match.group(1)
    for url in urls:
        match = re.search(r"https?://(?:x|twitter)\.com/([^/?#]+)/", url)
        if match:
            return match.group(1)
    return None


def md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()

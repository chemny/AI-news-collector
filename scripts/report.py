from pathlib import Path


def write_report(report_dir: str, daily_bucket: str, window_start: str, window_end: str, stats: dict, report_scope: str = "all") -> str:
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    suffix = "collect_report" if report_scope in ("", "all", None) else f"{report_scope}.collect_report"
    path = Path(report_dir) / f"{daily_bucket}.{suffix}.md"
    lines = [
        f"# Collection Report · {daily_bucket}",
        "",
        f"Window: {window_start} to {window_end}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Fetched | {stats.get('fetched_count', 0)} |",
        f"| Normalized | {stats.get('normalized_count', 0)} |",
        f"| In window | {stats.get('in_window_count', 0)} |",
        f"| New | {stats.get('inserted_count', 0)} |",
        f"| Duplicate today | {stats.get('duplicate_today_count', 0)} |",
        f"| Duplicate recent | {stats.get('duplicate_recent_count', 0)} |",
        f"| Quality skipped | {stats.get('quality_skipped_count', 0)} |",
        f"| Out of window | {stats.get('out_of_window_count', 0)} |",
        f"| Skipped | {stats.get('skipped_count', 0)} |",
        f"| Duration seconds | {stats.get('duration_seconds', '')} |",
        "",
    ]
    if stats.get("source_stats"):
        lines.extend(["## Sources", "", "| Source | Fetched | Normalized | In window | New | Duplicate today | Duplicate recent | Quality skipped | Out of window | Skipped | Status |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"])
        for name, source in stats["source_stats"].items():
            lines.append(
                f"| {name} | {source.get('fetched', 0)} | {source.get('normalized', 0)} | "
                f"{source.get('in_window', 0)} | {source.get('new', 0)} | "
                f"{source.get('duplicate_today', 0)} | {source.get('duplicate_recent', 0)} | "
                f"{source.get('quality_skipped', 0)} | {source.get('out_of_window', 0)} | "
                f"{source.get('skipped', 0)} | {source.get('status', 'ok')} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- Only `status = new` items should flow into topic mining.",
            "- Duplicate records are kept in SQLite for audit and threshold tuning.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)

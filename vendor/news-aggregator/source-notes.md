# News Aggregator Integration Notes

Original inspiration: https://github.com/cclank/news-aggregator-skill

The bundled `rss_parser.py` is a small local stdlib-based RSS/Atom helper written for
this repository so the skill can run without installing the upstream project.

Use in this skill:

- Do not require users to install the upstream skill.
- Do not call upstream local files from `/tmp`, `~/.agents`, `~/.claude`, or `~/.codex`.
- Keep a small self-contained V1 subset of stable public sources.

V1 sources implemented locally:

- Hacker News front page / Algolia keyword search
- GitHub Trending
- arXiv cs.AI/cs.CL/cs.LG
- AI newsletters via RSS
- User OPML feeds
- AIHOT RSS fallback when configured as a news aggregator source

Sources intentionally not bundled in V1:

- Cookie/private-session sources.
- Fragile platform scraping requiring login.
- Playwright-heavy sources.
- Paid third-party APIs.

If a future version needs more sources, add them to our own adapter code and update this note. Users should only update this skill package.

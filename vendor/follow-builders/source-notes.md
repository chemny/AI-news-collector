# follow-builders Integration Notes

Upstream: https://github.com/zarazhangrui/follow-builders

Use in this skill:

- Read public center-feed JSON files from GitHub raw URLs.
- Do not require users to install the upstream skill.
- Do not require users to configure X API or podcast transcript keys.

Public feeds:

- `https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json`
- `https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-podcasts.json`
- `https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-blogs.json`

Current behavior:

- The upstream repository generates feeds on GitHub Actions.
- This skill only reads those feeds and maps them into local source cards.
- If we later self-host the same backend, update this skill's feed URLs or add a config option.

Do not make users install `follow-builders` separately.


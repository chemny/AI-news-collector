# Source Registry Schema

`source_registry.yaml` is the local source-of-truth for owned and externally curated information sources.

Default project path:

```text
media-workflow/config/source_registry.yaml
```

## Purpose

Use the registry to move from third-party curated feeds toward controllable local collection.

Source roles:

- `owned`: collected directly by our adapters.
- `verify`: candidate source that looks collectable but needs endpoint validation.
- `external_only`: source should stay behind an external service for now.
- `ignore`: low-value or irrelevant source.

## Top-Level Fields

| Field | Meaning |
|---|---|
| `version` | Schema version. Current value is `1`. |
| `policy` | Local collection policy and default behavior. |
| `sources` | Directly collectable or candidate sources. |
| `external_curated_sources` | External APIs or curated services such as AIHOT. |

## Source Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable lowercase identifier. |
| `name` | yes | Human-readable source name. |
| `type` | yes | `official_blog`, `rss`, `blog`, `newsletter`, `changelog`, `x`, `github`, `paper`, `media`, `external_api`. |
| `platform` | yes | `web`, `rss`, `x`, `github`, `other`. |
| `company_id` | no | Optional link to `builder_source_profiles.yaml`. |
| `urls` | no | Canonical web URLs. |
| `rss` | no | RSS/Atom feed URL when available. |
| `x_handle` | no | X handle for source accounts. |
| `priority` | yes | Local editorial priority. |
| `reliability` | yes | Baseline source reliability. |
| `enabled` | yes | Whether the source should be collected. |
| `migration_status` | yes | `owned`, `verify`, `external_only`, or `ignore`. |
| `tags` | no | Editorial tags used as source hints. |

## AIHOT Migration Rule

AIHOT should be treated as `external_curated_signal`, not as the core collector.

Use AIHOT to:

- discover candidate sources,
- cross-check our owned sources,
- catch missed stories,
- provide Chinese curated fallback.

Do not depend on AIHOT as the only source for critical categories.

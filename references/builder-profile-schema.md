# Builder Profile Schema

Builder profiles are the source of truth for monitored people, companies, and X builder accounts.

Default project path:

```text
media-workflow/config/builder_source_profiles.yaml
```

## Top-level Fields

| Field | Meaning |
|---|---|
| `version` | Schema version. Current value is `1`. |
| `companies` | Companies, labs, media organizations, funds, or product teams. |
| `builders` | People or company accounts monitored for builder updates. |

## Company Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable lowercase identifier, such as `openai`. |
| `name` | yes | Display name. |
| `type` | no | `ai_lab`, `big_tech`, `ai_tool`, `dev_tool`, `media`, `vc`, etc. |
| `priority` | no | Source priority used by collector ranking. |
| `official_sources` | no | Official blogs, news pages, changelogs, or docs. |
| `x_handles` | no | Company or related X handles. |

## Builder Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable lowercase identifier. |
| `name` | yes | Display name. |
| `handle` | yes for X | X handle without `@`. |
| `type` | yes | `person` or `company_account`. |
| `role` | no | `founder`, `researcher`, `product`, `engineer`, `creator`, etc. |
| `company_id` | no | Links to `companies[].id`. |
| `priority` | no | Builder-specific priority. Overrides company default. |
| `topics` | no | Editorial topic hints. |
| `max_items` | no | Optional per-builder fetch limit. Use only for unusually active official/product accounts. The global X default is `5`. |

## Management Rules

- Keep builder and company identity data in this profile, not inside adapter code.
- Prefer `company_id` links over free-text company names.
- Use stable IDs; changing IDs breaks historical analysis.
- Keep X handles without `@`.
- Validate the profile after editing:

```bash
python scripts/manage_builder_profiles.py validate --profiles media-workflow/config/builder_source_profiles.yaml
```

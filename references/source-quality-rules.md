# Source Quality Rules

Use these rules to decide whether a collected item is useful enough to enter the daily pool.

## Keep

- Official company announcements.
- Builder posts with concrete product, research, market, or workflow information.
- High-signal newsletters and blogs.
- Papers and repositories with clear novelty.
- Platform trend items with useful heat metadata.

## Skip

- Missing title or URL.
- Missing or unparseable publish time in daily mode.
- Published outside the configured 24-hour daily collection window.
- Empty summary and empty content.
- Multiline summaries in user-facing reports. Collapse whitespace before saving `summary` and `summary_zh`.
- Summaries that are mostly mentions, URLs, hashtags, or "learn more" style CTA text.
- Summary fields containing URLs.
- Emoji in titles or summaries.
- User-facing Chinese summaries longer than 150 Chinese characters.
- Pure ads without useful information.
- Duplicates from the same day or recent-day window.
- Items older than the collection window unless running backfill.
- Login-only pages that cannot be verified from public content.
- Private-cookie-only sources unless explicitly configured by the user.

## Mark Risk Notes

Add risk notes rather than discarding when an item is potentially useful but uncertain:

- `unverified_claim`
- `marketing_claim`
- `paywalled`
- `aggregated_source`
- `weak_timestamp`
- `translated_summary`

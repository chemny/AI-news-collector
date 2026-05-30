# AIHOT Integration Notes

Upstream skill repo: https://github.com/KKKKhazix/khazix-skills

Service: https://aihot.virxact.com

Use in this skill:

- Call the public AIHOT API directly.
- Do not require users to install `khazix-skills`.
- Keep the important API routing rules locally documented.

Rules:

- Always send a browser User-Agent to `/api/public/*`.
- Default broad collection uses selected items, not daily.
- Daily mode is only for the generated daily report.
- Items endpoint is naturally capped to recent data by the service; our collector additionally uses a 24-hour window.
- Keep source URLs when storing items.

Endpoints used:

- `/api/public/items`
- `/api/public/daily`

If we later self-host an AIHOT-compatible service, add a `base_url` config option and keep the same adapter contract.

Do not make users install `khazix-skills` separately.


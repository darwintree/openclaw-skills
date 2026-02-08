---
name: imas-portal-schedule
description: Fetch and summarize THE IDOLM@STER official portal (idolmaster-official.jp) SCHEDULE items via the Python package `imas-tools`. Use when the user asks to “查日程/查日历/查 schedule” for IM@S, especially for CD release schedules (subcategory=CD), and wants results for a time range (past month, next 7/30 days, specific dates) with event_url links.
---

# IM@S Portal Schedule (imas-tools)

Use `imas-tools` portal API to fetch SCHEDULE entries and filter for **CD**.

## Quick start (recommended)

Run via `uv` in an isolated env (no venv management):

- Past 30 days (JST):

```bash
uv run --isolated --with imas-tools==0.4.8 python skills/public/imas-portal-schedule/scripts/fetch_cd_schedule.py --past-days 30 --tz Asia/Tokyo
```

- Next 30 days (JST):

```bash
uv run --isolated --with imas-tools==0.4.8 python skills/public/imas-portal-schedule/scripts/fetch_cd_schedule.py --future-days 30 --past-days 0 --tz Asia/Tokyo
```

- Custom date range (YYYY-MM-DD in the given timezone):

```bash
uv run --isolated --with imas-tools==0.4.8 python skills/public/imas-portal-schedule/scripts/fetch_cd_schedule.py \
  --start-date 2026-01-08 --end-date 2026-02-07 --tz Asia/Tokyo
```

## Output rules

- Prefer `event_url`.
- If `event_url` exists, **do not print** portal URL fallback.
- If `event_url` is missing, print `url` (idolmaster-official.jp page) as the only link.

## Notes

- The underlying call uses `imas_tools.portal.article._fetch_schedule(...)` with `subcategories=["CD"]`.
- Time calculations are done in `--tz` (default `Asia/Tokyo`).

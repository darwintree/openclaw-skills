#!/usr/bin/env python3
"""Fetch IM@S Portal schedule items (category SCHEDULE) for CD releases.

Uses imas-tools portal API wrapper. Intended to be run via:
  uv run --isolated --with imas-tools==0.4.8 python scripts/fetch_cd_schedule.py --past-days 30

Behavior:
- Filters by subcategory=CD (Portal "listed_subcategories").
- Outputs event_url if present; otherwise outputs portal url.
- If event_url exists, DO NOT print portal url fallback.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import pytz

from imas_tools.portal.article import _fetch_schedule


def _pick_start(a: Dict[str, Any]) -> int:
    return int(a.get("event_startdate") or a.get("startdate") or 0)


def _pick_end(a: Dict[str, Any]) -> int:
    return int(a.get("event_enddate") or a.get("enddate") or 0)


def _brands_str(a: Dict[str, Any]) -> str:
    brands = a.get("brand") or []
    codes: List[str] = []
    for b in brands:
        if isinstance(b, dict) and b.get("code"):
            codes.append(str(b["code"]))
    return ",".join(codes)


def _fmt_ts(ts: int, tz) -> str:
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M")


def fetch(start: datetime, end: datetime, limit: int = 500) -> List[Dict[str, Any]]:
    resp = _fetch_schedule(start, end, brands=[], subcategories=["CD"], limit=limit)
    return list(resp.get("article_list") or [])


def render(items: List[Dict[str, Any]], tz_name: str) -> str:
    tz = pytz.timezone(tz_name)

    rows: List[Tuple[int, Dict[str, Any]]] = []
    for a in items:
        st = _pick_start(a)
        if st:
            rows.append((st, a))
    rows.sort(key=lambda x: x[0])

    out: List[str] = []
    for st, a in rows:
        en = _pick_end(a)
        title = (a.get("title") or "").strip()
        brand = _brands_str(a)
        event_url = (a.get("event_url") or "").strip()
        portal_url = (a.get("url") or "").strip()

        url = event_url if event_url else portal_url

        s = _fmt_ts(st, tz)
        e = _fmt_ts(en, tz) if en else ""
        when = s if not e else f"{s} ~ {e}"
        brand_part = f" ({brand})" if brand else ""

        out.append(f"- {when} | {title}{brand_part}")
        out.append(f"  {url}")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--past-days", type=int, default=30, help="Look back N days (default: 30)")
    ap.add_argument("--future-days", type=int, default=0, help="Look forward N days (default: 0)")
    ap.add_argument(
        "--start-date",
        default="",
        help="Override start date (YYYY-MM-DD) in --tz timezone",
    )
    ap.add_argument(
        "--end-date",
        default="",
        help="Override end date (YYYY-MM-DD) in --tz timezone",
    )
    ap.add_argument(
        "--tz",
        default="Asia/Tokyo",
        help="Timezone for date calculations and display (default: Asia/Tokyo)",
    )
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    tz = pytz.timezone(args.tz)
    now = datetime.now(tz)

    if args.start_date:
        y, m, d = (int(x) for x in args.start_date.split("-"))
        start = tz.localize(datetime(y, m, d, 0, 0, 0))
    else:
        start = (now - timedelta(days=args.past_days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if args.end_date:
        y, m, d = (int(x) for x in args.end_date.split("-"))
        end = tz.localize(datetime(y, m, d, 23, 59, 59))
    else:
        end = (now + timedelta(days=args.future_days)).replace(
            hour=23, minute=59, second=59, microsecond=0
        )

    items = fetch(start, end, limit=args.limit)
    header = (
        f"Range ({args.tz}): {start.strftime('%Y-%m-%d')}..{end.strftime('%Y-%m-%d')} | CD items: {len(items)}"
    )
    print(header)
    if items:
        print(render(items, args.tz))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

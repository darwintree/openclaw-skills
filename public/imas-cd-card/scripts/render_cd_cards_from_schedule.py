#!/usr/bin/env python3
"""Generate IM@S CD cards from Portal schedule (past N days), merge, and zip.

Workflow:
1) Use imas-tools portal SCHEDULE API to fetch subcategory=CD in a time range.
2) Prefer event_url; filter out YouTube (miscategorized items).
3) For each event_url, render a cd card PNG via render_cd_card.py.
4) Merge cards into a single tall PNG (single-column; preserves varying heights).
5) Create a ZIP containing the merged PNG (workaround for Telegram image downscaling).

Recommended run (uv isolated):
  uv run --isolated --with imas-tools==0.4.8 --with pytz --with pillow --with requests --with beautifulsoup4 --with qrcode \
    python scripts/render_cd_cards_from_schedule.py --past-days 14 --tz Asia/Tokyo --out-prefix cd_cards_past2w

Outputs:
  <out-prefix>_merged.png
  <out-prefix>_merged.zip
  <out-dir>/cards/*.png
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import os
import re
import zipfile
from urllib.parse import urlparse

import pytz
from PIL import Image, ImageDraw

from imas_tools.portal.article import _fetch_schedule

# Local import of renderer script (same folder)
import importlib.util


def load_renderer(path: str):
    spec = importlib.util.spec_from_file_location("render_cd_card", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def is_bad_event_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return ("youtube.com" in host) or ("youtu.be" in host)


def safe_name(url: str, max_len: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url)[:max_len]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--past-days", type=int, default=14, help="Look back N days (ignored if --start-date given)")
    ap.add_argument("--future-days", type=int, default=0, help="Look forward N days (ignored if --end-date given)")
    ap.add_argument("--start-date", default="", help="Start date YYYY-MM-DD in --tz")
    ap.add_argument("--end-date", default="", help="End date YYYY-MM-DD in --tz")
    ap.add_argument("--tz", default="Asia/Tokyo")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out-prefix", default="cd_cards")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument(
        "--font",
        default="/home/openclaw/.openclaw/workspace/assets/fonts/NotoSansCJKjp-Regular.otf",
    )
    ap.add_argument("--max-height", type=int, default=1500)
    ap.add_argument("--merge-width", type=int, default=1200, help="Keep merge at native card width to avoid blur")
    args = ap.parse_args()

    tz = pytz.timezone(args.tz)
    now = datetime.now(tz)

    if args.start_date:
        y, m, d = (int(x) for x in args.start_date.split("-"))
        start = tz.localize(datetime(y, m, d, 0, 0, 0))
    else:
        start = (now - timedelta(days=args.past_days)).replace(hour=0, minute=0, second=0, microsecond=0)

    if args.end_date:
        y, m, d = (int(x) for x in args.end_date.split("-"))
        end = tz.localize(datetime(y, m, d, 23, 59, 59))
    else:
        end = (now + timedelta(days=args.future_days)).replace(hour=23, minute=59, second=59, microsecond=0)

    resp = _fetch_schedule(start, end, brands=[], subcategories=["CD"], limit=args.limit)
    items = list(resp.get("article_list") or [])

    # Collect event_urls ordered by event start time
    entries = []
    for a in items:
        eu = (a.get("event_url") or "").strip()
        if not eu:
            continue
        if is_bad_event_url(eu):
            continue
        ts = int(a.get("event_startdate") or a.get("startdate") or 0)
        entries.append((ts, a.get("title", "").strip(), eu))
    entries.sort(key=lambda x: x[0])

    out_dir = os.path.abspath(args.out_dir)
    cards_dir = os.path.join(out_dir, f"{args.out_prefix}_cards")
    os.makedirs(cards_dir, exist_ok=True)

    renderer_path = os.path.join(os.path.dirname(__file__), "render_cd_card.py")
    renderer = load_renderer(renderer_path)

    card_paths: list[str] = []
    for i, (_, title, url) in enumerate(entries, start=1):
        out = os.path.join(cards_dir, f"{i:02d}_{safe_name(url)}.png")
        soup = renderer.fetch_release_page(url)
        info = renderer.parse_release_info(url, soup)
        renderer.render_card(url, info, args.font, out, w=args.merge_width, h=None, max_height=args.max_height)
        card_paths.append(out)
        print("ok", i, url)

    if not card_paths:
        print("no cards")
        return 0

    # Merge (single column, no scaling)
    cards = [Image.open(p).convert("RGB") for p in card_paths]
    w = max(im.size[0] for im in cards)
    pad = 30
    bg = (245, 245, 245)
    W = pad + w + pad
    H = pad + sum(im.size[1] for im in cards) + pad * (len(cards) - 1) + pad

    canvas = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(canvas)

    y = pad
    for im in cards:
        x = pad + (w - im.size[0]) // 2
        canvas.paste(im, (x, y))
        draw.rectangle([x, y, x + im.size[0], y + im.size[1]], outline=(220, 220, 220), width=2)
        y += im.size[1] + pad

    merged_png = os.path.join(out_dir, f"{args.out_prefix}_merged.png")
    canvas.save(merged_png, "PNG")

    merged_zip = os.path.join(out_dir, f"{args.out_prefix}_merged.zip")
    with zipfile.ZipFile(merged_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(merged_png, arcname=os.path.basename(merged_png))

    print("merged", merged_png, "size", canvas.size)
    print("zip", merged_zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

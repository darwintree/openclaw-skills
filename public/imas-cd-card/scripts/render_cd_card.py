#!/usr/bin/env python3
"""Render a compact IM@S CD info card into a single PNG.

Input: an event_url (typically Lantis release page)
Output: PNG with cover + metadata + tracklist/staff + QR + one-line URL.

Design targets (current iteration):
- Compact layout; omit catalog/price.
- Keep artist (CV) line; remove promotional description.
- QR under tracklist, left-aligned in right panel.
- URL must be a single line (no wrapping); shrink font to fit.

Run (recommended via uv):
  uv run --isolated --with pillow --with requests --with beautifulsoup4 --with qrcode \
    python scripts/render_cd_card.py --url <event_url> --out out.png
"""

from __future__ import annotations

import argparse
import re
from io import BytesIO
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import qrcode


# Track number formats vary by site:
# - Lantis IM@S pages: "01：Title" / "01:Title"
# - ShinyColors Lantis pages: "1．Title" (Japanese dot)
TRACK_RE = re.compile(r"^(?P<no>\d{1,2})\s*[：:.．]\s*(?P<title>.+)$")
STOP_RE = re.compile(r"^(text|-->|■)")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, maxw: int):
    out = []
    line = ""
    for ch in text:
        test = line + ch
        if draw.textlength(test, font=font) <= maxw:
            line = test
        else:
            if line:
                out.append(line)
            line = ch
    if line:
        out.append(line)
    return out


def fetch_release_page(url: str, timeout: int = 30) -> BeautifulSoup:
    # Some hosts (e.g. shinycolors.lantis.jp) return 403 without a browser-like User-Agent.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    html = requests.get(url, timeout=timeout, headers=headers).text
    return BeautifulSoup(html, "html.parser")


def parse_release_info(url: str, soup: BeautifulSoup):
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    def first_line(regex: str) -> str:
        for ln in lines:
            if re.search(regex, ln):
                return ln
        return ""

    # title
    h2 = soup.find("h2")
    title = h2.get_text(" ", strip=True) if h2 else ""
    if not title:
        for ln in lines:
            if "THE IDOLM@STER" in ln and "RELEASE" not in ln:
                title = ln
                break

    # release date
    # - Some pages use Japanese label: "発売日：YYYY/M/D"
    # - SideM Lantis pages often use: "YYYY.M.D RELEASE"
    release_date = ""
    release_ln = first_line(r"^発売日")
    if release_ln and "：" in release_ln:
        release_date = release_ln.split("：", 1)[1].strip()
    if not release_date:
        for ln in lines:
            m = re.match(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})\s+RELEASE\b", ln)
            if m:
                y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
                release_date = f"{y}/{mo}/{d}"
                break

    # artist line (keep)
    # - Many IM@S Lantis pages include a "CV." line
    # - ShinyColors release pages use "アーティスト：..."
    artists = ""
    for ln in lines:
        if "CV." in ln:
            artists = ln
            break
    if not artists:
        for ln in lines:
            if ln.startswith("アーティスト"):
                artists = ln
                break

    # cover (lantis pages usually have div.release_img img)
    cover_src = None
    main_img = soup.select_one("div.release_img img")
    if main_img and main_img.get("src"):
        cover_src = main_img["src"]
    cover_url = urljoin(url, cover_src) if cover_src else None

    # tracklist + staff (heuristic: staff lines follow track and contain 作詞/作曲/編曲)
    tracks = []
    cur = None
    for ln in lines:
        m = TRACK_RE.match(ln)
        if m:
            if cur:
                tracks.append(cur)
            no = m.group("no")
            title_part = m.group("title").strip()
            cur = {"no": f"{int(no):02d}", "title": title_part, "staff": []}
            continue
        if not cur:
            continue
        if STOP_RE.match(ln):
            continue
        if "作詞" in ln or "作曲" in ln or "編曲" in ln:
            cur["staff"].append(ln)
    if cur:
        tracks.append(cur)

    return {
        "title": title,
        "release_date": release_date,
        "artists": artists,
        "cover_url": cover_url,
        "tracks": tracks,
    }


def fetch_image(url: str, timeout: int = 30) -> Image.Image:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


def make_qr(url: str, size: int = 190) -> Image.Image:
    qr = qrcode.QRCode(border=1, box_size=6)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((size, size))


def fit_one_line_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    maxw: int,
    start_size: int = 20,
    min_size: int = 12,
):
    size = start_size
    while size >= min_size:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= maxw:
            return f
        size -= 1
    return ImageFont.truetype(font_path, min_size)


def _estimate_height(
    draw: ImageDraw.ImageDraw,
    info: dict,
    font_title: ImageFont.FreeTypeFont,
    font_date: ImageFont.FreeTypeFont,
    font_body: ImageFont.FreeTypeFont,
    font_small: ImageFont.FreeTypeFont,
    font_staff: ImageFont.FreeTypeFont,
    w: int,
    pad: int,
    left_w: int,
    max_height: int,
    qr_size: int,
) -> int:
    """Estimate needed canvas height for current content.

    We keep the left panel cover size fixed (square: left_w-40).
    Right panel height grows with track count + staff.
    """

    right_x = pad + left_w + 30
    right_w = w - right_x - pad

    # Top blocks
    y = pad + 18

    artists = info.get("artists", "") or ""
    if artists:
        y += len(_wrap(draw, artists, font_small, right_w - 40)[:2]) * (font_small.size + 3)
        y += 8

    # header
    y += font_body.size + 8

    # tracks
    for t in info.get("tracks", []) or []:
        # main line: we render 1 line
        y += font_body.size + 2
        # staff: up to 2 wrapped lines
        if t.get("staff"):
            staff = " / ".join(t["staff"])
            y += len(_wrap(draw, staff, font_staff, right_w - 60)[:2]) * (font_staff.size + 2)
        y += 8

    # QR + URL
    y += 18 + qr_size + 8
    y += font_small.size + 10

    # Bottom padding
    y += pad

    # Minimum height: must fit left panel content (date+title+cover)
    left_min = pad + 18
    if info.get("release_date"):
        left_min += len(_wrap(draw, f"発売日：{info['release_date']}", font_date, left_w - 40)) * (font_date.size + 6)
    left_min += len(_wrap(draw, info.get("title", ""), font_title, left_w - 40)) * (font_title.size + 4)
    left_min += 10 + (left_w - 40) + pad  # cover + spacing + bottom

    # "wrap content": do not force a fixed minimum beyond what's needed.
    need = max(y, left_min)
    return min(max_height, need)


def render_card(
    event_url: str,
    info: dict,
    font_path: str,
    out_path: str,
    w: int = 1200,
    h: int | None = None,
    max_height: int = 1500,
):
    # We'll decide height dynamically if not provided.
    # Fonts are needed for measurement.
    pad = 30
    left_w = 430
    qr_size = 190

    font_date = ImageFont.truetype(font_path, 30)
    font_title = ImageFont.truetype(font_path, 34)
    font_body = ImageFont.truetype(font_path, 26)
    font_small = ImageFont.truetype(font_path, 20)
    font_staff = ImageFont.truetype(font_path, 22)

    # Temporary draw for measurement
    tmp = Image.new("RGB", (w, 10), (0, 0, 0))
    tmp_draw = ImageDraw.Draw(tmp)

    if h is None:
        h = _estimate_height(
            tmp_draw,
            info,
            font_title,
            font_date,
            font_body,
            font_small,
            font_staff,
            w=w,
            pad=pad,
            left_w=left_w,
            max_height=max_height,
            qr_size=qr_size,
        )
    else:
        h = min(max_height, h)

    img = Image.new("RGB", (w, h), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    # fonts already prepared above

    right_x = pad + left_w + 30
    right_w = w - right_x - pad

    panel = (255, 255, 255)
    draw.rounded_rectangle(
        [pad, pad, pad + left_w, h - pad],
        radius=18,
        fill=panel,
        outline=(225, 225, 225),
        width=2,
    )
    draw.rounded_rectangle(
        [right_x, pad, w - pad, h - pad],
        radius=18,
        fill=panel,
        outline=(225, 225, 225),
        width=2,
    )

    # left: date + title + cover
    x = pad + 20
    y = pad + 18

    if info.get("release_date"):
        for ln in _wrap(draw, f"発売日：{info['release_date']}", font_date, left_w - 40):
            draw.text((x, y), ln, font=font_date, fill=(60, 60, 60))
            y += font_date.size + 6

    for ln in _wrap(draw, info.get("title", ""), font_title, left_w - 40):
        draw.text((x, y), ln, font=font_title, fill=(20, 20, 20))
        y += font_title.size + 4

    y += 10
    cover_box = [pad + 20, y, pad + left_w - 20, y + (left_w - 40)]
    if info.get("cover_url"):
        cover = fetch_image(info["cover_url"])
        ci = cover.copy()
        ci.thumbnail((left_w - 40, left_w - 40))
        cx = cover_box[0] + ((left_w - 40) - ci.size[0]) // 2
        cy = cover_box[1] + ((left_w - 40) - ci.size[1]) // 2
        img.paste(ci, (cx, cy))
    draw.rectangle(cover_box, outline=(210, 210, 210), width=2)

    # right: artists + tracklist + QR + one-line URL
    rx = right_x + 20
    ry = pad + 18

    artists = info.get("artists", "")
    if artists:
        for ln in _wrap(draw, artists, font_small, right_w - 40)[:2]:
            draw.text((rx, ry), ln, font=font_small, fill=(50, 50, 50))
            ry += font_small.size + 3
        ry += 8

    draw.text((rx, ry), "曲目 / Staff", font=font_body, fill=(10, 10, 10))
    ry += font_body.size + 8

    for t in info.get("tracks", []):
        main = f"{t['no']} {t['title']}"
        draw.text(
            (rx, ry),
            _wrap(draw, main, font_body, right_w - 40)[0],
            font=font_body,
            fill=(30, 30, 30),
        )
        ry += font_body.size + 2

        if t.get("staff"):
            staff = " / ".join(t["staff"])
            for ln in _wrap(draw, staff, font_staff, right_w - 60)[:2]:
                draw.text((rx + 20, ry), ln, font=font_staff, fill=(95, 95, 95))
                ry += font_staff.size + 2
        ry += 8

    qr_img = make_qr(event_url, size=qr_size)
    qr_x = rx
    qr_y = ry + 18

    # If we hit max_height, track list may overflow into the QR area.
    # In that case, truncate and add a "…" marker.
    qr_top_limit = qr_y
    if qr_top_limit < (pad + 18):
        qr_top_limit = pad + 18

    if qr_y + qr_size + 8 + font_small.size + pad > h - pad:
        # move QR to bottom area if even the base computation was too small
        qr_y = h - pad - qr_size - 8 - font_small.size

    # If tracklist already went beyond where QR should start, mark truncation.
    if ry > qr_y:
        draw.text((rx, qr_y - (font_small.size + 6)), "……（曲目过多，已截断）", font=font_small, fill=(110, 110, 110))

    img.paste(qr_img, (qr_x, qr_y))
    draw.rectangle([qr_x, qr_y, qr_x + qr_size, qr_y + qr_size], outline=(210, 210, 210), width=2)

    url_y = qr_y + qr_size + 8
    url_font = fit_one_line_font(draw, event_url, font_path, maxw=right_w - 40, start_size=20, min_size=12)
    draw.text((rx, url_y), event_url, font=url_font, fill=(80, 80, 80))

    img.save(out_path, "PNG")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="CD event_url (e.g. Lantis release page)")
    ap.add_argument("--out", required=True, help="Output PNG path")
    ap.add_argument(
        "--font",
        default="/home/openclaw/.openclaw/workspace/assets/fonts/NotoSansCJKjp-Regular.otf",
        help="Font path (needs CJK support)",
    )
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument(
        "--height",
        type=int,
        default=0,
        help="Fixed canvas height. If 0, auto-grow up to --max-height.",
    )
    ap.add_argument("--max-height", type=int, default=1500, help="Max auto height (default: 1500)")
    args = ap.parse_args()

    soup = fetch_release_page(args.url)
    info = parse_release_info(args.url, soup)
    fixed_h = args.height if args.height and args.height > 0 else None
    render_card(
        args.url,
        info,
        args.font,
        args.out,
        w=args.width,
        h=fixed_h,
        max_height=args.max_height,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

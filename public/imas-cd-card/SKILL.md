---
name: imas-cd-card
description: Generate a compact single-image “CD card” for IM@S releases by fetching details from a CD event_url (typically Lantis) and composing cover + release date + title + artist line + tracklist with staff + QR code and one-line URL using Pillow. Use when the user asks to turn a CD link into an image, make a shareable CD info picture, include QR code, or wants a compact layout.
---

# IM@S CD Card Image (Pillow)

Create a **single PNG** that combines CD info into a compact layout.

## What it does

Given an `event_url` (e.g. `https://www.lantis.jp/.../release_XXXX.html`), fetch:
- Release date
- CD title
- Artist line (the line containing `CV.`)
- Tracklist + per-track staff (lines containing `作詞/作曲/編曲` that follow each track)
- Cover image

Then render:
- **Left panel**: 発売日 + タイトル + 封面
- **Right panel**: artist line + tracklist/staff + QR code (under tracklist, left-aligned) + **URL in one line** (auto-shrink font to fit)

## Run

Use `uv` to run without managing a venv:

### Render one CD card from an event_url

```bash
uv run --isolated \
  --with pillow --with requests --with beautifulsoup4 --with qrcode \
  python skills/public/imas-cd-card/scripts/render_cd_card.py \
  --url "https://www.lantis.jp/imas/release_LACM-24714.html" \
  --out cd_card.png \
  --max-height 1500
```

### Batch: user-specified date range from Portal schedule → cards → merged PNG + merged ZIP

By relative range:

```bash
uv run --isolated \
  --with imas-tools==0.4.8 --with pytz \
  --with pillow --with requests --with beautifulsoup4 --with qrcode \
  python skills/public/imas-cd-card/scripts/render_cd_cards_from_schedule.py \
  --past-days 14 --future-days 0 --tz Asia/Tokyo \
  --out-prefix cd_cards --out-dir . \
  --max-height 1500
```

By explicit dates:

```bash
uv run --isolated \
  --with imas-tools==0.4.8 --with pytz \
  --with pillow --with requests --with beautifulsoup4 --with qrcode \
  python skills/public/imas-cd-card/scripts/render_cd_cards_from_schedule.py \
  --start-date 2026-01-25 --end-date 2026-02-07 --tz Asia/Tokyo \
  --out-prefix cd_cards --out-dir . \
  --max-height 1500
```

Outputs:
- `<out-prefix>_merged.png` (for chat preview)
- `<out-prefix>_merged.zip` (always preserves original PNG for Telegram)
- `<out-prefix>_cards/*.png` (per-album cards)

## Layout rules (current iteration)

- Keep layout compact; omit catalog/price.
- Keep the **artist line** (CV. / アーティスト：...), remove promotional description.
- QR code appears **below the tracklist**, aligned to the **left** of the right panel.
- Print the URL as **one single line** (no wrapping/folding). If it doesn’t fit, shrink font size down to a minimum.
- Height is **wrap-content** (auto-grow/shrink) with an upper bound `--max-height` (default 1500).

## Notes

- `shinycolors.lantis.jp` may return 403 without a browser-like User-Agent; the script sets one.
- Telegram can downscale images even when sent as a file; the batch script always produces a ZIP as a reliable workaround.
- If the host lacks CJK fonts, install/bundle a font (e.g., Noto Sans CJK) and pass `--font`.

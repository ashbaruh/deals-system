"""Own 1000x1500 Pinterest images for the RSS feeds (Pinterest skips re-used AliExpress photos).

Runs after the site build:  python -m webgen.pins
Reads public/{lang}/pins.json (written by webgen.build), renders public/pins/{lang}/{id}.jpg and
points that item's image in public/{lang}/feed.xml at it. An item whose image fails keeps the original.
Needs: pillow, python-bidi.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
FONT = Path(__file__).with_name("Rubik.ttf")
BASE = "https://dealim.net"
W, H = 1000, 1500
RED, INK, PAPER, MUTED = "#d0001b", "#1d1d1f", "#fff4ec", "#6b6b70"
TXT = {
    "he": {"now": "עכשיו", "was": "במקום", "tag": "דיל שנבדק מול מחיר 30 יום", "rtl": True},
    "es": {"now": "Ahora", "was": "Antes", "tag": "Precio comprobado vs. 30 días", "rtl": False},
    "en": {"now": "Now", "was": "Was", "tag": "Checked against its 30-day price", "rtl": False},
}


def font(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size, layout_engine=ImageFont.Layout.BASIC)   # we do bidi ourselves: same result with or without libraqm
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def vis(s: str, rtl: bool) -> str:
    if not rtl:
        return s
    from bidi.algorithm import get_display
    return get_display(s, base_dir="R")


def wrap(dr, text, f, width, lines):
    words, out, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=f) <= width:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        while out[-1] and dr.textlength(out[-1] + "…", font=f) > width:
            out[-1] = out[-1][:-1]
        out[-1] = out[-1].rstrip() + "…"
    return out


def render(item: dict, lang: str, photo: Image.Image) -> Image.Image:
    t, rtl = TXT[lang], TXT[lang]["rtl"]
    im = Image.new("RGB", (W, H), PAPER)
    dr = ImageDraw.Draw(im)
    # header band
    dr.rectangle((0, 0, W, 110), fill=RED)
    dr.text((W // 2, 55), "dealim.net", font=font(54, 800), fill="white", anchor="mm")
    # product photo on a white card
    dr.rounded_rectangle((50, 150, W - 50, 1010), radius=36, fill="white")
    ph = ImageOps.contain(photo.convert("RGB"), (840, 800))
    im.paste(ph, ((W - ph.width) // 2, 150 + (860 - ph.height) // 2))
    # discount badge
    if item.get("pct"):
        dr.ellipse((W - 290, 90, W - 40, 340), fill=RED)
        dr.text((W - 165, 215), f"-{item['pct']}%", font=font(72, 900), fill="white", anchor="mm")
    # title (2 lines)
    ft = font(50, 700)
    y = 1050
    for ln in wrap(dr, item["title"], ft, W - 120, 2):
        dr.text((W // 2, y), vis(ln, rtl), font=ft, fill=INK, anchor="mt")
        y += 64
    # prices
    y = max(y + 20, 1200)
    now = f"{t['now']} {item['now']}"
    dr.text((W // 2, y), vis(now, rtl), font=font(96, 900), fill=RED, anchor="mt")
    if item.get("was"):
        was = f"{t['was']} {item['was']}"
        fw = font(48, 500)
        dr.text((W // 2, y + 120), vis(was, rtl), font=fw, fill=MUTED, anchor="mt")
        tw = dr.textlength(vis(was, rtl), font=fw)
        dr.line((W // 2 - tw / 2, y + 146, W // 2 + tw / 2, y + 146), fill=MUTED, width=4)
    # footer
    dr.rectangle((0, H - 90, W, H), fill=INK)
    dr.text((W // 2, H - 45), vis(t["tag"], rtl), font=font(38, 500), fill="white", anchor="mm")
    return im


def fetch(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read()))


def main() -> int:
    made = 0
    for lang in TXT:
        meta_f, feed_f = PUB / lang / "pins.json", PUB / lang / "feed.xml"
        if not meta_f.exists() or not feed_f.exists():
            continue
        feed = feed_f.read_text(encoding="utf-8")
        out = PUB / "pins" / lang
        out.mkdir(parents=True, exist_ok=True)
        for it in json.loads(meta_f.read_text(encoding="utf-8")):
            try:
                render(it, lang, fetch(it["image"])).save(out / f"{it['id']}.jpg", "JPEG", quality=88)
            except Exception as e:
                print(f"pin {lang} {it['id']}: {e}")
                continue
            new = f"{BASE}/pins/{lang}/{it['id']}.jpg"
            feed = feed.replace(it["image"].replace("&", "&amp;amp;"), new).replace(it["image"].replace("&", "&amp;"), new).replace(it["image"], new)
            made += 1
        feed_f.write_text(feed, encoding="utf-8")
        meta_f.unlink()
    print(f"pins: {made} images")
    return 0


if __name__ == "__main__":
    sys.exit(main())

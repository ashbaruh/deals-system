"""Daily "3 deals of the day" short (9:16) per language, picked automatically.

    python -m video.daily es en   -> out/daily_video_{lang}.mp4 + out/daily_cover_{lang}.png
Picks today's strongest deals (big real discount, good price, three different categories).
On-screen links use the per-platform short pages (dealim.net/tt etc.) so clicks are measurable.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from . import make
from .make import OUT, ROOT, TMP, money, page

TXT = {
    "he": dict(top="3 דילים של היום", hook="3 דילים מאלי אקספרס<br>שבאמת שווים היום", sub="המחירים נבדקו מול 30 יום",
               now="עכשיו", was="במקום", cta1="עוד דילים כל יום", tg="@mivtzaim_kuponim"),
    "es": dict(top="3 CHOLLOS DE HOY", hook="3 chollos de AliExpress<br>que merecen la pena hoy", sub="Precios comprobados (30 días)",
               now="Ahora", was="Antes", cta1="Más chollos cada día", tg="@ofertas_descuentos_es"),
    "en": dict(top="TODAY'S TOP 3", hook="3 AliExpress deals<br>actually worth it today", sub="Prices checked vs 30-day history",
               now="Now", was="Was", cta1="New deals every day", tg="@discount_deals_promo"),
}
SITE = os.environ.get("SITE_TAG", "dealim.net/tt")
BAD = ("toyota", "honda", "bmw", "for 20", "custom fit", "sexy", "reborn", "doll", "underwear", "panties", "bra ",
       "lingerie", "trolley", "barber", "wig", "ropa interior", " case", "funda", "cover")
PREF = ["brands", "audio", "tech", "coffee", "appliances", "home", "tools", "sports", "shoes", "fashion", "kids"]


def pick(lang, n=3):
    deals = json.loads((ROOT / "data" / f"deals_{lang}.json").read_text(encoding="utf-8"))
    deals = [d for d in deals if d.get("image") and 12 <= d["price_usd"] <= 120 and d.get("discount", 0) >= 0.5
             and d.get("niche") not in ("dollar",) and not any(b in d["title"].lower() for b in BAD)]
    newest = max((d.get("day", "") for d in deals), default="")
    fresh = [d for d in deals if d.get("day", "") >= newest[:8]] or deals     # this month's picks first
    out = []
    for niche in PREF:
        cand = sorted((d for d in fresh if d.get("niche") == niche), key=lambda d: -d["discount"] * min(d["price_usd"], 80))
        if cand:
            out.append(cand[0])
        if len(out) == n:
            break
    return out


def slides(lang):
    t = TXT[lang]
    ds = pick(lang)
    imgs = []
    for d in ds:
        img = TMP / (d["pid"].split(":")[1] + ".jpg")
        if not img.exists():
            req = urllib.request.Request(d["image"], headers={"User-Agent": "Mozilla/5.0"})
            img.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        imgs.append(img)
    thumbs = "".join(f'<img src="{i.as_uri()}">' for i in imgs)
    out = [(page(lang, f'<div class="top"><span class="pill">{t["top"]}</span></div>'
                       f'<div class="hook"><div class="mid" style="font-size:100px">{t["hook"]}</div>'
                       f'<div class="sm">{t["sub"]} ✅</div></div><div class="thumbs">{thumbs}</div>'), 2.6)]
    for i, (d, img) in enumerate(zip(ds, imgs), 1):
        import re
        name = re.sub(r"^\s*(\d+[- ]hour delivery|new|hot|original|20\d\d)\s+", "", d.get("title_local") or d["title"], flags=re.I)
        name = name if len(name) <= 46 else name[:44].rsplit(" ", 1)[0] + "…"
        out.append((page(lang,
            f'<div class="top"><span class="pill">{t["top"]}</span></div>'
            f'<div class="card"><img src="{img.as_uri()}"></div>'
            f'<div class="off"><bdi>-{round(d["discount"] * 100)}%</bdi></div>'
            f'<div class="title">{name}</div>'
            f'<div class="price">{t["now"]} <b><bdi>{money(d["price_usd"], lang)}</bdi></b><br>'
            f'{t["was"]} <s><bdi>{money(d["median_30d"], lang)}</bdi></s></div>'
            f'<div class="n">{i}/3 · {SITE}</div>'), 3.0))
    out.append((page(lang,
        f'<div class="top"><span class="pill">{t["top"]}</span></div>'
        f'<div class="cta"><div class="mid">{t["cta1"]} 🔥</div>'
        f'<div class="tgbox"><small>Telegram</small><span dir="ltr">{t["tg"]}</span></div>'
        f'<div class="site">{SITE}</div></div>'), 3.4))
    (OUT / f"daily_picks_{lang}.json").write_text(json.dumps(
        [{"title": d.get("title_local") or d["title"], "slug": d["slug"], "pct": round(d["discount"] * 100),
          "price": money(d["price_usd"], lang)} for d in ds], ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright
    TMP.mkdir(parents=True, exist_ok=True)
    make.SLIDES_FN = slides
    make.PREFIX = "daily_"
    with sync_playwright() as pw:
        for lang in sys.argv[1:] or ["es", "en"]:
            make.render(lang, pw)
    return 0


if __name__ == "__main__":
    sys.exit(main())

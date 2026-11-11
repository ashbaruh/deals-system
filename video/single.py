"""One-product promo: 9:16 video + 4:5 image per language.

    PID=aliexpress:123 python -m video.single he es en
Output: out/one_video_{lang}.mp4, out/one_post_{lang}.png
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from . import make
from .make import CSS, H, OUT, ROOT, TMP, W, money, page

TXT = {
    "he": dict(top="דיל חם 🔥", now="עכשיו", was="במקום", cta="עוד דילים כל יום", tg="@mivtzaim_kuponim",
               hook="{name}<br>ב-{price} בלבד?"),
    "es": dict(top="OFERTA 🔥", now="Ahora", was="Antes", cta="Más ofertas cada día", tg="@ofertas_descuentos_es",
               hook="¿{name}<br>por solo {price}?"),
    "en": dict(top="HOT DEAL 🔥", now="Now", was="Was", cta="New deals every day", tg="@discount_deals_promo",
               hook="{name}<br>for just {price}?"),
}
NAME = json.loads(os.environ.get("NAMES", "{}"))


def _deal(lang):
    pid = os.environ["PID"]
    d = next(a for a in json.loads((ROOT / "data" / f"deals_{lang}.json").read_text(encoding="utf-8")) if a["pid"] == pid)
    img = TMP / (pid.split(":")[1] + ".jpg")
    if not img.exists():
        req = urllib.request.Request(d["image"], headers={"User-Agent": "Mozilla/5.0"})
        img.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    return d, img


def product_html(lang, d, img, t):
    pct = round(d["discount"] * 100)
    name = NAME.get(lang) or d.get("title_local") or d["title"]
    return (f'<div class="top"><span class="pill">{t["top"]}</span></div>'
            f'<div class="card"><img src="{img.as_uri()}"></div>'
            f'<div class="off"><bdi>-{pct}%</bdi></div>'
            f'<div class="title">{name}</div>'
            f'<div class="price">{t["now"]} <b><bdi>{money(d["price_usd"], lang)}</bdi></b><br>'
            f'{t["was"]} <s><bdi>{money(d["median_30d"], lang)}</bdi></s></div>'
            f'<div class="n">dealim.net</div>')


def single_slides(lang):
    t = TXT[lang]
    d, img = _deal(lang)
    name = NAME.get(lang) or d.get("title_local") or d["title"]
    hook = t["hook"].format(name=name, price=f'<bdi>{money(d["price_usd"], lang)}</bdi>')
    return [
        (page(lang, f'<div class="top"><span class="pill">{t["top"]}</span></div>'
                    f'<div class="hook" style="top:420px"><div class="mid" style="font-size:104px">{hook}</div></div>'
                    f'<div class="thumbs" style="top:1150px"><img style="width:560px;height:560px" src="{img.as_uri()}"></div>'), 2.4),
        (page(lang, product_html(lang, d, img, t)), 4.2),
        (page(lang, f'<div class="top"><span class="pill">{t["top"]}</span></div>'
                    f'<div class="cta"><div class="mid">{t["cta"]} 🔥</div>'
                    f'<div class="tgbox"><small>Telegram</small><span dir="ltr">{t["tg"]}</span></div>'
                    f'<div class="site">dealim.net</div></div>'), 3.0),
    ]


def post_image(lang, pw):
    """4:5 still (1080x1350) for Instagram / Pinterest: product slide squeezed."""
    t = TXT[lang]
    d, img = _deal(lang)
    css = CSS.replace("height:1920px", "height:1350px")
    html_ = page(lang, product_html(lang, d, img, t)).replace(CSS, css + """
.top{top:50px}.card{top:200px;left:220px;width:640px;height:640px}.off{top:770px;font-size:140px}
.title{top:960px;font-size:52px}.price{top:1090px;font-size:44px;line-height:1.15}.price b{font-size:72px}.n{bottom:22px;font-size:34px}""")
    f = TMP / f"one_post_{lang}.html"
    f.write_text(html_, encoding="utf-8")
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": 1350})
    pg.goto(f.as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
    pg.screenshot(path=str(OUT / f"one_post_{lang}.png"))
    b.close()


def main() -> int:
    from playwright.sync_api import sync_playwright
    TMP.mkdir(parents=True, exist_ok=True)
    make.SLIDES_FN = single_slides
    make.PREFIX = "one_"
    with sync_playwright() as pw:
        for lang in sys.argv[1:] or ["he", "es", "en"]:
            make.render(lang, pw)
            post_image(lang, pw)
    return 0


if __name__ == "__main__":
    sys.exit(main())

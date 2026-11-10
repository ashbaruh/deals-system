"""Render a 9:16 promo video (MP4) per language from deals in data/deals_{lang}.json.

Runs on the GitHub runner (needs internet for product images + Google Fonts):
    python -m video.make he es en
Output: out/video_{lang}.mp4 and out/cover_{lang}.png
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from webgen.build import LANGS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
TMP = ROOT / "out" / "tmp"
W, H, FPS = 1080, 1920, 30

PIDS = [  # (pid, short titles he/es/en)
    ("aliexpress:1005005286149243", "כפכפי ענן רכים במיוחד", "Chanclas nube ultrasuaves", "Ultra-soft cloud slides"),
    ("aliexpress:1005012173196854", "מתנע לרכב + משאבת צמיגים", "Arrancador de coche + compresor", "Car jump starter + tire pump"),
    ("aliexpress:1005013478258500", "מטחנת קפה ידנית מפלדה", "Molinillo de café manual de acero", "Steel burr coffee grinder"),
    ("aliexpress:1005012883649734", "אוזניות Open-Ear בלוטות' 5.4", "Auriculares open-ear Bluetooth 5.4", "Open-ear Bluetooth 5.4 earbuds"),
    ("aliexpress:1005013506901092", "שעון קיר LED עם טמפרטורה", "Reloj LED de pared con temperatura", "LED wall clock with temperature"),
    ("aliexpress:1005013448328016", "ווים בוואקום, בלי קידוח", "Ganchos de ventosa sin taladrar", "No-drill suction hooks"),
]
TXT = {
    "he": dict(top="11.11 מחר!", hook="6 דילים מאלי אקספרס<br>עד 70% הנחה", sub="בדקנו את המחירים בשבילכם",
               now="עכשיו", was="במקום", bonus="בונוס", cta1="דילים חדשים כל יום", tg="@mivtzaim_kuponim", off="הנחה"),
    "es": dict(top="¡11.11 es MAÑANA!", hook="6 chollos de AliExpress<br>hasta -70%", sub="Precios comprobados",
               now="Ahora", was="Antes", bonus="BONUS", cta1="Ofertas nuevas cada día", tg="@ofertas_descuentos_es", off="dto."),
    "en": dict(top="11.11 is TOMORROW!", hook="6 AliExpress deals<br>up to 70% off", sub="Prices checked for you",
               now="Now", was="Was", bonus="BONUS", cta1="New deals every day", tg="@discount_deals_promo", off="off"),
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@500;700;900&display=block');
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1920px;overflow:hidden;font-family:Rubik,sans-serif;color:#fff;
 background:radial-gradient(120% 80% at 50% 0%,#ff8a00 0%,#ff3b30 55%,#b3121f 100%)}
.top{position:absolute;top:90px;left:0;right:0;text-align:center}
.pill{display:inline-block;background:#fff;color:#e0241b;font-weight:900;font-size:64px;padding:14px 44px;border-radius:70px}
.card{position:absolute;top:270px;left:90px;width:900px;height:900px;background:#fff;border-radius:48px;overflow:hidden;
 box-shadow:0 30px 80px rgba(80,0,0,.35)}
.card img{width:100%;height:100%;object-fit:contain}
.off{position:absolute;top:1080px;left:50%;transform:translateX(-50%) rotate(-4deg);background:#ffe600;color:#c4120c;
 font-weight:900;font-size:190px;line-height:1;padding:18px 54px;border-radius:36px;white-space:nowrap;box-shadow:0 20px 50px rgba(0,0,0,.3)}
.title{position:absolute;top:1360px;left:60px;right:60px;text-align:center;font-weight:700;font-size:66px;line-height:1.15}
.price{position:absolute;top:1520px;line-height:1.25;left:0;right:0;text-align:center;font-size:58px;font-weight:500}
.price b{font-size:96px;font-weight:900}
.price s{opacity:.8}
.n{position:absolute;bottom:70px;left:0;right:0;text-align:center;font-size:40px;opacity:.85;font-weight:700}
.hook{position:absolute;top:330px;left:50px;right:50px;text-align:center}
.hook .big{font-size:150px;font-weight:900;line-height:1.02}
.hook .mid{font-size:92px;font-weight:900;line-height:1.1;margin-top:60px}
.hook .sm{font-size:56px;font-weight:500;margin-top:50px;opacity:.95}
.cta{position:absolute;top:520px;left:50px;right:50px;text-align:center}
.cta .mid{font-size:96px;font-weight:900;line-height:1.1}
.tgbox{margin:80px auto 0;background:#fff;color:#1b6fd1;font-weight:900;font-size:62px;padding:34px 30px;border-radius:40px;width:960px}
.tgbox small{display:block;color:#555;font-size:44px;font-weight:500;margin-bottom:10px}
.thumbs{position:absolute;top:1330px;left:60px;right:60px;display:flex;gap:30px;justify-content:center}
.thumbs img{width:300px;height:300px;object-fit:contain;background:#fff;border-radius:32px;box-shadow:0 20px 50px rgba(80,0,0,.3)}
.site{margin-top:60px;font-size:78px;font-weight:900}
"""


def money(usd: float, lang: str) -> str:
    c = LANGS[lang]
    v = usd * c["currency_rate_from_usd"]
    return f"{v:,.2f} {c['currency']}" if lang == "he" else f"{c['currency']}{v:,.2f}"


def page(lang: str, body: str) -> str:
    d = "rtl" if lang == "he" else "ltr"
    return f'<!doctype html><html lang="{lang}" dir="{d}"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'


def slides(lang: str) -> list[tuple[str, float]]:
    t = TXT[lang]
    deals = {d["pid"]: d for d in json.loads((ROOT / "data" / f"deals_{lang}.json").read_text(encoding="utf-8"))}
    li = {"he": 1, "es": 2, "en": 3}[lang]
    imgs = []
    for row in PIDS:
        img = TMP / (row[0].split(":")[1] + ".jpg")
        if not img.exists():
            req = urllib.request.Request(deals[row[0]]["image"], headers={"User-Agent": "Mozilla/5.0"})
            img.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        imgs.append(img)
    thumbs = "".join(f'<img src="{i.as_uri()}">' for i in imgs[:3])
    out = [(page(lang, f'<div class="top"><span class="pill">{t["top"]}</span></div>'
                       f'<div class="hook"><div class="big">11.11</div><div class="mid">{t["hook"]}</div>'
                       f'<div class="sm">{t["sub"]} ✅</div></div><div class="thumbs">{thumbs}</div>'), 2.6)]
    for i, row in enumerate(PIDS, 1):
        d = deals[row[0]]
        img = imgs[i - 1]
        pct = round(d["discount"] * 100)
        last = i == len(PIDS)
        label = f'{t["bonus"]} 🎁' if last else f"{i}/{len(PIDS) - 1}"
        out.append((page(lang,
            f'<div class="top"><span class="pill">{t["top"]}</span></div>'
            f'<div class="card"><img src="{img.as_uri()}"></div>'
            f'<div class="off"><bdi>-{pct}%</bdi></div>'
            f'<div class="title">{row[li]}</div>'
            f'<div class="price">{t["now"]} <b><bdi>{money(d["price_usd"], lang)}</bdi></b><br>'
            f'{t["was"]} <s><bdi>{money(d["median_30d"], lang)}</bdi></s></div>'
            f'<div class="n">{label}</div>'), 2.4))
    out.append((page(lang,
        f'<div class="top"><span class="pill">{t["top"]}</span></div>'
        f'<div class="cta"><div class="mid">{t["cta1"]} 🔥</div>'
        f'<div class="tgbox"><small>Telegram</small>{t["tg"]}</div>'
        f'<div class="site">dealim.net</div></div>'), 3.2))
    return out


def render(lang: str, pw) -> Path:
    from math import ceil
    sl = slides(lang)
    browser = pw.chromium.launch()
    pg = browser.new_page(viewport={"width": W, "height": H})
    pngs = []
    for i, (html_, _) in enumerate(sl):
        f = TMP / f"{lang}_{i}.html"
        f.write_text(html_, encoding="utf-8")
        pg.goto(f.as_uri())
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        png = TMP / f"{lang}_{i}.png"
        pg.screenshot(path=str(png))
        pngs.append(png)
    browser.close()
    (OUT / f"cover_{lang}.png").write_bytes(pngs[0].read_bytes())

    xf = 0.35  # crossfade seconds
    inputs, filt = [], []
    for i, (png, (_, dur)) in enumerate(zip(pngs, sl)):
        n = ceil(dur * FPS)
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(png)]
        filt.append(f"[{i}:v]scale={W * 2}:{H * 2},zoompan=z='min(zoom+0.0009,1.07)':x='iw/2-(iw/zoom/2)':"
                    f"y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[v{i}]")
    prev, t = "v0", sl[0][1]
    for i in range(1, len(pngs)):
        filt.append(f"[{prev}][v{i}]xfade=transition=slideleft:duration={xf}:offset={t - xf:.2f}[x{i}]")
        prev, t = f"x{i}", t + sl[i][1] - xf
    mp4 = OUT / f"video_{lang}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-f", "lavfi", "-t", f"{t:.2f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-filter_complex", ";".join(filt), "-map", f"[{prev}]", "-map", f"{len(pngs)}:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    print(f"{lang}: {mp4} {t:.1f}s", flush=True)
    return mp4


def main() -> int:
    from playwright.sync_api import sync_playwright
    TMP.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        for lang in sys.argv[1:] or ["he", "es", "en"]:
            render(lang, pw)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""10-minute 16:9 "live deals" video for a YouTube live stream + numbered short links.

    python -m video.live en
Writes:
  out/live_{lang}.mp4                 1920x1080, stream-ready (2s keyframes, CBR-ish)
  out/live_description_{lang}.txt     YouTube description with dealim.net/l/N links
  data/live_links.json                N -> affiliate url (subid {lang}_ytlive_{niche}); the site build turns it into /l/N
  public/l/N.html                     same redirects, so they work before the next site build
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from math import ceil

from webgen.build import click_url

from .daily import BAD
from .make import OUT, ROOT, TMP, money

W, H, FPS = 1920, 1080, 30
_S = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
BRANDS = tuple(w.lower() for w in _S.get("joom_exclude_title_words", [])) + ("armour", "girls", "boys", "onesie", "crotch", "romper", "pajama")
N_DEALS = int(os.environ.get("LIVE_DEALS", "20"))
TOTAL = float(os.environ.get("LIVE_SECONDS", "600"))
INTRO, OUTRO = 12.0, 20.0
PREF = ["audio", "tech", "brands", "coffee", "appliances", "home", "tools", "car", "sports", "shoes", "fashion", "kids"]
TXT = {
    "en": dict(live="LIVE · AliExpress deals right now", hook="Real AliExpress price drops", sub="Every price checked against its own 30-day history",
               now="Now", was="30-day price", link="Link #{n} in the description", foot="All links in the description · Telegram @discount_deals_promo",
               cta="New deals every day", tg="@discount_deals_promo"),
    "es": dict(live="EN DIRECTO · Chollos de AliExpress", hook="Bajadas de precio reales en AliExpress", sub="Cada precio comparado con sus últimos 30 días",
               now="Ahora", was="Precio 30 días", link="Enlace #{n} en la descripción", foot="Todos los enlaces en la descripción · Telegram @ofertas_descuentos_es",
               cta="Chollos nuevos cada día", tg="@ofertas_descuentos_es"),
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@500;700;900&display=block');
*{box-sizing:border-box;margin:0}
body{width:1920px;height:1080px;overflow:hidden;font-family:Rubik,sans-serif;color:#fff;
 background:radial-gradient(120% 120% at 0% 0%,#ff8a00 0%,#ff3b30 50%,#9e0f1b 100%)}
.bar{position:absolute;top:0;left:0;right:0;height:84px;background:rgba(0,0,0,.28);display:flex;align-items:center;padding:0 44px;
 font-size:38px;font-weight:700;gap:18px}
.dot{width:22px;height:22px;border-radius:50%;background:#fff;box-shadow:0 0 0 6px rgba(255,255,255,.3)}
.cnt{margin-left:auto;opacity:.9}
.card{position:absolute;top:130px;left:70px;width:800px;height:800px;background:#fff;border-radius:44px;overflow:hidden;
 box-shadow:0 30px 80px rgba(60,0,0,.35)}
.card img{width:100%;height:100%;object-fit:contain}
.num{position:absolute;top:140px;left:930px;font-size:64px;font-weight:900;opacity:.9}
.title{position:absolute;top:230px;left:930px;right:70px;font-size:62px;font-weight:700;line-height:1.15}
.off{position:absolute;top:440px;left:930px;background:#ffe600;color:#c4120c;font-weight:900;font-size:150px;line-height:1;
 padding:14px 44px;border-radius:30px;transform:rotate(-3deg);box-shadow:0 18px 44px rgba(0,0,0,.3)}
.price{position:absolute;top:640px;left:930px;font-size:50px;font-weight:500;line-height:1.3}
.price b{font-size:92px;font-weight:900}
.price s{opacity:.85}
.link{position:absolute;top:880px;left:930px;right:70px;background:#fff;color:#c4120c;font-size:50px;font-weight:900;
 padding:18px 30px;border-radius:24px;text-align:center}
.foot{position:absolute;bottom:0;left:0;right:0;height:70px;background:rgba(0,0,0,.28);display:flex;align-items:center;
 justify-content:center;font-size:32px;font-weight:500}
.center{position:absolute;top:200px;left:100px;right:100px;text-align:center}
.center .big{font-size:120px;font-weight:900;line-height:1.05}
.center .sm{font-size:52px;font-weight:500;margin-top:40px}
.thumbs{display:flex;gap:36px;justify-content:center;margin-top:60px}
.thumbs img{width:260px;height:260px;object-fit:contain;background:#fff;border-radius:30px}
.tg{display:inline-block;margin-top:50px;background:#fff;color:#1b6fd1;font-size:80px;font-weight:900;padding:26px 60px;border-radius:40px}
"""


def page(body: str) -> str:
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'


def short_name(d) -> str:
    name = re.sub(r"^\s*(\d+[- ]hour delivery|new|hot|original|20\d\d)\s+", "", d.get("title_local") or d["title"], flags=re.I)
    return name if len(name) <= 60 else name[:58].rsplit(" ", 1)[0] + "…"


def pick(lang: str) -> list[dict]:
    deals = json.loads((ROOT / "data" / f"deals_{lang}.json").read_text(encoding="utf-8"))
    deals = [d for d in deals if not d.get("expired") and d.get("store") != "joom" and d.get("image")
             and 8 <= d["price_usd"] <= 200 and d.get("discount", 0) >= 0.3 and d.get("niche") != "dollar"
             and not any(b in (d["title"] + " " + (d.get("title_local") or "")).lower() for b in BAD + BRANDS)]
    deals.sort(key=lambda d: -d["discount"] * min(d["price_usd"], 80))
    out, used = [], set()
    while len(out) < N_DEALS and len(used) < len(deals):   # round-robin over niches so the stream stays varied
        added = False
        for niche in PREF + sorted({d.get("niche") for d in deals} - set(PREF)):
            for d in deals:
                if d["slug"] not in used and d.get("niche") == niche:
                    used.add(d["slug"]); out.append(d); added = True
                    break
            if len(out) == N_DEALS:
                break
        if not added:
            break
    return out


def redirect_html(url: str) -> str:
    u = html.escape(url, quote=True)
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="robots" content="noindex">'
            f'<meta http-equiv="refresh" content="0;url={u}"><title>dealim.net</title></head>'
            f'<body><a href="{u}" rel="sponsored nofollow">Continue to AliExpress</a>'
            f'<script>location.replace({json.dumps(url)})</script></body></html>')


def main() -> int:
    from playwright.sync_api import sync_playwright
    lang = (sys.argv[1:] or ["en"])[0]
    t = TXT[lang]
    TMP.mkdir(parents=True, exist_ok=True)
    ds = pick(lang)
    per = (TOTAL - INTRO - OUTRO) / len(ds)
    imgs = []
    for d in ds:
        img = TMP / (d["pid"].split(":")[1] + ".jpg")
        if not img.exists():
            req = urllib.request.Request(d["image"], headers={"User-Agent": "Mozilla/5.0"})
            img.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        imgs.append(img)

    bar = f'<div class="bar"><span class="dot"></span>{t["live"]}<span class="cnt">dealim.net</span></div>'
    foot = f'<div class="foot">{t["foot"]}</div>'
    thumbs = "".join(f'<img src="{i.as_uri()}">' for i in imgs[:5])
    sl = [(page(bar + f'<div class="center"><div class="big">{t["hook"]}</div><div class="sm">{t["sub"]} ✅</div>'
                f'<div class="thumbs">{thumbs}</div></div>' + foot), INTRO)]
    for n, (d, img) in enumerate(zip(ds, imgs), 1):
        sl.append((page(bar.replace('dealim.net</span>', f'{n} / {len(ds)}</span>') +
            f'<div class="card"><img src="{img.as_uri()}"></div><div class="num">#{n}</div>'
            f'<div class="title">{html.escape(short_name(d))}</div>'
            f'<div class="off">-{round(d["discount"] * 100)}%</div>'
            f'<div class="price">{t["now"]} <b>{money(d["price_usd"], lang)}</b><br>{t["was"]} <s>{money(d["median_30d"], lang)}</s></div>'
            f'<div class="link">👇 {t["link"].format(n=n)}</div>' + foot), per))
    sl.append((page(bar + f'<div class="center"><div class="big">{t["cta"]} 🔥</div>'
                    f'<div class="tg">Telegram {t["tg"]}</div><div class="sm">dealim.net</div></div>' + foot), OUTRO))

    pngs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for i, (h, _) in enumerate(sl):
            f = TMP / f"live_{lang}_{i}.html"
            f.write_text(h, encoding="utf-8")
            pg.goto(f.as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
            p = TMP / f"live_{lang}_{i}.png"; pg.screenshot(path=str(p)); pngs.append(p)
        b.close()
    (OUT / f"live_cover_{lang}.png").write_bytes(pngs[1].read_bytes())

    # each slide: slow zoom; joined with short crossfades. Audio: quiet ambient pad (no copyrighted music).
    xf = 0.6
    inputs, filt = [], []
    for i, (p, (_, dur)) in enumerate(zip(pngs, sl)):
        inputs += ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(p)]
        filt.append(f"[{i}:v]scale={W * 2}:{H * 2},zoompan=z='min(zoom+0.0002,1.06)':x='iw/2-(iw/zoom/2)':"
                    f"y='ih/2-(ih/zoom/2)':d={ceil(dur * FPS)}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[v{i}]")
    prev, tt = "v0", sl[0][1]
    for i in range(1, len(pngs)):
        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration={xf}:offset={tt - xf:.2f}[x{i}]")
        prev, tt = f"x{i}", tt + sl[i][1] - xf
    pad = ("aevalsrc='0.035*sin(2*PI*130.81*t)*(0.7+0.3*sin(2*PI*0.07*t))+0.03*sin(2*PI*196*t)*(0.7+0.3*sin(2*PI*0.05*t+1))"
           "+0.025*sin(2*PI*261.63*t)*(0.6+0.4*sin(2*PI*0.09*t+2))+0.02*sin(2*PI*329.63*t)*(0.6+0.4*sin(2*PI*0.04*t+3))'"
           f":s=44100:d={tt:.2f},aformat=channel_layouts=stereo")
    mp4 = OUT / f"live_{lang}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-f", "lavfi", "-i", pad,
                    "-filter_complex", ";".join(filt), "-map", f"[{prev}]", "-map", f"{len(pngs)}:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
                    "-g", str(FPS * 2), "-keyint_min", str(FPS * 2), "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    print(f"{lang}: {mp4} {tt:.1f}s, {len(ds)} deals", flush=True)

    links = []
    ldir = ROOT / "public" / "l"
    ldir.mkdir(parents=True, exist_ok=True)
    for n, d in enumerate(ds, 1):
        url = click_url(d, "ytlive")
        links.append({"n": n, "url": url, "slug": d["slug"]})
        (ldir / f"{n}.html").write_text(redirect_html(url), encoding="utf-8")
    (ROOT / "data" / "live_links.json").write_text(json.dumps(links, indent=1), encoding="utf-8")

    hdr = {"en": "🔥 Real AliExpress price drops, checked against each product's own 30-day price history.\n"
                 "Tap a number to open the deal:\n",
           "es": "🔥 Bajadas de precio reales en AliExpress, comparadas con el historial de 30 días de cada producto.\n"
                 "Toca un número para abrir el chollo:\n"}[lang]
    lines = [f"#{n} {short_name(d)} – {money(d['price_usd'], lang)} (-{round(d['discount'] * 100)}%) https://dealim.net/l/{n}"
             for n, d in enumerate(ds, 1)]
    tail = {"en": "\n\n📲 New deals every day on Telegram: https://t.me/discount_deals_promo\n🌐 All deals: https://dealim.net/en/\n\n"
                  "Disclosure: these are affiliate links. If you buy through them I may earn a small commission at no extra cost to you. "
                  "Prices can change at any time.",
            "es": "\n\n📲 Chollos nuevos cada día en Telegram: https://t.me/ofertas_descuentos_es\n🌐 Todos: https://dealim.net/es/\n\n"
                  "Aviso: enlaces de afiliado. Si compras a través de ellos puedo ganar una pequeña comisión sin coste extra para ti. "
                  "Los precios pueden cambiar."}[lang]
    (OUT / f"live_description_{lang}.txt").write_text(hdr + "\n".join(lines) + tail, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

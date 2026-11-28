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
from pathlib import Path

from webgen.build import click_url

from .daily import BAD
from .make import OUT, ROOT, TMP, money

W, H, FPS = 1920, 1080, 30
_S = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
BRANDS = tuple(w.lower() for w in _S.get("joom_exclude_title_words", [])) + ("armour", "girls", "boys", "onesie", "crotch", "romper", "pajama")
N_DEALS = int(os.environ.get("LIVE_DEALS", "30"))
THEME = os.environ.get("LIVE_THEME", "")           # "" = all niches; "gaming" = gaming gear only (Twitch)
LPFX = os.environ.get("LIVE_PREFIX", "l")          # short links dealim.net/<LPFX>/N
TOTAL = float(os.environ.get("LIVE_SECONDS", "600"))
INTRO, OUTRO = 8.0, 12.0
PREF = ["audio", "power", "dashcam", "tech", "brands", "coffee", "appliances", "home", "pets", "tools", "car", "sports", "shoes", "fashion", "kids"]
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
body{width:1920px;height:1080px;overflow:hidden;font-family:Rubik,sans-serif;color:#fff;background:transparent}
.bar{position:absolute;top:0;left:0;right:0;height:84px;background:rgba(120,0,10,.75);display:flex;align-items:center;padding:0 44px;
 font-size:38px;font-weight:900;gap:18px;letter-spacing:.5px}
.dot{width:24px;height:24px;border-radius:50%;background:#ff1a1a;box-shadow:0 0 0 6px rgba(255,255,255,.5)}
.cnt{margin-left:auto}
.card{position:absolute;top:130px;left:70px;width:800px;height:800px;background:#fff;border-radius:44px;overflow:hidden;
 border:10px solid #ffe600;box-shadow:0 30px 80px rgba(60,0,0,.55)}
.card img{width:100%;height:100%;object-fit:contain}
.num{position:absolute;top:120px;left:930px;font-size:58px;font-weight:900;color:#ffe600;text-shadow:0 4px 0 #8a0010}
.title{position:absolute;top:200px;left:930px;right:70px;font-size:58px;font-weight:900;line-height:1.12;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;text-shadow:0 5px 0 rgba(110,0,10,.8)}
.price{position:absolute;top:660px;left:930px;font-size:50px;font-weight:700;line-height:1.25;text-shadow:0 4px 0 rgba(110,0,10,.8)}
.price b{font-size:100px;font-weight:900;color:#fff}
.price s{opacity:.9}
.link{position:absolute;top:880px;left:930px;right:70px;background:#fff;color:#d0001b;font-size:50px;font-weight:900;
 padding:18px 30px;border-radius:24px;text-align:center;box-shadow:0 12px 0 #8a0010}
.qr{position:absolute;top:585px;right:70px;width:250px;background:#fff;border-radius:22px;padding:14px 14px 6px;text-align:center;
 color:#d0001b;font-size:26px;font-weight:900;box-shadow:0 10px 0 #8a0010}
.qr img{width:222px;height:222px;display:block}
.foot{position:absolute;bottom:0;left:0;right:0;height:70px;background:rgba(120,0,10,.75);display:flex;align-items:center;
 justify-content:center;font-size:32px;font-weight:700}
.center{position:absolute;top:170px;left:100px;right:100px;text-align:center;text-shadow:0 6px 0 rgba(110,0,10,.8)}
.center .big{font-size:120px;font-weight:900;line-height:1.05}
.center .sm{font-size:52px;font-weight:700;margin-top:36px}
.thumbs{display:flex;gap:36px;justify-content:center;margin-top:56px}
.thumbs img{width:260px;height:260px;object-fit:contain;background:#fff;border-radius:30px;border:8px solid #ffe600}
.tg{display:inline-block;margin-top:50px;background:#fff;color:#1b6fd1;font-size:80px;font-weight:900;padding:26px 60px;border-radius:40px;text-shadow:none}
.badge{width:480px;height:220px;display:flex;align-items:center;justify-content:center;background:#ffe600;color:#d0001b;
 font-family:Rubik,sans-serif;font-weight:900;font-size:150px;border-radius:34px;transform:rotate(-4deg);border:8px solid #fff}
.rays{width:2400px;height:2400px;border-radius:50%;
 background:repeating-conic-gradient(#ff9f00 0deg 9deg,#ff3b1f 9deg 18deg)}
.burst{position:absolute;font-size:46px;font-weight:900;background:#fff;color:#d0001b;padding:10px 26px;border-radius:40px;transform:rotate(6deg)}
"""


def page(body: str, bg: str = "transparent") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f'<body style="background:{bg}">{body}</body></html>')


def short_name(d) -> str:
    name = re.sub(r"^\s*(\d+[- ]hour delivery|new|hot|original|20\d\d)\s+", "", d.get("title_local") or d["title"], flags=re.I)
    return name if len(name) <= 60 else name[:58].rsplit(" ", 1)[0] + "…"


SOURCE = os.environ.get("LIVE_SOURCE", "")         # "talia" = Talia's Closet picks (config talia_picks)


def pick_talia(lang: str) -> list[dict]:
    """Talia's Closet live: her teen-fashion picks, in the order she chose them."""
    import urllib.parse
    base = _S.get("affiliate_base", "https://rzekl.com/g/1e8d11449413a2dc498e16525dc3e8/")
    out = []
    for x in _S.get("talia_picks", []):
        if not x.get("live", True) or not x.get("img") or not x.get("list_usd") or x["list_usd"] <= x["price_usd"]:
            continue
        ali = "https://www.aliexpress.com/item/" + x["id"] + ".html"
        out.append({"pid": "talia:" + x["id"], "slug": "talia-" + x["id"], "title": x.get("name_en") or x["name"],
                    "title_local": x.get("name_" + lang) or x.get("name_en") or x["name"], "image": x["img"],
                    "price_usd": x["price_usd"], "median_30d": x["list_usd"], "discount": 1 - x["price_usd"] / x["list_usd"],
                    "url": base + "?ulp=" + urllib.parse.quote(ali, safe=""), "lang": lang, "niche": "talia"})
    return out[:N_DEALS]


def pick(lang: str) -> list[dict]:
    if SOURCE == "talia":
        return pick_talia(lang)
    deals = json.loads((ROOT / "data" / f"deals_{lang}.json").read_text(encoding="utf-8"))
    deals = [d for d in deals if not d.get("expired") and d.get("store") != "joom" and d.get("image")
             and 8 <= d["price_usd"] <= 200 and d.get("discount", 0) >= 0.3 and d.get("niche") != "dollar"
             and not any(b in (d["title"] + " " + (d.get("title_local") or "")).lower() for b in BAD + BRANDS)]
    if THEME:
        kw = _S.get("live_themes", {}).get(THEME, [])
        rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in kw) + r")\b", re.I)
        deals = [d for d in deals if rx.search(d.get("title_local") or d["title"]) and "stand" not in d["title"].lower()]
    deals.sort(key=lambda d: -d["discount"] * min(d["price_usd"], 80))
    seen_m, uniq = set(), []
    for d in deals:                       # one per product model ("ATTACK SHARK R98HE" x5 -> 1)
        m = " ".join(re.sub(r"[^\w ]", " ", short_name(d).lower()).split()[:3])
        if m not in seen_m:
            seen_m.add(m); uniq.append(d)
    deals = uniq
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


def index_html(links: list[dict], pfx: str) -> str:
    """dealim.net/<pfx>/ : every deal of the latest stream as a tappable list (stream chats/bios link here)."""
    title = {"g": "Gaming gear deals from the live stream", "t": "Talia's Closet – picks from the live stream"}.get(pfx, "Deals from the live stream")
    rows = "".join(
        f'<a class="r" href="/{pfx}/{x["n"]}" rel="sponsored nofollow">'
        f'<b class="n">#{x["n"]}</b>'
        + (f'<img src="{html.escape(x.get("img", ""), quote=True)}" alt="" loading="lazy" referrerpolicy="no-referrer">' if x.get("img") else "")
        + f'<span class="t">{html.escape(x.get("name", "Deal"))}</span>'
        + (f'<span class="p">{html.escape(x.get("price", ""))} <i>{html.escape(x.get("off", ""))}</i></span>' if x.get("price") else "")
        + '</a>' for x in links)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{title} | dealim.net</title><style>'
            'body{margin:0;font-family:system-ui,sans-serif;background:#fff4ec;color:#222}h1{font-size:1.3rem;margin:16px}'
            '.r{display:flex;align-items:center;gap:10px;margin:8px 12px;padding:8px;background:#fff;border-radius:12px;'
            'text-decoration:none;color:#222;box-shadow:0 2px 6px rgba(0,0,0,.08)}.r img{width:64px;height:64px;object-fit:contain}'
            '.n{color:#d0001b;min-width:2.2em}.t{flex:1;font-weight:600}.p{font-weight:800;white-space:nowrap}.p i{color:#d0001b;font-style:normal}'
            'footer{margin:16px;font-size:.8rem;opacity:.7}</style></head><body>'
            f'<h1>🔥 {title}</h1>{rows}<footer>Affiliate links: we may earn a commission at no extra cost to you. '
            'Prices can change. <a href="https://dealim.net/en/">All deals</a></footer></body></html>')


VOICE = {"en": "en-US-AriaNeural", "es": "es-ES-ElviraNeural"}
SAY = {
    "en": dict(intro="Live AliExpress deals. Every price is checked against its own thirty day history. All links are in the description.",
               deal="Deal number {n}. {name}. Now {price}, that is {off} percent off. Tap link number {n} in the description.",
               tg="Want more? Join our Telegram channel, new deals every day. The link is at the top of the description.",
               outro="New deals every day. Join our Telegram channel, link at the top of the description."),
    "es": dict(intro="Chollos de AliExpress en directo. Cada precio está comparado con sus últimos treinta días. Todos los enlaces están en la descripción.",
               deal="Chollo número {n}. {name}. Ahora {price}, un {off} por ciento de descuento. Abre el enlace número {n} en la descripción.",
               tg="¿Quieres más? Únete a nuestro canal de Telegram, chollos nuevos cada día. El enlace está al principio de la descripción.",
               outro="Chollos nuevos cada día. Únete a nuestro canal de Telegram, enlace al principio de la descripción."),
}


def narration(lang: str, ds: list, sl: list) -> Path | None:
    """Spoken voice-over (edge-tts, free) fitted to each slide; returns a wav or None if TTS is unavailable."""
    if os.environ.get("LIVE_VOICE", "1") == "0":
        return None
    say, parts, ok = SAY[lang], [], 0
    for i, (_, dur, _) in enumerate(sl):
        if i == 0:
            txt = say["intro"]
        elif i == len(sl) - 1:
            txt = say["outro"]
        else:
            d = ds[i - 1]
            txt = say["deal"].format(n=i, name=" ".join(short_name(d).split()[:9]), price=money(d["price_usd"], lang),
                                     off=round(d["discount"] * 100))
            if i % 5 == 0:
                txt += " " + say["tg"]
        mp3, wav = TMP / f"nar_{lang}_{i}.mp3", TMP / f"nar_{lang}_{i}.wav"
        r = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOICE[lang], "--rate=+8%", "--text", txt,
                            "--write-media", str(mp3)], capture_output=True, text=True)
        af = ["-af", "adelay=300|300,apad"]
        if r.returncode == 0 and mp3.exists() and mp3.stat().st_size > 1000:
            ok += 1
            m_ = re.search(r"Duration: (\d+):(\d+):([\d.]+)", subprocess.run(["ffmpeg", "-i", str(mp3)], capture_output=True, text=True).stderr)
            ln = (int(m_[1]) * 3600 + int(m_[2]) * 60 + float(m_[3]) if m_ else dur) + 0.3
            if ln > dur - 0.2:                                     # too long for the slide: speed up (max 1.5x)
                af = ["-af", f"atempo={min(1.5, ln / (dur - 0.2)):.3f},adelay=300|300,apad"]
            src = ["-i", str(mp3)]
        else:
            src = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            af = []
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, *af, "-t", f"{dur:.2f}", "-ar", "44100", "-ac", "2", str(wav)], check=True)
        parts.append(wav)
    if ok < max(3, len(sl) // 2):
        print(f"voice-over unavailable ({ok}/{len(sl)} clips) - music only"); return None
    lst = TMP / f"nar_{lang}_list.txt"
    lst.write_text("".join(f"file '{p_}'\n" for p_ in parts), encoding="utf-8")
    out = TMP / f"nar_{lang}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
    print(f"voice-over: {ok}/{len(sl)} clips", flush=True)
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright
    lang = (sys.argv[1:] or ["en"])[0]
    t = dict(TXT[lang])
    if SOURCE == "talia":
        t.update({"en": dict(live="LIVE · Talia's Closet · teen fashion deals", hook="Talia's Closet 👗", sub="Trendy teen picks chosen by Talia",
                             was="Store price", cta="More of Talia's picks: dealim.net/en/talia"),
                  "es": dict(live="EN DIRECTO · El armario de Talia", hook="El armario de Talia 👗", sub="Moda juvenil elegida por Talia",
                             was="Precio tienda", cta="Más elecciones de Talia: dealim.net/es/talia")}[lang])
    if THEME == "gaming":
        t.update(live="🎮 GAMING GEAR DEALS · AliExpress", hook="Gaming gear price drops",
                 foot="All links in one list: dealim.net/g")
    TMP.mkdir(parents=True, exist_ok=True)
    ds = pick(lang)
    if len(ds) < int(os.environ.get("LIVE_MIN", "1")):
        print(f"only {len(ds)} deals for theme '{THEME}' (< LIVE_MIN) - not going live"); sys.exit(3)
    per = float(os.environ.get("LIVE_PER", "15"))          # seconds per deal: fast pace keeps viewers watching
    imgs = []
    for d in ds:
        img = TMP / (d["pid"].split(":")[1] + ".jpg")
        if not img.exists():
            req = urllib.request.Request(d["image"], headers={"User-Agent": "Mozilla/5.0"})
            img.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        imgs.append(img)

    import qrcode

    def qr_html(n):
        q = TMP / f"qr_{LPFX}_{n}.png"
        qrcode.make(f"https://dealim.net/{LPFX}/{n}", border=1, box_size=10).save(q)
        return f'<div class="qr"><img src="{q.as_uri()}">📱 Scan to open</div>'

    bar = f'<div class="bar"><span class="dot"></span>{t["live"]}<span class="cnt">dealim.net</span></div>'
    foot = f'<div class="foot">{t["foot"]}</div>'
    thumbs = "".join(f'<img src="{i.as_uri()}">' for i in imgs[:5])
    sl = [(page(bar + f'<div class="center"><div class="big">{t["hook"]}</div><div class="sm">{t["sub"]} ✅</div>'
                f'<div class="thumbs">{thumbs}</div></div>' + foot), INTRO, None)]
    for n, (d, img) in enumerate(zip(ds, imgs), 1):
        sl.append((page(bar.replace('dealim.net</span>', f'{n} / {len(ds)}</span>') +
            f'<div class="card"><img src="{img.as_uri()}"></div><div class="num">DEAL #{n}</div>'
            f'<div class="title">{html.escape(short_name(d))}</div>'
            f'<div class="price">{t["now"]} <b>{money(d["price_usd"], lang)}</b><br>{t["was"]} <s>{money(d["median_30d"], lang)}</s></div>'
            + qr_html(n) +
            f'<div class="link">👉 {(t["link"].format(n=n) if LPFX == "l" else "dealim.net/" + LPFX + "/" + str(n))}</div>' + foot), per, f'-{round(d["discount"] * 100)}%'))
    sl.append((page(bar + f'<div class="center"><div class="big">{t["cta"]} 🔥</div>'
                    f'<div class="tg">Telegram {t["tg"]}</div><div class="sm">dealim.net</div></div>' + foot), OUTRO, None))

    def shot(pg, h, path, sel=None):
        f = TMP / (path.stem + ".html"); f.write_text(h, encoding="utf-8")
        pg.goto(f.as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        (pg.locator(sel) if sel else pg).screenshot(path=str(path), omit_background=True)

    rays = TMP / "live_rays.png"
    burst = TMP / "live_burst.png"
    fgs, badges = [], []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for i, (h, _, off) in enumerate(sl):
            p_ = TMP / f"live_{lang}_{i}.png"; shot(pg, h, p_); fgs.append(p_)
            bd = None
            if off:
                bd = TMP / f"live_{lang}_b{i}.png"
                shot(pg, page(f'<div style="padding:40px;display:inline-block"><div class="badge">{off}</div></div>'), bd, ".badge")
            badges.append(bd)
        shot(pg, page('<div style="padding:30px;display:inline-block"><div class="burst">⚡ PRICE DROP</div></div>'), burst, ".burst")
        b.close()
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1300, 1300), "#ff3b1f")
    dr = ImageDraw.Draw(im)
    for k in range(0, 360, 18):
        dr.pieslice([-700, -700, 2000, 2000], k, k + 9, fill="#ff9f00")
    im.save(rays)

    # one segment per slide: rotating sunburst + slide + pulsing discount badge + flashing sticker + countdown bar
    jobs = []
    for i, ((_, dur, off), fg, bd) in enumerate(zip(sl, fgs, badges)):
        seg = TMP / f"live_{lang}_seg{i}.mp4"
        ins = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", str(rays),
               "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", str(fg)]
        f = (f"[0:v]scale=1300:1300,rotate=a='t*0.35':c=#c4121f,scale=2300:2300,crop={W}:{H},format=rgba[bg];"
             f"[bg][1:v]overlay=0:0[a]")
        last = "a"
        if bd:
            ins += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", str(bd),
                    "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", str(burst),
                    "-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"color=c=#ffe600:s={W}x14:r={FPS}"]
            f += (f";[2:v]scale=w='trunc(iw*(1+0.08*sin(2*PI*t*2.07))/2)*2':h=-2:eval=frame[bz]"
                  f";[a][bz]overlay=x='1190-overlay_w/2':y='478-overlay_h/2':eval=frame[b]"
                  f";[b][3:v]overlay=x=20:y=86:enable='lt(mod(t,1),0.62)'[c]"
                  f";[c][4:v]overlay=x='-W+W*t/{dur:.2f}':y=996[d]")
            last = "d"
        f += f";[{last}]format=yuv420p[v]"
        jobs.append(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", f, "-map", "[v]", "-r", str(FPS),
                     "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "9000k",
                     "-g", str(FPS * 2), "-keyint_min", str(FPS * 2), "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                     "-threads", "2", str(seg)])
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:        # segments render in parallel
        list(ex.map(lambda c: subprocess.run(c, check=True), jobs))
    segs = [Path(j[-1]) for j in jobs]
    lst = TMP / f"live_{lang}_list.txt"
    lst.write_text("".join(f"file '{s_}'\n" for s_ in segs), encoding="utf-8")
    music = TMP / "live_loop.wav"
    from .music import main as make_music
    make_music(str(music))
    tt = sum(x[1] for x in sl)
    mp4 = OUT / f"live_{lang}.mp4"
    try:
        nar = narration(lang, ds, sl)
    except Exception as e:                      # never lose the stream because of the voice-over
        print(f"voice-over failed: {e!r} - music only"); nar = None
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-stream_loop", "-1", "-i", str(music)]
    if nar:
        cmd += ["-i", str(nar), "-filter_complex",
                "[1:a]volume=0.28[m];[2:a]volume=1.0[v];[m][v]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    subprocess.run(cmd + ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{tt:.2f}",
                          "-movflags", "+faststart", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{INTRO + 2:.1f}", "-i", str(mp4), "-frames:v", "1",
                    str(OUT / f"live_cover_{lang}.png")], check=True)
    print(f"{lang}: {mp4} {tt:.1f}s, {len(ds)} deals", flush=True)

    links = []
    ldir = ROOT / "public" / LPFX
    ldir.mkdir(parents=True, exist_ok=True)
    for n, d in enumerate(ds, 1):
        url = click_url(d, os.environ.get("LIVE_SRC_TAG") or ("ytlive" if LPFX == "l" else "twitch"))
        links.append({"n": n, "url": url, "slug": d["slug"], "name": short_name(d), "img": d["image"],
                      "price": money(d["price_usd"], lang), "off": f'-{round(d["discount"] * 100)}%'})
        (ldir / f"{n}.html").write_text(redirect_html(url), encoding="utf-8")
    (ldir / "index.html").write_text(index_html(links, LPFX), encoding="utf-8")
    (ROOT / "data" / ("live_links.json" if LPFX == "l" else f"live_links_{LPFX}.json")).write_text(json.dumps(links, indent=1), encoding="utf-8")

    hdr = {"en": "🔥 Real AliExpress price drops, checked against each product's own 30-day price history.\n"
                 "Tap a number to open the deal:\n",
           "es": "🔥 Bajadas de precio reales en AliExpress, comparadas con el historial de 30 días de cada producto.\n"
                 "Toca un número para abrir el chollo:\n"}[lang]
    lines = [f"#{n} {short_name(d)} – {money(d['price_usd'], lang)} (-{round(d['discount'] * 100)}%) https://dealim.net/{LPFX}/{n}"
             for n, d in enumerate(ds, 1)]
    tail = {"en": "\n\n📲 New deals every day on Telegram: https://t.me/discount_deals_promo\n🌐 All deals: https://dealim.net/en/\n\n"
                  "Disclosure: these are affiliate links. If you buy through them I may earn a small commission at no extra cost to you. "
                  "Prices can change at any time.",
            "es": "\n\n📲 Chollos nuevos cada día en Telegram: https://t.me/ofertas_descuentos_es\n🌐 Todos: https://dealim.net/es/\n\n"
                  "Aviso: enlaces de afiliado. Si compras a través de ellos puedo ganar una pequeña comisión sin coste extra para ti. "
                  "Los precios pueden cambiar."}[lang]
    top = {"en": "📲 Join our Telegram for new deals every day: https://t.me/discount_deals_promo\n\n",
           "es": "📲 Únete a Telegram para chollos nuevos cada día: https://t.me/ofertas_descuentos_es\n\n"}[lang]
    (OUT / f"live_description_{lang}.txt").write_text(top + hdr + "\n".join(lines) + tail, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

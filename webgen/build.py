"""Static site generator: /he/ /es/ /en/ with hreflang, sitemap, deal pages."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from pathlib import Path

from engine.core import DATA, LANGS, ROOT, SETTINGS

OUT = ROOT / "public"
BASE = os.environ.get("SITE_BASE_URL", SETTINGS["site_base_url"]).rstrip("/")
CLICK_BASE = os.environ.get("CLICK_BASE_URL", "").rstrip("/")   # Cloudflare Worker, optional

CSS = """
:root{--bg:#fbf7f2;--card:#fff;--ink:#1d1a16;--muted:#6b6259;--accent:#e4572e;--good:#1f8a5b;--line:#ece4da}
@media (prefers-color-scheme:dark){:root{--bg:#141210;--card:#1e1b18;--ink:#f3ede6;--muted:#a89d91;--line:#2d2925}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
a{color:inherit}.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);background:var(--card)}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;flex-wrap:wrap}
.brand{font-weight:800;font-size:1.15rem;text-decoration:none}.brand span{color:var(--accent)}
.langs a{margin-inline-start:10px;font-size:.9rem;color:var(--muted);text-decoration:none}.langs a.on{color:var(--ink);font-weight:700}
.hero{padding:28px 0 8px}.hero h1{margin:0 0 6px;font-size:1.7rem}.hero p{margin:0;color:var(--muted)}
.cta{display:inline-block;margin-top:14px;background:var(--accent);color:#fff;padding:9px 16px;border-radius:999px;text-decoration:none;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;padding:18px 0 30px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;text-decoration:none}
.card img{width:100%;aspect-ratio:1/1;object-fit:cover;background:var(--line)}
.card .b{padding:12px;display:flex;flex-direction:column;gap:6px;flex:1}
.t{font-weight:600;font-size:.95rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.price{font-size:1.25rem;font-weight:800}.was{color:var(--muted);text-decoration:line-through;font-size:.9rem;margin-inline-start:6px}
.badges{display:flex;gap:6px;flex-wrap:wrap}.badge{font-size:.78rem;padding:2px 8px;border-radius:999px;background:var(--line)}
.badge.off{background:var(--accent);color:#fff}.badge.heat{background:#fff1d6;color:#7a4b00}
.expired{opacity:.55}.expired .badge.off{background:var(--muted)}
.niches{display:flex;gap:8px;flex-wrap:wrap;padding:6px 0}.niches a{border:1px solid var(--line);padding:5px 12px;border-radius:999px;text-decoration:none;font-size:.9rem;background:var(--card)}
.deal{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;padding:24px 0}
@media(max-width:760px){.deal{grid-template-columns:1fr}}
.deal img{width:100%;border-radius:14px;border:1px solid var(--line)}
.go{display:block;text-align:center;background:var(--good);color:#fff;padding:13px;border-radius:12px;text-decoration:none;font-weight:800;font-size:1.1rem;margin:14px 0}
.note,.foot{color:var(--muted);font-size:.85rem}
footer{border-top:1px solid var(--line);padding:18px 0 40px;margin-top:20px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.empty{padding:40px 0;color:var(--muted)}
"""


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def slug(title: str, pid: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "deal"
    return f"{base}-{re.sub(r'[^a-z0-9]', '', pid.split(':')[-1].lower())[-10:]}"


def money(usd: float, lang: str) -> str:
    c = LANGS[lang]
    v = usd * c["currency_rate_from_usd"]
    txt = f"{v:,.2f} {c['currency']}" if lang == "he" else f"{c['currency']}{v:,.2f}"
    return f"<bdi>{txt}</bdi>"


def plain(usd: float, lang: str) -> str:
    c = LANGS[lang]
    return f"{c['currency']}{usd * c['currency_rate_from_usd']:,.2f}"


def click_url(d: dict) -> str:
    if CLICK_BASE:
        return f"{CLICK_BASE}/go/{d['lang']}/{d['niche']}?u={html.escape(d['url'])}"
    return d["url"]


def page(lang: str, path: str, title: str, desc: str, body: str, alt_paths: dict | None = None,
         schema: dict | None = None) -> str:
    c = LANGS[lang]
    alts = alt_paths or {l: path.replace(f"/{lang}/", f"/{l}/", 1) for l in LANGS}
    hreflang = "".join(f'<link rel="alternate" hreflang="{l}" href="{BASE}{p}">' for l, p in alts.items())
    hreflang += f'<link rel="alternate" hreflang="x-default" href="{BASE}{alts.get("en", path)}">'
    langs = "".join(
        f'<a class="{"on" if l == lang else ""}" href="{alts[l]}" hreflang="{l}">{esc(LANGS[l]["name"])}</a>'
        for l in LANGS)
    s = c["strings"]
    ld = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>' if schema else ""
    return f"""<!doctype html><html lang="{lang}" dir="{c['dir']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"><link rel="canonical" href="{BASE}{path}">{hreflang}
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<style>{CSS}</style>{ld}</head><body>
<header><div class="wrap top"><a class="brand" href="/{lang}/">🔥 <span>{esc(c['site_title'])}</span></a>
<nav class="langs">{langs}</nav></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap foot"><p>{esc(s['disclosure'])}</p>
<p><a href="/{lang}/how.html">{esc(s['how_title'])}</a> · <a href="{c['channel_url']}">{esc(s['join_channel'])}</a></p></div></footer>
</body></html>"""


def card(d: dict) -> str:
    lang, s = d["lang"], LANGS[d["lang"]]["strings"]
    cls = "card expired" if d.get("expired") else "card"
    tag = s["expired"] if d.get("expired") else f"-{round(d['discount'] * 100)}%"
    return f"""<a class="{cls}" href="/{lang}/deal/{d['slug']}.html">
<img src="{esc(d['image'])}" alt="{esc(d['title'][:80])}" loading="lazy">
<div class="b"><div class="t">{esc(d.get('title_local') or d['title'])}</div>
<div><span class="price">{money(d['price_usd'], lang)}</span><span class="was">{money(d['median_30d'], lang)}</span></div>
<div class="badges"><span class="badge off">{esc(tag)}</span><span class="badge heat">{esc(s['heat'])} {round(d['heat'])}</span></div></div></a>"""


def chart(history: list, lang: str) -> str:
    pts = [p for _, p in history]
    if len(pts) < 2:
        return ""
    w, h, pad = 560, 160, 24
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    xs = [pad + i * (w - 2 * pad) / (len(pts) - 1) for i in range(len(pts))]
    ys = [h - pad - (p - lo) / span * (h - 2 * pad) for p in pts]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    return f"""<div class="chart"><div class="note">{esc(LANGS[lang]['strings']['price_history'])}</div>
<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="price history" direction="ltr" style="direction:ltr">
<path d="{path}" fill="none" stroke="#e4572e" stroke-width="2.5"/>
<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="5" fill="#1f8a5b"/>
<text x="{pad}" y="14" font-size="12" fill="currentColor">{plain(hi, lang)}</text>
<text x="{pad}" y="{h - 4}" font-size="12" fill="currentColor">{plain(lo, lang)}</text></svg></div>"""


def load_archive(lang: str) -> list[dict]:
    f = DATA / f"deals_{lang}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    urls = []
    archives = {l: load_archive(l) for l in LANGS}

    for lang, c in LANGS.items():
        s = c["strings"]
        deals = archives[lang]
        live = [d for d in deals if not d.get("expired")]
        root = OUT / lang
        (root / "deal").mkdir(parents=True)
        (root / "niche").mkdir()

        niche_links = "".join(f'<a href="/{lang}/niche/{k}.html">{esc(n["title"])}</a>'
                              for k, n in c["niches"].items())
        grid = "".join(card(d) for d in deals[:60]) or f'<p class="empty">{esc(s["no_deals"])}</p>'
        body = f"""<section class="hero"><h1>{esc(s['latest'])}</h1><p>{esc(c['site_tagline'])}</p>
<a class="cta" href="{c['channel_url']}">✈ {esc(s['join_channel'])}</a></section>
<nav class="niches">{niche_links}</nav><section class="grid">{grid}</section>"""
        (root / "index.html").write_text(
            page(lang, f"/{lang}/", c["site_title"], c["meta_description"], body), encoding="utf-8")
        urls.append(f"/{lang}/")

        for key, n in c["niches"].items():
            items = [d for d in deals if d.get("niche") == key]
            g = "".join(card(d) for d in items[:60]) or f'<p class="empty">{esc(s["no_deals"])}</p>'
            title = f"{n['title']} | {c['site_title']}"
            b = f'<section class="hero"><h1>{esc(n["title"])}</h1><p>{esc(c["site_tagline"])}</p></section><section class="grid">{g}</section>'
            (root / "niche" / f"{key}.html").write_text(
                page(lang, f"/{lang}/niche/{key}.html", title, f"{n['title']} – {c['meta_description']}", b),
                encoding="utf-8")
            urls.append(f"/{lang}/niche/{key}.html")

        for d in deals:
            p_path = f"/{lang}/deal/{d['slug']}.html"
            pct = round(d["discount"] * 100)
            title = f"{(d.get('title_local') or d['title'])[:70]} – {pct}% {s['off']} | {c['site_title']}"
            desc = f"{s['now']} {plain(d['price_usd'], lang)} ({s['was']} {plain(d['median_30d'], lang)}). {c['site_tagline']}."
            schema = {"@context": "https://schema.org", "@type": "Product", "name": d["title"],
                      "image": d["image"], "offers": {"@type": "Offer",
                      "price": round(d["price_usd"] * c["currency_rate_from_usd"], 2),
                      "priceCurrency": {"₪": "ILS", "€": "EUR", "$": "USD"}[c["currency"]],
                      "availability": "https://schema.org/OutOfStock" if d.get("expired") else "https://schema.org/InStock",
                      "url": BASE + p_path}}
            if d.get("rating"):
                schema["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": d["rating"],
                                             "reviewCount": max(d.get("orders") or 1, 1)}
            meta = f"⭐ {d['rating']:.1f} · {d.get('orders') or 0:,} {esc(s['orders'])}" if d.get("rating") else ""
            go = "" if d.get("expired") else f'<a class="go" rel="sponsored nofollow" href="{esc(click_url(d))}">🛒 {esc(s["go"])}</a>'
            b = f"""<article class="deal"><img src="{esc(d['image'])}" alt="{esc(d['title'][:80])}">
<div><h1>{esc(d.get('title_local') or d['title'])}</h1>
<div><span class="price">{money(d['price_usd'], lang)}</span><span class="was">{money(d['median_30d'], lang)}</span></div>
<div class="badges" style="margin:8px 0"><span class="badge off">-{pct}%</span><span class="badge heat">{esc(s['heat'])} {round(d['heat'])}/100</span></div>
<p class="note">{meta}</p>{go}{chart(d.get('history', []), lang)}
<p class="note">{esc(s['price_note'])}</p></div></article>"""
            # A deal page only exists in its own language: hreflang points to the language homes.
            alts = {l: (p_path if l == lang else f"/{l}/") for l in LANGS}
            (root / "deal" / f"{d['slug']}.html").write_text(
                page(lang, p_path, title, desc, b, alt_paths=alts, schema=schema), encoding="utf-8")
            if not d.get("expired"):
                urls.append(p_path)

        how = f'<section class="hero"><h1>{esc(s["how_title"])}</h1><p>{esc(s["how_body"])}</p><p>{esc(s["disclosure"])}</p></section>'
        (root / "how.html").write_text(page(lang, f"/{lang}/how.html", s["how_title"], s["how_body"][:150], how),
                                       encoding="utf-8")
        urls.append(f"/{lang}/how.html")

    # Root: language picker; suggests the browser language, never auto-redirects (SEO).
    picker = "".join(f'<a class="cta" style="margin:6px" href="/{l}/" hreflang="{l}">{esc(c["name"])}</a>' for l, c in LANGS.items())
    script = """<script>try{var l=(navigator.language||'').slice(0,2),a=document.querySelector('a[hreflang="'+l+'"]');if(a)a.style.outline='3px solid #1f8a5b'}catch(e){}</script>"""
    root_html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deals · דילים · Ofertas</title>{''.join(f'<link rel="alternate" hreflang="{l}" href="{BASE}/{l}/">' for l in LANGS)}
<link rel="alternate" hreflang="x-default" href="{BASE}/en/"><style>{CSS}</style></head>
<body><main class="wrap" style="text-align:center;padding:60px 16px"><h1>🔥</h1>{picker}</main>{script}</body></html>"""
    (OUT / "index.html").write_text(root_html, encoding="utf-8")

    sm = "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in urls)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>',
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    return len(urls)


if __name__ == "__main__":
    print("pages:", build())

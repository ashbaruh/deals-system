"""Static site generator: /he/ /es/ /en/ with hreflang, sitemap, deal pages."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path

from engine.core import DATA, LANGS, ROOT, SETTINGS

OUT = ROOT / "public"
BASE = (os.environ.get("SITE_BASE_URL") or SETTINGS["site_base_url"]).rstrip("/")
CLICK_BASE = os.environ.get("CLICK_BASE_URL", "").rstrip("/")   # Cloudflare Worker, optional

UI = {
    "he": {"search": "חיפוש דיל...", "hot": "🔥 הכי חמים עכשיו", "tab_hot": "חמים", "tab_new": "חדשים",
           "tab_off": "ההנחה הגדולה", "today": "היום", "yday": "אתמול", "at": "באלי אקספרס", "cta": "לדיל",
           "join_box": "כל דיל חדש ישר לטלגרם", "alert_box": "מחכים למוצר מסוים? הבוט ישלח הודעה כשיש עליו דיל",
           "how_box": "איך אנחנו בודקים", "how_short": "כל מחיר מושווה להיסטוריה של המוצר עצמו. מתפרסם רק מה שבאמת ירד במחיר.",
           "cats": "קטגוריות", "prev": "הקודם", "next": "הבא", "none_found": "לא נמצאו דילים. נסו מילה אחרת."},
    "es": {"search": "Buscar oferta...", "hot": "🔥 Lo más caliente ahora", "tab_hot": "Calientes", "tab_new": "Nuevos",
           "tab_off": "Mayor descuento", "today": "Hoy", "yday": "Ayer", "at": "en AliExpress", "cta": "Ver oferta",
           "join_box": "Cada oferta nueva directa a Telegram", "alert_box": "¿Esperas un producto? El bot te avisa cuando baje",
           "how_box": "Cómo lo comprobamos", "how_short": "Cada precio se compara con el historial del propio producto. Solo publicamos bajadas reales.",
           "cats": "Categorías", "prev": "Anterior", "next": "Siguiente", "none_found": "No hay ofertas. Prueba otra palabra."},
    "en": {"search": "Search deals...", "hot": "🔥 Hottest right now", "tab_hot": "Hottest", "tab_new": "Newest",
           "tab_off": "Biggest discount", "today": "Today", "yday": "Yesterday", "at": "at AliExpress", "cta": "Get deal",
           "join_box": "Every new deal straight to Telegram", "alert_box": "Waiting for something? The bot pings you when it drops",
           "how_box": "How we check", "how_short": "Every price is compared with the product's own history. Only real drops get posted.",
           "cats": "Categories", "prev": "Previous", "next": "Next", "none_found": "No deals found. Try another word."},
}
ICONS = {"nails": "💅", "coffee": "☕", "fashion": "👗", "audio": "🎧", "home": "🏠", "tech": "📱", "tools": "🔧",
         "car": "🚗", "sports": "⛺", "kids": "🧸", "shoes": "👟", "appliances": "🔌", "dollar": "💲", "brands": "🏷️"}

CSS = """
:root{--page:#eef0f4;--card:#fff;--ink:#1b1f26;--muted:#69707d;--line:#dfe3ea;--hot:#ff3b30;--hot2:#ff8a00;
--price:#e8590c;--save:#12804a;--save-bg:#e2f5ea;--btn:#ff6a00;--chip:#f4f5f8}
@media (prefers-color-scheme:dark){:root{--page:#16181d;--card:#1f232a;--ink:#eef0f4;--muted:#9aa1ad;--line:#2e333c;--chip:#272c34;--save-bg:#173326}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 Rubik,system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
a{color:inherit;text-decoration:none}img{display:block}
.wrap{max-width:1200px;margin:0 auto;padding:0 16px}
:focus-visible{outline:3px solid var(--btn);outline-offset:2px}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20}
.top{display:flex;align-items:center;gap:14px;padding:10px 0}
.brand{display:flex;align-items:center;gap:6px;font-weight:800;font-size:1.25rem;white-space:nowrap}
.brand b{background:linear-gradient(90deg,var(--hot),var(--hot2));-webkit-background-clip:text;background-clip:text;color:transparent}
.search{flex:1;min-width:0;position:relative}
.search input{width:100%;font:inherit;padding:10px 16px;border:1px solid var(--line);border-radius:999px;background:var(--chip);color:var(--ink)}
.acts{display:flex;gap:8px;align-items:center}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border-radius:999px;font-weight:600;white-space:nowrap;border:1px solid var(--line);background:var(--card)}
.btn.main{background:var(--btn);border-color:var(--btn);color:#fff}
.langs{display:flex;gap:14px;font-size:.85rem;color:var(--muted)}.langbar{justify-content:flex-end;padding-top:8px}.langbar a{padding:2px 0}.langs a.on{color:var(--ink);font-weight:700}
.cats{display:flex;flex-wrap:wrap;gap:8px;padding:8px 0 10px}
@media(max-width:760px){.cats{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}}.cats::-webkit-scrollbar{display:none}
.cats a{flex:none;padding:6px 14px;border-radius:999px;background:var(--chip);font-size:.9rem}
.cats a.on{background:var(--ink);color:var(--card)}
.event{background:linear-gradient(100deg,#e5174f,#ff5a36);color:#fff}
.event .wrap{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;font-weight:700;font-size:1.1rem}
.event a{border:1.5px solid #fff;border-radius:999px;padding:6px 14px;font-size:.9rem;white-space:nowrap}
h2{font-size:1.3rem;margin:22px 0 12px}
.hotbar{position:relative}
.rail{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding:2px 2px 12px;scrollbar-width:thin}
.hcard{flex:0 0 200px;scroll-snap-align:start;background:var(--card);border-radius:14px;overflow:hidden;border:1px solid var(--line);position:relative}
.hcard img{width:100%;aspect-ratio:1;object-fit:cover;background:var(--chip)}
.hcard .in{padding:10px}.hcard .t{font-size:.88rem}
.arrow{position:absolute;top:40%;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:1.2rem;cursor:pointer;box-shadow:0 2px 8px rgba(20,24,32,.15)}
.arrow.prev{inset-inline-start:-14px}.arrow.next{inset-inline-end:-14px}
@media(max-width:760px){.arrow{display:none}}
.deg{position:absolute;top:8px;inset-inline-start:8px;background:var(--card);color:var(--hot);font-weight:800;font-size:.85rem;padding:3px 9px;border-radius:999px;box-shadow:0 1px 4px rgba(20,24,32,.2)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:20px;align-items:start;padding-bottom:30px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.side{display:none}}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:12px}
.tabs button{font:inherit;font-weight:600;background:none;border:0;border-bottom:3px solid transparent;padding:10px 12px;color:var(--muted);cursor:pointer}
.tabs button.on{color:var(--ink);border-color:var(--btn)}
.list{display:flex;flex-direction:column;gap:10px}
.deal-row{display:grid;grid-template-columns:150px minmax(0,1fr);gap:14px;background:var(--card);border-radius:14px;padding:12px;border:1px solid var(--line)}
.deal-row .pic{position:relative}.deal-row img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:10px;background:var(--chip)}
.meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:.82rem;color:var(--muted)}
.temp{color:var(--hot);font-weight:800;font-size:.95rem;border:1px solid var(--line);border-radius:999px;padding:1px 10px}
.t{font-weight:600;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:6px 0}
.deal-row .t{font-size:1.05rem}
.prices{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.price{color:var(--price);font-weight:800;font-size:1.35rem}.hcard .price{font-size:1.1rem}
.was{color:var(--muted);text-decoration:line-through;font-size:.9rem}
.pct{background:var(--hot);color:#fff;font-weight:800;font-size:1.15rem;line-height:1.3;padding:2px 10px;border-radius:8px;letter-spacing:.01em}
.row-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:10px}
.go-btn{background:var(--btn);color:#fff;font-weight:700;padding:8px 18px;border-radius:999px;white-space:nowrap}
.expired{opacity:.5}.expired .go-btn{display:none}
@media(max-width:600px){.deal-row{grid-template-columns:96px minmax(0,1fr);gap:10px;padding:10px}.deal-row .t{font-size:.95rem}.price{font-size:1.15rem}
.top{flex-wrap:wrap}.brand{flex:1;font-size:1.05rem}.search{order:3;flex-basis:100%}.hcard{flex-basis:160px}.acts .btn:not(.main) .lbl{display:none}}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px}
.box h3{margin:0 0 6px;font-size:1rem}.box p{margin:0 0 10px;color:var(--muted);font-size:.9rem}
.box .btn{width:100%;justify-content:center}
.side .cl{display:flex;flex-direction:column}.side .cl a{padding:7px 0;border-bottom:1px solid var(--line)}
.deal{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;padding:24px 0}
@media(max-width:760px){.deal{grid-template-columns:1fr}}
.deal img{width:100%;border-radius:14px;border:1px solid var(--line);background:var(--card)}
.deal h1{font-size:1.4rem;line-height:1.3}
.badges{display:flex;gap:6px;flex-wrap:wrap}.badge{font-size:.8rem;padding:2px 9px;border-radius:999px;background:var(--chip)}
.badge.off{background:var(--hot);color:#fff;font-weight:800;font-size:1.6rem;padding:4px 14px;border-radius:10px}.badge.heat{color:var(--hot);font-weight:700}
.go{display:block;text-align:center;background:var(--btn);color:#fff;padding:14px;border-radius:999px;font-weight:800;font-size:1.1rem;margin:16px 0}
.note,.foot{color:var(--muted);font-size:.85rem}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.hero{padding:22px 0 6px}.hero h1{margin:0 0 6px;font-size:1.6rem}.hero p{margin:0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;padding:6px 0 30px}
.empty{padding:40px 0;color:var(--muted)}
footer{background:var(--card);border-top:1px solid var(--line);padding:20px 0 40px}
footer a{text-decoration:underline}
@media (prefers-reduced-motion:reduce){.rail{scroll-behavior:auto}}
"""

JS = """<script>
(function(){
var q=document.getElementById('q'),f=document.querySelector('.search'),list=document.getElementById('list'),none=document.getElementById('none');
function filt(){if(!list)return;var v=(q.value||'').trim().toLowerCase(),n=0;
 list.querySelectorAll('.deal-row').forEach(function(r){var ok=!v||r.dataset.s.indexOf(v)>-1;r.hidden=!ok;if(ok)n++});
 if(none)none.hidden=n>0;}
if(f&&document.getElementById('list'))f.addEventListener('submit',function(e){e.preventDefault()});
if(q){q.addEventListener('input',filt);var p=new URLSearchParams(location.search).get('q');if(p&&list){q.value=p;filt();}}
document.querySelectorAll('.tabs button').forEach(function(b){b.addEventListener('click',function(){
 document.querySelectorAll('.tabs button').forEach(function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-selected',x===b)});
 var k=b.dataset.k,rows=[].slice.call(list.children);
 rows.sort(function(a,c){return parseFloat(c.dataset[k])-parseFloat(a.dataset[k])});
 rows.forEach(function(r){list.appendChild(r)});});});
var rail=document.getElementById('rail'),rtl=document.dir==='rtl';
document.querySelectorAll('.arrow').forEach(function(a){a.addEventListener('click',function(){
 var d=(a.classList.contains('next')?1:-1)*(rtl?-1:1)*rail.clientWidth*0.8;
 rail.scrollBy({left:d,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});});});
})();
</script>"""


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


SEO_WORDS = {'he': ('דילים ומבצעים באלי אקספרס', 'מחיר באלי אקספרס'), 'es': ('ofertas y chollos de AliExpress', 'precio en AliExpress'), 'en': ('AliExpress deals & discounts', 'AliExpress price')}  # search words in <title>: what people type into Google


def click_url(d: dict, src: str = "site") -> str:
    """Affiliate link tagged with where the click came from (Admitad subid): lang_source_niche."""
    url = d["url"]
    if "admitad" in url or "/g/" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}subid={d['lang']}_{src}_{d.get('niche') or 'x'}"
    if CLICK_BASE:
        return f"{CLICK_BASE}/go/{d['lang']}/{d['niche']}?u={html.escape(url)}"
    return url


_HTML_LINK = __import__("re").compile(r'((?:href|content)="(?:https://dealim\.net)?/(?:he|es|en)/[^"]*?)\.html"')


def clean_urls(html_: str) -> str:
    """Cloudflare Pages answers /x.html with a 308 to /x: link, canonical and sitemap to /x directly
    so Google never meets a redirect ("Page with redirect" = not indexed)."""
    return _HTML_LINK.sub(r'\1"', html_)


def page(lang: str, path: str, title: str, desc: str, body: str, alt_paths: dict | None = None,
         schema: dict | None = None, active: str = "", top: str = "") -> str:
    c = LANGS[lang]
    u = UI[lang]
    alts = alt_paths or {l: path.replace(f"/{lang}/", f"/{l}/", 1) for l in LANGS}
    hreflang = "".join(f'<link rel="alternate" hreflang="{l}" href="{BASE}{p}">' for l, p in alts.items())
    hreflang += f'<link rel="alternate" hreflang="x-default" href="{BASE}{alts.get("en", path)}">'
    langs = "".join(
        f'<a class="{"on" if l == lang else ""}" href="{alts[l]}" hreflang="{l}">{esc(LANGS[l]["name"])}</a>'
        for l in LANGS)
    s = c["strings"]
    bot = f"https://t.me/{SETTINGS.get('bot_username', 'dilim_deals_bot')}"
    cats = f'<a class="{"on" if active == "all" else ""}" href="/{lang}/">🔥 {esc(u["tab_hot"])}</a>' + "".join(
        f'<a class="{"on" if active == k else ""}" href="/{lang}/niche/{k}.html">{ICONS.get(k, "")} {esc(n["title"])}</a>'
        for k, n in c["niches"].items() if k != "brands" or k in ACTIVE.get(lang, ()))   # brands: shown once filled
    ld = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>' if schema else ""
    return clean_urls(f"""<!doctype html><html lang="{lang}" dir="{c['dir']}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}"><link rel="canonical" href="{BASE}{path}">{hreflang}
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;800&display=swap" rel="stylesheet">
<style>{CSS}</style>{ld}</head><body>
<header><div class="wrap"><nav class="langs langbar" aria-label="Language">{langs}</nav><div class="top"><a class="brand" href="/{lang}/">🔥 <b>{esc(c['site_title'].split('|')[0].strip())}</b></a>
<form class="search" action="/{lang}/" role="search"><input id="q" name="q" type="search" placeholder="{esc(u['search'])}" aria-label="{esc(u['search'])}"></form>
<div class="acts"><a class="btn" href="{bot}" aria-label="{esc(s.get('alert_cta', 'Alerts'))}">🔔 <span class="lbl">{esc(s.get('alert_cta', 'Alerts'))}</span></a>
<a class="btn main" href="{c['channel_url']}">✈ Telegram</a></div></div>
<nav class="cats" aria-label="{esc(u['cats'])}">{cats}</nav></div></header>
{top}<main class="wrap">{body}</main>
<footer><div class="wrap foot"><p>{esc(s['disclosure'])}</p>
<p><a href="/{lang}/how.html">{esc(s['how_title'])}</a> &nbsp; <a href="{c['channel_url']}">{esc(s['join_channel'])}</a></p></div></footer>
{JS}<script>try{{localStorage.setItem("lang","{lang}")}}catch(e){{}}</script></body></html>""")


def when(d: dict, lang: str) -> str:
    day = d.get("day", "")
    if not day:
        return ""
    delta = (date.today() - date.fromisoformat(day)).days
    return UI[lang]["today"] if delta <= 0 else UI[lang]["yday"] if delta == 1 else day[8:10] + "/" + day[5:7]


def title_of(d: dict) -> str:
    return d.get("title_local") or d["title"]


def card(d: dict) -> str:
    """Compact vertical card (carousel, category and event grids)."""
    lang = d["lang"]
    cls = "hcard expired" if d.get("expired") else "hcard"
    return f"""<a class="{cls}" href="/{lang}/deal/{d['slug']}.html"><span class="deg"><bdi>{round(d['heat'])}°</bdi></span>
<img src="{esc(d['image'])}" alt="{esc(title_of(d)[:80])}" loading="lazy" referrerpolicy="no-referrer" width="200" height="200">
<div class="in"><div class="t">{esc(title_of(d))}</div>
<div class="prices"><span class="price">{money(d['price_usd'], lang)}</span><span class="pct"><bdi>-{round(d['discount'] * 100)}%</bdi></span></div></div></a>"""


def row(d: dict) -> str:
    """Wide list row in the style of the big deal communities."""
    lang, s, u = d["lang"], LANGS[d["lang"]]["strings"], UI[d["lang"]]
    href = f"/{lang}/deal/{d['slug']}.html"
    niche = LANGS[lang]["niches"].get(d.get("niche", ""), {}).get("title", "")
    search = esc(f"{title_of(d)} {d['title']} {niche}".lower())
    exp = d.get("expired")
    tag = f'<span class="badge">{esc(s["expired"])}</span>' if exp else ""
    return f"""<article class="deal-row{' expired' if exp else ''}" data-s="{search}" data-heat="{d['heat']}" data-new="{d.get('day', '').replace('-', '')}" data-off="{d['discount']}">
<a class="pic" href="{href}"><img src="{esc(d['image'])}" alt="{esc(title_of(d)[:80])}" loading="lazy" referrerpolicy="no-referrer" width="150" height="150"></a>
<div><div class="meta"><span class="temp"><bdi>{round(d['heat'])}°</bdi></span><span>{esc(when(d, lang))}</span>{tag}</div>
<a class="t" href="{href}">{esc(title_of(d))}</a>
<div class="prices"><span class="price">{money(d['price_usd'], lang)}</span><span class="was">{money(d['median_30d'], lang)}</span><span class="pct"><bdi>-{round(d['discount'] * 100)}%</bdi></span></div>
<div class="row-foot"><span class="meta">{ICONS.get(d.get('niche', ''), '')} {esc(niche)} · {esc(u['at'])}</span>
<a class="go-btn" rel="sponsored nofollow" href="{esc(click_url(d))}">{esc(u['cta'])}</a></div></div></article>"""


def hot_rail(items: list, lang: str) -> str:
    if not items:
        return ""
    u = UI[lang]
    return f"""<h2>{esc(u['hot'])}</h2><div class="hotbar"><div class="rail" id="rail">{''.join(card(d) for d in items)}</div>
<button class="arrow prev" type="button" aria-label="{esc(u['prev'])}">‹</button><button class="arrow next" type="button" aria-label="{esc(u['next'])}">›</button></div>"""


def sidebar(lang: str) -> str:
    c, u, s = LANGS[lang], UI[lang], LANGS[lang]["strings"]
    bot = f"https://t.me/{SETTINGS.get('bot_username', 'dilim_deals_bot')}"
    cl = "".join(f'<a href="/{lang}/niche/{k}.html">{ICONS.get(k, "")} {esc(n["title"])}</a>' for k, n in c["niches"].items() if k != "brands" or k in ACTIVE.get(lang, ()))
    return f"""<aside class="side"><div class="box"><h3>✈ Telegram</h3><p>{esc(u['join_box'])}</p><a class="btn main" href="{c['channel_url']}">{esc(s['join_channel'])}</a></div>
<div class="box"><h3>🔔 {esc(s.get('alert_cta', ''))}</h3><p>{esc(u['alert_box'])}</p><a class="btn" href="{bot}">@{esc(SETTINGS.get('bot_username', ''))}</a></div>
<div class="box"><h3>{esc(u['how_box'])}</h3><p>{esc(u['how_short'])}</p><a class="btn" href="/{lang}/how.html">{esc(s['how_title'])}</a></div>
<div class="box"><h3>{esc(u['cats'])}</h3><div class="cl">{cl}</div></div></aside>"""


def listing(deals: list, lang: str) -> str:
    u, s = UI[lang], LANGS[lang]["strings"]
    if not deals:
        return f'<p class="empty">{esc(s["no_deals"])}</p>'
    return f"""<div class="tabs" role="tablist"><button class="on" data-k="heat" role="tab" aria-selected="true">{esc(u['tab_hot'])}</button>
<button data-k="new" role="tab" aria-selected="false">{esc(u['tab_new'])}</button><button data-k="off" role="tab" aria-selected="false">{esc(u['tab_off'])}</button></div>
<div class="list" id="list">{''.join(row(d) for d in deals)}</div><p class="empty" id="none" hidden>{esc(u['none_found'])}</p>"""


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


ACTIVE: dict = {}   # lang -> niches that currently have live deals (empty ones are hidden from menus)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    urls = []
    archives = {l: load_archive(l) for l in LANGS}

    for lang, c in LANGS.items():
        s = c["strings"]
        deals = archives[lang]
        live = [d for d in deals if not d.get("expired")]
        ACTIVE[lang] = {d.get("niche") for d in live}
        root = OUT / lang
        (root / "deal").mkdir(parents=True)
        (root / "niche").mkdir()

        today = date.today().isoformat()
        rank = lambda d: (d["heat"], d.get("orders") or 0)
        ordered = sorted(live, key=rank, reverse=True) + [d for d in deals if d.get("expired")]
        strip = ""
        for ev in SETTINGS.get("events", []):
            ev_deals = [d for d in live if ev["start"] <= d.get("day", "") <= ev["end"]]
            if not (ev["start"] <= today <= ev["end"] or ev_deals):
                continue
            (root / "event").mkdir(exist_ok=True)
            t = ev["title"][lang]
            ev_sorted = sorted(ev_deals, key=rank, reverse=True)
            eb = f'<section class="hero"><h1>{esc(t)}</h1><p>{esc(c["site_tagline"])}</p></section>' + listing(ev_sorted, lang)
            (root / "event" / f"{ev['key']}.html").write_text(page(
                lang, f"/{lang}/event/{ev['key']}.html", f"{t} | {c['site_title']}", t, eb), encoding="utf-8")
            urls.append(f"/{lang}/event/{ev['key']}.html")
            if ev["start"] <= today <= ev["end"]:
                strip = f'<div class="event"><div class="wrap"><span>🎯 {esc(t)}</span><a href="/{lang}/event/{ev["key"]}.html">{esc(UI[lang]["cta"])}</a></div></div>'

        body = f"""{hot_rail(sorted(live, key=rank, reverse=True)[:12], lang)}
<div class="layout"><section><h1 class="sr" style="font-size:1.3rem;margin:22px 0 4px">{esc(s['latest'])}</h1>{listing(ordered[:80], lang)}</section>{sidebar(lang)}</div>"""
        (root / "index.html").write_text(
            page(lang, f"/{lang}/", c["site_title"], c["meta_description"], body, active="all", top=strip), encoding="utf-8")
        urls.append(f"/{lang}/")

        for key, n in c["niches"].items():
            items = [d for d in ordered if d.get("niche") == key]
            title = f"{n['title']} – {SEO_WORDS[lang][0]} | dealim.net"
            hot_n = [d for d in items if not d.get("expired")][:12]
            b = f"""{hot_rail(hot_n, lang) if len(hot_n) >= 4 else ''}<div class="layout"><section><h1 style="font-size:1.3rem;margin:22px 0 4px">{ICONS.get(key, '')} {esc(n['title'])}</h1>
{listing(items[:80], lang)}</section>{sidebar(lang)}</div>"""
            (root / "niche" / f"{key}.html").write_text(
                page(lang, f"/{lang}/niche/{key}.html", title, f"{n['title']} – {c['meta_description']}", b, active=key),
                encoding="utf-8")
            urls.append(f"/{lang}/niche/{key}.html")

        for d in deals:
            p_path = f"/{lang}/deal/{d['slug']}.html"
            pct = round(d["discount"] * 100)
            t0 = " ".join((d.get('title_local') or d['title']).split())
            t0 = t0 if len(t0) <= 60 else t0[:60].rsplit(" ", 1)[0]
            title = f"{t0} – {plain(d['price_usd'], lang)} (-{pct}%) | {SEO_WORDS[lang][1]}"
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
            b = f"""<article class="deal"><img referrerpolicy="no-referrer" src="{esc(d['image'])}" alt="{esc(d['title'][:80])}">
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

    # Root: send visitors straight to their language (last one used, else the browser's);
    # the picker stays for crawlers / no-JS, and hreflang alternates tell Google the rest.
    picker = "".join(
        f'<section class="box" lang="{l}" dir="{c["dir"]}" style="text-align:start"><h2 style="margin:0 0 4px">{esc(c["site_title"])}</h2>'
        f'<p>{esc(c["site_tagline"])}</p>'
        f'<a class="btn main" style="margin-bottom:8px" href="/{l}/" hreflang="{l}">{esc(c["name"])} →</a>'
        f'<a class="btn" href="{esc(c["channel_url"])}" rel="noopener">Telegram · {esc(c["channel_url"].rsplit("/", 1)[-1])}</a></section>'
        for l, c in LANGS.items())
    root_desc = "AliExpress deals, coupons and promo codes – only real price drops, verified against price history. עברית · Español · English."
    script = """<script>try{var s=null;try{s=localStorage.getItem('lang')}catch(e){}
var b=(navigator.languages&&navigator.languages[0]||navigator.language||'').toLowerCase().slice(0,2);if(b=='iw')b='he';
var l=['he','es','en'].indexOf(s)>-1?s:(['he','es'].indexOf(b)>-1?b:'en');location.replace('/'+l+'/'+location.search+location.hash)}catch(e){}</script>"""
    root_html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deals · דילים · Ofertas</title><meta name="description" content="{esc(root_desc)}"><link rel="canonical" href="{BASE}/">
<meta property="og:type" content="website"><meta property="og:url" content="{BASE}/"><meta property="og:title" content="Deals · דילים · Ofertas"><meta property="og:description" content="{esc(root_desc)}">
<meta name="twitter:card" content="summary">{''.join(f'<link rel="alternate" hreflang="{l}" href="{BASE}/{l}/">' for l in LANGS)}
<link rel="alternate" hreflang="x-default" href="{BASE}/en/"><style>{CSS}</style></head>
<body>{script}<main class="wrap" style="max-width:560px;padding:40px 16px"><h1 style="text-align:center">🔥 Deals · דילים · Ofertas</h1>{picker}</main></body></html>"""
    (OUT / "index.html").write_text(root_html, encoding="utf-8")

    sm = "".join(f"<url><loc>{BASE}{u.removesuffix('.html')}</loc></url>" for u in urls)
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>',
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    # Google Search Console ownership file: must stay published or the site loses verification
    (OUT / "google70086153ac75eff1.html").write_text(
        "google-site-verification: google70086153ac75eff1.html", encoding="utf-8")
    return len(urls)


if __name__ == "__main__":
    print("pages:", build())

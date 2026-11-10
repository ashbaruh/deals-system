"""Deal engine core: feed loading, price history, filtering and heat score.

Standard library only, so it runs on a bare GitHub Actions runner.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sqlite3
import statistics
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


SETTINGS = load_json(CONFIG / "settings.json")
import os as _os
if _os.environ.get("SEED") == "1":
    # One-time manual fill: allow the shop's old price as reference (strict heat
    # threshold still applies) and post more per run.
    SETTINGS.update(bootstrap_post=True, max_posts_per_run=20, per_niche_max=3)
if _os.environ.get("PREVIEW") == "1":
    SETTINGS["preview_only"] = True
LANGS = load_json(CONFIG / "languages.json")


@dataclass
class Product:
    pid: str
    store: str
    title: str
    price_usd: float
    old_price_usd: float | None
    url: str               # affiliate link (from the feed / deeplink API)
    image: str
    rating: float | None = None
    orders: int | None = None
    category: str = ""
    niche: str = ""
    ships_to: list[str] = field(default_factory=list)
    title_local: str = ""
    commission: float | None = None


@dataclass
class Deal:
    product: Product
    lang: str
    median_30d: float
    discount: float
    heat: float
    history: list[tuple[str, float]]

    def to_dict(self) -> dict:
        d = asdict(self.product)
        d.update(lang=self.lang, median_30d=round(self.median_30d, 2),
                 discount=round(self.discount, 4), heat=round(self.heat, 1),
                 history=self.history)
        return d


# ---------------------------------------------------------------- feeds ----
# Admitad CSV feeds use these column names; aliases cover other networks.
COLS = {
    "pid": ["id", "product_id", "offer_id"],
    "title": ["name", "title", "product_title"],
    "price": ["price", "sale_price", "target_sale_price"],
    "old_price": ["oldprice", "old_price", "original_price", "target_original_price"],
    "url": ["url", "promotion_link", "link", "affiliate_link"],
    "image": ["picture", "image", "product_main_image_url", "image_link"],
    "rating": ["rating", "evaluate_rate", "product_rating"],
    "orders": ["orders", "lastest_volume", "sales", "volume"],
    "category": ["category", "categoryId", "first_level_category_name"],
    "ships_to": ["ships_to", "ship_to_countries"],
}


def _pick(row: dict, key: str):
    for name in COLS[key]:
        if name in row and str(row[name]).strip() != "":
            return str(row[name]).strip()
    return None


def _num(v):
    if v is None:
        return None
    v = v.replace("%", "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def read_feed_text(source: str, deadline_s: int = 2400) -> str:
    """source = local path or http(s) URL. Streams in chunks with an overall deadline.
    The feed server often drops the connection part-way (the file is ~1 GB and sorted by
    category, so a cut-off file silently loses whole categories). When that happens we
    resume from the last byte with an HTTP Range request."""
    import http.client
    import time
    if not source.startswith("http"):
        return Path(source).read_text(encoding="utf-8")
    start, buf, resumes, total = time.monotonic(), bytearray(), 0, None
    while True:
        headers = {"User-Agent": "deals-bot/1.0"}
        if buf:
            headers["Range"] = f"bytes={len(buf)}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(source, headers=headers), timeout=90) as r:
                if buf and r.status != 206:
                    raise IOError(f"server ignored Range (status {r.status}); cannot resume at {len(buf) / 1e6:.0f} MB")
                if total is None:
                    total = int(r.headers.get("Content-Length") or 0) or None
                    print(f"[feed] length={r.headers.get('Content-Length')} ranges={r.headers.get('Accept-Ranges')} "
                          f"type={r.headers.get('Content-Type')}", flush=True)
                elif r.headers.get("Content-Range"):
                    total = int(r.headers["Content-Range"].rsplit("/", 1)[-1] or 0) or total
                last = len(buf)
                while True:
                    if time.monotonic() - start > deadline_s:
                        raise TimeoutError(f"feed download exceeded {deadline_s}s")
                    block = r.read(1 << 20)
                    if not block:
                        break
                    buf += block
                    if len(buf) // (100 << 20) != last // (100 << 20):
                        print(f"[feed] {len(buf) / 1e6:.0f} MB after {time.monotonic() - start:.0f}s", flush=True)
                    last = len(buf)
        except (http.client.IncompleteRead, ConnectionError, TimeoutError, OSError) as e:
            if isinstance(e, TimeoutError) and "exceeded" in str(e):
                raise
            print(f"[feed] connection dropped at {len(buf) / 1e6:.0f} MB: {e.__class__.__name__}", flush=True)
        complete = (total and len(buf) >= total) or (not total and buf.endswith(b"\n") and resumes > 0)
        if complete:
            break
        if total is None and not buf.endswith(b"\n"):
            pass                                    # mid-line: definitely cut, resume
        elif total is None:
            # No length header: probe once with a Range request; 416 means we have it all.
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        source, headers={"User-Agent": "deals-bot/1.0", "Range": f"bytes={len(buf)}-"}), timeout=90) as r:
                    if r.status == 206:
                        resumes += 1
                        rest = r.read()
                        buf += rest
                        if not rest:
                            break
                        continue
                    break                            # 200: server can't resume; keep what we have
            except urllib.error.HTTPError as e:
                if e.code == 416:
                    break                            # range starts past the end: file complete
                raise
        resumes += 1
        if resumes > 15:
            raise IOError(f"feed kept dropping; got {len(buf) / 1e6:.0f} MB")
        time.sleep(5)
    if len(buf) < 200_000_000:
        raise IOError(f"feed suspiciously small: {len(buf) / 1e6:.0f} MB")
    print(f"[feed] downloaded {len(buf) / 1e6:.1f} MB in {time.monotonic() - start:.0f}s "
          f"({resumes} resumes, expected {total})", flush=True)
    return bytes(buf).decode("utf-8", errors="replace")


def _merge_param(row: dict) -> None:
    """Admitad puts extra attributes in 'param' (e.g. 'rating:4.8|orders:1200').
    Copy any rating/orders values found there into the row."""
    raw = row.get("param") or ""
    pairs = []
    for seg in raw.split(";"):                 # Admitad format: key|value|;key|value|;
        bits = seg.split("|")
        if len(bits) >= 2 and ":" not in bits[0] and "=" not in bits[0]:
            pairs.append((bits[0], "|", bits[1]))
        else:
            for part in bits:
                k, sep, v = part.partition(":")
                if not sep:
                    k, sep, v = part.partition("=")
                pairs.append((k, sep, v))
    for k, sep, v in pairs:
        k = k.strip().lower()
        if not sep or not v.strip():
            continue
        if any(x in k for x in ("rating", "evaluat", "score")) and "rating" not in row:
            row["rating"] = v.strip()
        elif k == "commissionrate" or "commission" in k:
            row["_commission"] = v.strip().strip("|")
        elif any(x in k for x in ("order", "sold", "sales", "volume")) and "orders" not in row:
            row["orders"] = v.strip()


def parse_feed(text: str, store: str) -> list[Product]:
    sample = text[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    out: list[Product] = []
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    print(f"[feed:{store}] columns: {reader.fieldnames}")
    shown = 0
    for row in reader:
        if shown < 3 and row.get("param"):
            print(f"[feed:{store}] param sample: {row['param'][:300]}", flush=True)
            shown += 1
        _merge_param(row)
        pid, title, price = _pick(row, "pid"), _pick(row, "title"), _num(_pick(row, "price"))
        url, image = _pick(row, "url"), _pick(row, "image")
        if not (pid and title and price and url):
            continue
        rating = _num(_pick(row, "rating"))
        if rating is not None and rating > 5:      # some feeds give 0-100 %
            rating = round(rating / 20, 2)
        orders = _num(_pick(row, "orders"))
        ships = _pick(row, "ships_to")
        out.append(Product(
            pid=f"{store}:{pid}", store=store, title=title, price_usd=price,
            old_price_usd=_num(_pick(row, "old_price")), url=url, image=image or "",
            rating=rating, orders=int(orders) if orders is not None else None,
            category=_pick(row, "category") or "",
            commission=(_num(row.get("_commission")) or 0) / 100 or None,
            ships_to=[c.strip().upper() for c in ships.split("|")] if ships else [],
        ))
    return out


_NICHE_RE: dict[str, list] = {}
import re as _re
_EXCL_RE = _re.compile(r"\b(" + "|".join(_re.escape(k) for k in SETTINGS.get("exclude_keywords", ["~none~"])) + r")\b", _re.I)


def assign_niche(p: Product, lang: str) -> str:
    import re
    if lang not in _NICHE_RE:
        _NICHE_RE[lang] = [(key, re.compile(r"\b(" + "|".join(re.escape(k) for k in n["keywords"]) + r")s?\b", re.I))
                           for key, n in LANGS[lang]["niches"].items() if n["keywords"]]
    if _EXCL_RE.search(p.title) or any(x.lower() in p.category.lower() for x in SETTINGS.get("exclude_categories", [])):
        return ""
    cat = p.category.lower()
    for key, rx in _NICHE_RE[lang]:
        hints = LANGS[lang]["niches"][key].get("categories")
        if rx.search(p.title) and (not hints or not cat or any(h.lower() in cat for h in hints)):
            return key
    return ""


# -------------------------------------------------------------- history ----
class History:
    def __init__(self, path: Path = DATA / "history.sqlite"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS prices(pid TEXT, day TEXT, price REAL,
                PRIMARY KEY(pid, day));
            CREATE TABLE IF NOT EXISTS posted(pid TEXT, lang TEXT, day TEXT,
                PRIMARY KEY(pid, lang, day));
            CREATE TABLE IF NOT EXISTS clicks(niche TEXT, lang TEXT, n INTEGER,
                PRIMARY KEY(niche, lang));
        """)

    def record(self, products: list[Product], day: str):
        self.db.executemany(
            "INSERT OR REPLACE INTO prices VALUES(?,?,?)",
            [(p.pid, day, p.price_usd) for p in products])
        self.db.commit()

    def series(self, pid: str, days: int, today: str) -> list[tuple[str, float]]:
        start = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
        cur = self.db.execute(
            "SELECT day, price FROM prices WHERE pid=? AND day>=? ORDER BY day",
            (pid, start))
        return [(d, p) for d, p in cur.fetchall()]

    def posted_recently(self, pid: str, lang: str, days: int, today: str) -> bool:
        start = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
        return self.db.execute(
            "SELECT 1 FROM posted WHERE pid=? AND lang=? AND day>=?",
            (pid, lang, start)).fetchone() is not None

    def mark_posted(self, pid: str, lang: str, day: str):
        self.db.execute("INSERT OR IGNORE INTO posted VALUES(?,?,?)", (pid, lang, day))
        self.db.commit()

    def niche_trend(self, lang: str) -> dict[str, float]:
        rows = self.db.execute("SELECT niche, n FROM clicks WHERE lang=?", (lang,)).fetchall()
        if not rows:
            return {}
        top = max(n for _, n in rows) or 1
        return {k: n / top for k, n in rows}

    def prune(self, keep_days: int, today: str):
        cut = (date.fromisoformat(today) - timedelta(days=keep_days)).isoformat()
        self.db.execute("DELETE FROM prices WHERE day<?", (cut,))
        self.db.execute("DELETE FROM posted WHERE day<?", (cut,))
        self.db.commit()


# -------------------------------------------------------------- scoring ----
def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def commission_rate(p: Product) -> float:
    if p.commission:
        return p.commission
    s = SETTINGS
    over = s.get("store_commission_override", {}).get(p.store, {})
    return over.get(p.niche, s["commission_by_category"].get(p.niche, 0.04))


def evaluate(p: Product, lang: str, hist: History, today: str,
             trend: dict[str, float]) -> Deal | None:
    """Return a Deal if the product passes every hard filter, else None."""
    s = SETTINGS
    country = LANGS[lang]["country"]
    if p.ships_to and country not in p.ships_to:
        return None
    if not p.niche:
        return None
    if p.price_usd > s.get("max_price_usd", 1e9):
        return None
    if p.price_usd < s.get("min_price_usd", 0):
        # Cheap items only as "dollar deals", and only from niches where a $1 item is useful.
        if not (s.get("dollar_min_price_usd", 1e9) <= p.price_usd <= s.get("dollar_max_price_usd", 0)
                and p.niche in s.get("dollar_from_niches", [])):
            return None
        p.niche = "dollar"
    if p.rating is not None and p.rating < s["min_rating"]:
        return None
    if p.orders is not None and p.orders < s["min_orders"]:
        return None
    if hist.posted_recently(p.pid, lang, s["repost_block_days"], today):
        return None

    series = hist.series(p.pid, s["history_window_days"], today)
    past = [price for d, price in series if d < today]
    bootstrap = len(past) < s["bootstrap_min_history_days"]
    if bootstrap and not s.get("bootstrap_post", False):
        return None                       # first days: only collect real price history
    if bootstrap:
        # Not enough of our own history yet: fall back to the shop's old price,
        # but demand a higher heat score to compensate.
        if not p.old_price_usd or p.old_price_usd <= p.price_usd:
            return None
        ref = p.old_price_usd
        if 1 - p.price_usd / ref > s.get("bootstrap_max_discount", 1):   # shop's "old price" likely inflated
            return None
    else:
        ref = statistics.median(past)

    discount = 1 - p.price_usd / ref
    if discount < s["min_discount"]:
        return None
    if discount >= s["suspicious_drop"]:          # likely a pricing error
        return None

    w = s["weights"]
    D = _clip((discount - 0.30) / 0.40)
    R = _clip(((p.rating or 4.7) - 4.7) / 0.3)
    O = _clip((math.log10(max(p.orders or 500, 1)) - math.log10(500)) / 2)
    C = _clip((commission_rate(p) - 0.023) / (0.09 - 0.023))
    T = trend.get(p.niche, 0.5)
    parts = [(w["discount"], D), (w["commission"], C), (w["trend"], T)]
    if p.rating is not None:
        parts.append((w["rating"], R))
    if p.orders is not None:
        parts.append((w["orders"], O))
    # Re-weight over the signals the feed actually provides, so a missing column
    # neither blocks every deal nor inflates scores.
    heat = 100 * sum(wt * v for wt, v in parts) / sum(wt for wt, _ in parts)

    threshold = s["heat_threshold_bootstrap"] if bootstrap else s["heat_threshold"]
    if heat < threshold:
        return None
    return Deal(product=p, lang=lang, median_30d=ref, discount=discount,
                heat=heat, history=series)


def select_deals(products: list[Product], lang: str, hist: History, today: str,
                 posted_today: dict | None = None, live_on_site: dict | None = None):
    """Returns (to_post, site_only): Telegram gets a capped selection; the rest of the
    good deals fill the site up to site_per_niche live deals per category."""
    trend = hist.niche_trend(lang)
    deals = []
    for p in products:
        p.niche = assign_niche(p, lang)
        p.title_local = ""          # titles are per language; never carry one over
        d = evaluate(p, lang, hist, today, trend)
        if d:
            deals.append(d)
    deals.sort(key=lambda d: d.heat, reverse=True)
    from collections import Counter
    print(f"[{lang}] products per niche: {dict(Counter(p.niche for p in products if p.niche))}", flush=True)
    print(f"[{lang}] passing deals per niche: {dict(Counter(d.product.niche for d in deals))}", flush=True)
    # at most 2 per niche per run, so a channel is never all earbuds
    picked, per_niche, seen = [], dict(posted_today or {}), set()   # caps count the whole day
    for d in deals:
        n = d.product.niche
        key = " ".join(d.product.title.lower().split()[:4])   # skip near-duplicates (same product line)
        if key in seen:
            continue
        cap = SETTINGS.get("per_niche_per_day", 3)
        if per_niche.get(n, 0) >= cap:
            continue
        per_niche[n] = per_niche.get(n, 0) + 1
        seen.add(key)
        picked.append(d)
        if len(picked) >= SETTINGS["max_posts_per_run"]:
            break
    chosen = {d.product.pid for d in picked}
    site, on_site = [], dict(live_on_site or {})
    for d in picked:
        on_site[d.product.niche] = on_site.get(d.product.niche, 0) + 1
    for d in deals:
        n = d.product.niche
        key = " ".join(d.product.title.lower().split()[:4])
        if d.product.pid in chosen or key in seen or on_site.get(n, 0) >= SETTINGS.get("site_per_niche", 12):
            continue
        seen.add(key)
        on_site[n] = on_site.get(n, 0) + 1
        site.append(d)
    return picked, site


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()

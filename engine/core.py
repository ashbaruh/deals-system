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


def read_feed_text(source: str) -> str:
    """source = local path or http(s) URL (Admitad feed URL from a secret)."""
    if source.startswith("http"):
        req = urllib.request.Request(source, headers={"User-Agent": "deals-bot/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read().decode("utf-8", errors="replace")
    return Path(source).read_text(encoding="utf-8")


def parse_feed(text: str, store: str) -> list[Product]:
    sample = text[:4096]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    out: list[Product] = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
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
            ships_to=[c.strip().upper() for c in ships.split("|")] if ships else [],
        ))
    return out


def assign_niche(p: Product, lang: str) -> str:
    t = p.title.lower()
    for key, niche in LANGS[lang]["niches"].items():
        if any(k in t for k in niche["keywords"]):
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
    if p.rating is not None and p.rating < s["min_rating"]:
        return None
    if p.orders is not None and p.orders < s["min_orders"]:
        return None
    if hist.posted_recently(p.pid, lang, s["repost_block_days"], today):
        return None

    series = hist.series(p.pid, s["history_window_days"], today)
    past = [price for d, price in series if d < today]
    bootstrap = len(past) < s["bootstrap_min_history_days"]
    if bootstrap:
        # Not enough of our own history yet: fall back to the shop's old price,
        # but demand a higher heat score to compensate.
        if not p.old_price_usd or p.old_price_usd <= p.price_usd:
            return None
        ref = p.old_price_usd
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
    heat = w["discount"] * D + w["rating"] * R + w["orders"] * O + w["commission"] * C + w["trend"] * T

    threshold = s["heat_threshold_bootstrap"] if bootstrap else s["heat_threshold"]
    if heat < threshold:
        return None
    return Deal(product=p, lang=lang, median_30d=ref, discount=discount,
                heat=heat, history=series)


def select_deals(products: list[Product], lang: str, hist: History, today: str) -> list[Deal]:
    trend = hist.niche_trend(lang)
    deals = []
    for p in products:
        p.niche = assign_niche(p, lang)
        d = evaluate(p, lang, hist, today, trend)
        if d:
            deals.append(d)
    deals.sort(key=lambda d: d.heat, reverse=True)
    # at most 2 per niche per run, so a channel is never all earbuds
    picked, per_niche = [], {}
    for d in deals:
        n = d.product.niche
        if per_niche.get(n, 0) >= 2:
            continue
        per_niche[n] = per_niche.get(n, 0) + 1
        picked.append(d)
        if len(picked) >= SETTINGS["max_posts_per_run"]:
            break
    return picked


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()

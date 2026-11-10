"""One full run: feeds -> history -> deals -> archive -> Telegram -> site.

Feed sources per language come from env vars (GitHub Secrets), e.g.
  FEEDS_HE="aliexpress=https://...admitad feed url...,banggood=https://..."
If a language has no feed configured, the mock feed in mock/ is used (local testing).
"""
from __future__ import annotations

import json
import os
import sys
import traceback

from .core import DATA, LANGS, ROOT, SETTINGS, History, parse_feed, read_feed_text, select_deals, today_iso
from .telegram import notify_owner, post_deal
from .translate import localize
from . import bot

ARCHIVE_MAX = 300


def feed_sources(lang: str) -> list[tuple[str, str]]:
    raw = os.environ.get(f"FEEDS_{lang.upper()}", "").strip()
    if not raw:
        # Mock data only on explicit request – never in production.
        mock = ROOT / "mock" / "feed.csv"
        if os.environ.get("DEALS_MOCK") == "1" and mock.exists():
            return [("aliexpress", str(mock))]
        return []
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.startswith("http"):             # bare link pasted without "store=" prefix
            store = "banggood" if "banggood" in part.lower() else "aliexpress"
            out.append((store, part))
            continue
        store, _, url = part.partition("=")
        if url.startswith("http"):
            out.append((store.strip(), url.strip()))
    return out


_FEED_CACHE: dict[str, list] = {}


def _relevant(products):
    """Keep only products that match a niche: the feed has ~500k items,
    storing all of them daily would bloat the history to gigabytes."""
    from .core import Product, assign_niche
    lang0 = next(iter(LANGS))
    keep = [p for p in products if assign_niche(p, lang0)]
    if os.environ.get("PREVIEW") == "1":
        # Diagnostics for tuning: whole-feed category counts, and for each niche the
        # categories of products whose title matched but whose category was rejected.
        import re
        from collections import Counter, defaultdict
        cats = Counter(p.category for p in products)
        missed = defaultdict(Counter)
        for key, n in LANGS[lang0]["niches"].items():
            if not n["keywords"]:
                continue
            rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in n["keywords"]) + r")s?\b", re.I)
            for p in products:
                if rx.search(p.title):
                    missed[key][p.category] += 1
        prices = Counter(min(int(p.price_usd // 5) * 5, 200) for p in products)
        (DATA / "feed_diag.json").write_text(json.dumps({
            "total": len(products), "kept": len(keep),
            "top_categories": cats.most_common(400),
            "title_match_categories": {k: v.most_common(40) for k, v in missed.items()},
            "price_buckets": sorted(prices.items()),
            "discount_buckets": sorted(Counter(round(1 - p.price_usd / p.old_price_usd, 1) for p in products
                                               if p.old_price_usd and p.old_price_usd > p.price_usd).items()),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return keep


def load_products(lang: str, errors: list[str]):
    products = []
    for store, src in feed_sources(lang):
        if src in _FEED_CACHE:                  # same feed shared by several languages
            products += _FEED_CACHE[src]
            continue
        print(f"[feed:{store}] downloading...", flush=True)
        for attempt in range(2):
            try:
                items = _relevant(parse_feed(read_feed_text(src), store))
                _FEED_CACHE[src] = items
                products += items
                break
            except Exception as e:  # network or format problem: retry, then report
                print(f"[feed:{store}] attempt {attempt + 1} failed: {e}", flush=True)
                if attempt == 1:
                    errors.append(f"{lang}/{store}: feed failed ({e.__class__.__name__}: {str(e)[:120]})")
                else:
                    import time
                    time.sleep(180)          # give the feed server a breather before retrying
    return products


def _still_valid(a: dict, lang: str) -> bool:
    """Drop archived deals that today's (stricter) category rules would not accept."""
    from .core import Product, assign_niche
    p = Product(pid=a["pid"], store=a.get("store", ""), title=a["title"], price_usd=a["price_usd"],
                old_price_usd=None, url="", image="", category=a.get("category", ""))
    n = assign_niche(p, lang)
    if a.get("niche") == "dollar":
        return bool(n) and n in SETTINGS.get("dollar_from_niches", [])
    return n == a.get("niche") and SETTINGS.get("min_price_usd", 0) <= a["price_usd"] <= SETTINGS.get("max_price_usd", 1e9)


def update_archive(lang: str, new_deals, products, today: str):
    from webgen.build import slug  # local import keeps engine importable without site/
    path = DATA / f"deals_{lang}.json"
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    archive = [a for a in archive if _still_valid(a, lang)]
    if products is not None:                # None = publishing a reviewed preview, no fresh prices
        current = {p.pid: p.price_usd for p in products}
        for d in archive:                   # expire deals whose price went back up / vanished
            now = current.get(d["pid"])
            if now is None or now > d["price_usd"] * 1.05:
                d["expired"] = True
    for deal in new_deals:
        d = deal.to_dict()
        d["slug"] = slug(d["title"], d["pid"])
        d["day"] = today
        archive = [a for a in archive if a["pid"] != d["pid"]]
        archive.insert(0, d)
    archive = archive[:ARCHIVE_MAX]
    path.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
    return archive


def publish_preview(hist, today, base, errors) -> int:
    """Post the picks saved by the last preview run, without downloading the feed again."""
    from dataclasses import fields
    from .core import Deal, Product
    from webgen.build import click_url, build
    names = {f.name for f in fields(Product)}
    total = 0
    for lang in LANGS:
        f = DATA / f"preview_{lang}.json"
        if not f.exists():
            continue
        deals = []
        for d in json.loads(f.read_text(encoding="utf-8")):
            p = Product(**{k: v for k, v in d.items() if k in names})
            deals.append(Deal(product=p, lang=lang, median_30d=d["median_30d"], discount=d["discount"],
                              heat=d["heat"], history=[tuple(x) for x in d["history"]]))
        archive = update_archive(lang, deals, None, today)
        by_pid = {a["pid"]: a for a in archive}
        links, posted = {}, []
        for deal in deals:
            a = by_pid[deal.product.pid]
            links[deal.product.pid] = click_url(a)
            if post_deal(deal, links[deal.product.pid], f"{base}/{lang}/deal/{a['slug']}.html"):
                hist.mark_posted(deal.product.pid, lang, today)
                posted.append(deal)
                total += 1
        bot.send_alerts(hist, lang, posted, links)
        f.unlink()
        print(f"{lang}: published {len(posted)} reviewed deals")
    print("site pages:", build())
    if errors:
        notify_owner("Deals run issues:\n" + "\n".join(errors))
    print(f"done: {total} posts")
    return 0


def main() -> int:
    today = today_iso()
    errors: list[str] = []
    if SETTINGS.get("paused"):
        print("paused via settings.json")
        return 0
    hist = History()
    posted_total = 0
    base = os.environ.get("SITE_BASE_URL", SETTINGS["site_base_url"]).rstrip("/")
    bot.ensure_owner()
    if os.environ.get("CLEANUP") == "1":
        bot.cleanup(hist)
        hist.db.execute("DELETE FROM posted")
        hist.db.commit()
        for l in LANGS:
            (DATA / f"deals_{l}.json").write_text("[]", encoding="utf-8")
    print("bot commands handled:", bot.process_commands(hist))
    bot.ensure_welcome(hist)

    if os.environ.get("PUBLISH_PREVIEW") == "1":
        return publish_preview(hist, today, base, errors)

    loaded = {}
    for lang in LANGS:
        try:
            loaded[lang] = load_products(lang, errors)
        except Exception:
            loaded[lang] = []
    fallback = next((p for p in loaded.values() if p), [])
    for lang in LANGS:
        if not loaded[lang] and fallback:
            # Same AliExpress catalogue and same affiliate account: if this language's
            # feed URL failed, use another language's download rather than post nothing.
            loaded[lang] = fallback
            errors.append(f"{lang}: own feed failed, used another language's feed")

    for lang in LANGS:
        try:
            products = loaded[lang]
            if not products:
                errors.append(f"{lang}: no products loaded – skipped (nothing posted)")
                continue
            hist.record(products, today)
            arch_path = DATA / f"deals_{lang}.json"
            prev = json.loads(arch_path.read_text(encoding="utf-8")) if arch_path.exists() else []
            from collections import Counter
            posted_today = Counter(a.get("niche") for a in prev if a.get("day") == today)
            deals = select_deals(products, lang, hist, today, posted_today)
            localize(deals, lang, hist)
            if SETTINGS.get("preview_only"):
                # Review mode: nothing goes public. The owner gets the picks privately
                # and they are saved for inspection; channels and site stay untouched.
                (DATA / f"preview_{lang}.json").write_text(
                    json.dumps([d.to_dict() for d in deals], ensure_ascii=False, indent=1), encoding="utf-8")
                lines = [f"{round(d.heat)}° -{round(d.discount * 100)}% ${d.product.price_usd:.2f} [{d.product.niche}] {d.product.title[:60]}" for d in deals]
                notify_owner(f"👀 Preview {lang} ({len(deals)}):\n" + "\n".join(lines))
                print(f"{lang}: {len(products)} products, {len(deals)} deals PREVIEW only")
                continue
            archive = update_archive(lang, deals, products, today)
            by_pid = {a["pid"]: a for a in archive}
            from webgen.build import click_url
            links, posted = {}, []
            for deal in deals:
                a = by_pid[deal.product.pid]
                links[deal.product.pid] = click_url(a)
                if post_deal(deal, links[deal.product.pid], f"{base}/{lang}/deal/{a['slug']}.html"):
                    hist.mark_posted(deal.product.pid, lang, today)
                    posted_total += 1
                    posted.append(deal)
            print(f"{lang}: alerts sent", bot.send_alerts(hist, lang, posted, links))
            print(f"{lang}: {len(products)} products, {len(deals)} deals posted")
        except Exception:
            errors.append(f"{lang}: crashed\n{traceback.format_exc(limit=3)}")

    try:
        from webgen.build import build
        print("site pages:", build())
    except Exception:
        errors.append("site build failed – previous version stays online\n" + traceback.format_exc(limit=3))

    try:
        bot.weekly(hist, today)
    except Exception:
        errors.append("weekly summary failed\n" + traceback.format_exc(limit=2))
    hist.prune(SETTINGS["history_retention_days"], today)
    if errors:
        notify_owner("⚠️ Deals run issues:\n" + "\n".join(errors))
    print(f"done: {posted_total} posts, {len(errors)} issues")
    return 1 if errors and posted_total == 0 and any("crashed" in e for e in errors) else 0


if __name__ == "__main__":
    sys.exit(main())

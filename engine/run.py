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
    return [p for p in products if assign_niche(p, lang0)]


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


def update_archive(lang: str, new_deals, products, today: str):
    from webgen.build import slug  # local import keeps engine importable without site/
    path = DATA / f"deals_{lang}.json"
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    current = {p.pid: p.price_usd for p in products}
    for d in archive:                       # expire deals whose price went back up / vanished
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

    for lang in LANGS:
        try:
            products = load_products(lang, errors)
            if not products:
                errors.append(f"{lang}: no products loaded – skipped (nothing posted)")
                continue
            hist.record(products, today)
            deals = select_deals(products, lang, hist, today)
            localize(deals, lang, hist)
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

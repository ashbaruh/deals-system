"""One full run: feeds -> history -> deals -> archive -> Telegram -> site.

Feed sources per language come from env vars (GitHub Secrets), e.g.
  FEEDS_HE="aliexpress=https://...admitad feed url...,banggood=https://..."
If a language has no feed configured, the mock feed in mock/ is used (local testing).
"""
from __future__ import annotations

import time
from pathlib import Path
import json
from datetime import date, timedelta
import os
import sys
import traceback

from .core import DATA, LANGS, ROOT, SETTINGS, History, select_deals, stream_products, today_iso
from .telegram import notify_owner, post_deal
from .translate import localize
from . import bot

ARCHIVE_MAX = 450


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


def _keep(p) -> bool:
    """Keep only products that match a niche (the feed has millions of rows)."""
    from .core import assign_niche
    return bool(assign_niche(p, next(iter(LANGS))))


def _load_cached_buckets():
    """Products saved by the parallel bucket-fetch jobs (engine.fetch), or None."""
    d = os.environ.get("FEED_CACHE_DIR")
    files = sorted(Path(d).glob("products_*.json.gz")) if d and Path(d).is_dir() else []
    if not files:
        return None
    import gzip
    from .core import Product
    seen, out = set(), []
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for r in json.load(fh):
                if r["pid"] not in seen:
                    seen.add(r["pid"])
                    out.append(Product(**r))
        print(f"[feed] {f.name}: total now {len(out)}", flush=True)
    return out


def load_products(lang: str, errors: list[str]):
    if "buckets" not in _FEED_CACHE:
        _FEED_CACHE["buckets"] = _load_cached_buckets()
    if _FEED_CACHE["buckets"]:
        return list(_FEED_CACHE["buckets"])
    products = []
    for store, src in feed_sources(lang):
        if src in _FEED_CACHE:                  # same feed shared by several languages
            products += _FEED_CACHE[src]
            continue
        print(f"[feed:{store}] downloading...", flush=True)
        for attempt in range(2):
            try:
                stats = {} if os.environ.get("PREVIEW") == "1" else None
                url = src
                hours = SETTINGS.get("feed_delta_hours")
                if hours and url.startswith("http") and "last_import" not in url:
                    # Only products changed since then: far smaller than the ~4 GB full feed,
                    # and every category is included (the full download gets cut off part-way).
                    from datetime import datetime, timedelta, timezone
                    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y.%m.%d.%H.%M")
                    url += ("&" if "?" in url else "?") + f"last_import={since}"
                    print(f"[feed:{store}] delta mode: changes since {since} UTC", flush=True)
                items = stream_products(url, store, _keep, stats)
                if stats is not None:
                    top = sorted(stats["categories"].items(), key=lambda kv: -kv[1])[:400]
                    (DATA / "feed_diag.json").write_text(json.dumps(
                        {"total": stats["total"], "kept": stats["kept"], "top_categories": top},
                        ensure_ascii=False, indent=1), encoding="utf-8")
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
    top = SETTINGS.get(f"max_price_usd_{n}", SETTINGS.get("max_price_usd", 1e9))
    return n == a.get("niche") and SETTINGS.get("min_price_usd", 0) <= a["price_usd"] <= top


def joom_showcase(products, lang: str, today: str) -> list:
    """Joom products shown on the Spanish site while their own price history builds up.
    They carry no discount claim (Joom's feed has no reference price): just the price.
    Rotates daily, a few per category, and keeps at most `joom_showcase` on the site."""
    import hashlib
    from .core import Deal
    want = SETTINGS.get("joom_showcase", 0)
    if lang != "es" or not want:
        return []
    path = DATA / f"deals_{lang}.json"
    live = sum(1 for a in (json.loads(path.read_text(encoding="utf-8")) if path.exists() else [])
               if a.get("showcase") and not a.get("expired"))
    need = max(0, want - live)
    if not need:
        return []
    per = SETTINGS.get("joom_showcase_per_niche", 3)
    lo, hi = SETTINGS.get("joom_showcase_price_usd", [8, 90])
    pool = [p for p in products if p.store == "joom" and p.niche and p.image and lo <= p.price_usd <= hi
            and 20 <= len(p.title) <= 140]
    pool.sort(key=lambda p: hashlib.md5(f"{today}{p.pid}".encode()).hexdigest())
    out, cnt = [], {}
    for p in pool:
        if cnt.get(p.niche, 0) >= per:
            continue
        cnt[p.niche] = cnt.get(p.niche, 0) + 1
        out.append(Deal(product=p, lang=lang, median_30d=p.price_usd, discount=0.0, heat=40.0, history=[]))
        if len(out) >= need:
            break
    print(f"[{lang}] joom showcase: +{len(out)} (live {live}, pool {len(pool)})", flush=True)
    return out


def update_archive(lang: str, new_deals, products, today: str):
    from webgen.build import slug  # local import keeps engine importable without site/
    path = DATA / f"deals_{lang}.json"
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    archive = [a for a in archive if _still_valid(a, lang)]
    if products is not None:                # None = publishing a reviewed preview, no fresh prices
        current = {p.pid: p.price_usd for p in products}
        floor = SETTINGS.get("site_per_niche", 12)
        cutoff = (date.fromisoformat(today) - timedelta(days=3)).isoformat()
        live = {}
        for d in archive:
            if not d.get("expired"):
                live[d["niche"]] = live.get(d["niche"], 0) + 1
        for d in sorted(archive, key=lambda a: a.get("day", today)):   # oldest first
            if d.get("expired"):
                continue
            now = current.get(d["pid"])
            # The feed is partial and rotates, so absence is weak evidence: expire on a price
            # rise, or when absent 3+ days AND the niche still keeps its minimum on the site.
            gone = now is None and not SETTINGS.get("feed_delta_hours") and d.get("day", today) < cutoff \
                and live.get(d["niche"], 0) > floor
            if (now is not None and now > d["price_usd"] * 1.05) or gone:
                d["expired"] = True
                live[d["niche"]] -= 1
    for deal in new_deals:
        d = deal.to_dict()
        if d.get("store") == "joom" and d.get("discount", 0) < 0.05:
            d["showcase"] = True
        d["slug"] = slug(d["title"], d["pid"])
        d["day"] = today
        archive = [a for a in archive if a["pid"] != d["pid"]]
        archive.insert(0, d)
    if len(archive) > ARCHIVE_MAX:          # trim expired first, then the oldest of crowded niches
        floor = SETTINGS.get("site_per_niche", 12)
        archive = [a for a in archive if not a.get("expired")] + [a for a in archive if a.get("expired")]
        cnt = {}
        for a in archive:
            cnt[a["niche"]] = cnt.get(a["niche"], 0) + 1
        for a in reversed(list(archive)):
            if len(archive) <= ARCHIVE_MAX:
                break
            if a.get("expired") or cnt[a["niche"]] > floor:
                archive.remove(a); cnt[a["niche"]] -= 1
    path.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
    return archive


def retranslate(hist) -> int:
    """Translate titles of deals already on the site (no feed download), then rebuild."""
    from types import SimpleNamespace as NS
    from webgen.build import build
    for lang in LANGS:
        if lang == "en":
            continue
        path = DATA / f"deals_{lang}.json"
        archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        todo = [NS(product=NS(pid=a["pid"], title=a["title"], title_local="")) for a in archive if not a.get("title_local")]
        localize(todo, lang, hist)
        got = {t.product.pid: t.product.title_local for t in todo if t.product.title_local}
        for a in archive:
            if a["pid"] in got:
                a["title_local"] = got[a["pid"]]
        path.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{lang}: translated {len(got)} of {len(todo)} titles", flush=True)
    print("site pages:", build())
    return 0


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
        deals, site_only = [], []
        for d in json.loads(f.read_text(encoding="utf-8")):
            p = Product(**{k: v for k, v in d.items() if k in names})
            (site_only if d.get("site_only") else deals).append(Deal(product=p, lang=lang, median_30d=d["median_30d"], discount=d["discount"],
                              heat=d["heat"], history=[tuple(x) for x in d["history"]]))
        archive = update_archive(lang, deals + site_only, None, today)
        by_pid = {a["pid"]: a for a in archive}
        links, posted = {}, []
        for deal in deals:
            a = by_pid[deal.product.pid]
            links[deal.product.pid] = click_url(a, "tg")
            if post_deal(deal, links[deal.product.pid], f"{base}/{lang}/deal/{a['slug']}.html"):
                hist.mark_posted(deal.product.pid, lang, today)
                posted.append(deal)
                total += 1
            time.sleep(4)                   # stay well under Telegram's per-channel rate limit
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
    base = (os.environ.get("SITE_BASE_URL") or SETTINGS["site_base_url"]).rstrip("/")
    bot.ensure_owner()
    if os.environ.get("CLEANUP") == "1":
        bot.cleanup(hist)
        hist.db.execute("DELETE FROM posted")
        hist.db.commit()
        for l in LANGS:
            (DATA / f"deals_{l}.json").write_text("[]", encoding="utf-8")
    print("bot commands handled:", bot.process_commands(hist))
    bot.ensure_welcome(hist)

    bot.maintenance(hist)
    if os.environ.get("RETRANSLATE") == "1":
        bot.pre_event_posts(hist, today)
        bot.event_posts(hist, today)
        bot.promo_video(hist)
        return retranslate(hist)
    if os.environ.get("PUBLISH_PREVIEW") == "1":
        return publish_preview(hist, today, base, errors)

    loaded = {}
    for lang in LANGS:
        if SETTINGS.get("single_feed", True) and any(loaded.values()):
            # Same AliExpress catalogue for every language: download the ~1 GB feed once
            # (repeated downloads get throttled by the feed server).
            loaded[lang] = next(p for p in loaded.values() if p)
            continue
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

    only = os.environ.get("ONLY_NICHE")
    if only:
        # Targeted fill: keep one niche, put everything on the site, post nothing now
        # (regular runs post from it under the normal daily limits).
        from .core import assign_niche
        SETTINGS["max_posts_per_run"] = 0
        for lang in LANGS:
            loaded[lang] = [p for p in loaded[lang] if assign_niche(p, lang) == only]
            print(f"[{lang}] only {only}: {len(loaded[lang])} products", flush=True)

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
            live_on_site = Counter(a.get("niche") for a in prev if not a.get("expired"))
            # Daily cap per channel (several scheduled runs a day, incl. backups GitHub may or may not fire)
            done_today = hist.db.execute("SELECT COUNT(*) FROM posted WHERE lang=? AND day=?", (lang, today)).fetchone()[0]
            run_cap = SETTINGS["max_posts_per_run"]
            SETTINGS["max_posts_per_run"] = max(0, min(run_cap, SETTINGS.get("max_posts_per_day", 10) - done_today))
            # GitHub often fires scheduled runs hours late: never post into the audience's night
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo
            tz = {"he": "Asia/Jerusalem", "es": "Europe/Madrid", "en": "America/New_York"}.get(lang, "UTC")
            hour = _dt.now(ZoneInfo(tz)).hour
            if not (8 <= hour < 23) and not os.environ.get("PUBLISH_ANYTIME"):
                print(f"[{lang}] local hour {hour}: night, site only", flush=True)
                SETTINGS["max_posts_per_run"] = 0
            deals, site_only = select_deals(products, lang, hist, today, posted_today, live_on_site)
            SETTINGS["max_posts_per_run"] = run_cap
            site_only = site_only + joom_showcase(products, lang, today)
            localize(deals, lang, hist)
            localize(site_only, lang, hist)
            if SETTINGS.get("preview_only"):
                # Review mode: nothing goes public. The owner gets the picks privately
                # and they are saved for inspection; channels and site stay untouched.
                (DATA / f"preview_{lang}.json").write_text(json.dumps(
                    [d.to_dict() for d in deals] + [dict(d.to_dict(), site_only=True) for d in site_only],
                    ensure_ascii=False, indent=1), encoding="utf-8")
                lines = [f"{round(d.heat)}° -{round(d.discount * 100)}% ${d.product.price_usd:.2f} [{d.product.niche}] {d.product.title[:60]}" for d in deals]
                notify_owner(f"👀 Preview {lang} ({len(deals)}):\n" + "\n".join(lines))
                print(f"{lang}: {len(products)} products, {len(deals)} to post + {len(site_only)} site-only PREVIEW")
                continue
            archive = update_archive(lang, deals + site_only, products, today)
            by_pid = {a["pid"]: a for a in archive}
            from webgen.build import click_url
            links, posted = {}, []
            for deal in deals:
                a = by_pid[deal.product.pid]
                links[deal.product.pid] = click_url(a, "tg")
                if post_deal(deal, links[deal.product.pid], f"{base}/{lang}/deal/{a['slug']}.html"):
                    hist.mark_posted(deal.product.pid, lang, today)
                    posted_total += 1
                    posted.append(deal)
            print(f"{lang}: alerts sent", bot.send_alerts(hist, lang, posted, links))
            print(f"{lang}: {len(products)} products, {len(deals)} deals posted, {len(site_only)} site-only")
        except Exception:
            errors.append(f"{lang}: crashed\n{traceback.format_exc(limit=3)}")

    try:
        from webgen.build import build
        print("site pages:", build())
    except Exception:
        errors.append("site build failed – previous version stays online\n" + traceback.format_exc(limit=3))

    try:
        bot.event_posts(hist, today)
        bot.pre_event_posts(hist, today)
    except Exception:
        errors.append("event post failed\n" + traceback.format_exc(limit=2))
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

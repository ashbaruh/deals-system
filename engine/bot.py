"""Telegram bot features that run inside the scheduled job (no server needed):

* keyword alerts  – users DM the bot "/alert earbuds"; new matching deals are sent to them
                    (inspired by Slickdeals deal alerts). Commands are read with getUpdates
                    on every run, so replies arrive within ~12 hours at most.
* welcome post    – one pinned intro message per channel, posted once.
* weekly summary  – every Sunday morning: top 5 deals of the week in each channel,
                    and a private report to the owner.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta, timezone

from .core import DATA, LANGS, SETTINGS, History
from .telegram import _call as _raw_call, notify_owner


def _call(token, method, payload):
    """Bot extras must never break the run: swallow Telegram errors."""
    try:
        return _raw_call(token, method, payload) or {}
    except Exception as e:
        print(f"[bot] {method} failed: {e}")
        return {}


def ensure_owner():
    """If TELEGRAM_OWNER_CHAT_ID isn't set, use the creator of the Hebrew channel
    (works once the owner has pressed Start in the bot)."""
    if os.environ.get("TELEGRAM_OWNER_CHAT_ID") or not _token():
        return
    ch = os.environ.get(LANGS[next(iter(LANGS))]["channel_env"])
    if not ch:
        return
    for m in _call(_token(), "getChatAdministrators", {"chat_id": ch}).get("result", []):
        if m.get("status") == "creator":
            os.environ["TELEGRAM_OWNER_CHAT_ID"] = str(m["user"]["id"])

BOT_USERNAME = SETTINGS.get("bot_username", "dilim_deals_bot")
MAX_ALERTS_PER_USER = 5
MAX_ALERT_MSGS_PER_RUN = 5

TEXT = {
    "he": {
        "start": "שלום! אני הבוט של {title}.\n\nכדי לקבל התראה כשמופיע דיל על משהו ספציפי, שלחו:\n/alert אוזניות\n(עד 5 מילים). /alerts מציג את ההתראות שלכם, /stop מבטל הכול.\n\nהערוץ: {channel}",
        "added": "✅ נוספה התראה: {kw}",
        "limit": "אפשר עד 5 התראות. שלחו /stop כדי להתחיל מחדש.",
        "list": "ההתראות שלכם: {kws}",
        "none": "אין התראות פעילות. שלחו למשל: /alert קפה",
        "stopped": "כל ההתראות בוטלו.",
        "hit": "🔔 דיל שמתאים להתראה \"{kw}\":",
        "welcome": "👋 ברוכים הבאים ל{title}!\n\n🔎 מערכת אוטומטית בודקת אלפי מוצרים פעמיים ביום ומשווה כל מחיר להיסטוריה שלו. מתפרסם רק דיל עם הנחה אמיתית של 30% ומעלה, ולכן יש ימים בלי פוסטים, וזה בכוונה.\n\n🔔 רוצים התראה על מוצר מסוים? שלחו ל-@{bot} את הפקודה: /alert והמילה\n\nחלק מהקישורים הם קישורי שותפים, בלי עלות נוספת עבורכם.",
        "weekly": "🏆 חמשת הדילים הכי חמים השבוע",
    },
    "es": {
        "start": "¡Hola! Soy el bot de {title}.\n\nPara recibir un aviso cuando haya una oferta de algo concreto, envía:\n/alert auriculares\n(máx. 5). /alerts muestra tus avisos, /stop los borra todos.\n\nCanal: {channel}",
        "added": "✅ Aviso añadido: {kw}",
        "limit": "Máximo 5 avisos. Envía /stop para empezar de nuevo.",
        "list": "Tus avisos: {kws}",
        "none": "No tienes avisos. Ejemplo: /alert café",
        "stopped": "Avisos borrados.",
        "hit": "🔔 Oferta para tu aviso \"{kw}\":",
        "welcome": "👋 ¡Bienvenido a {title}!\n\n🔎 Un sistema automático revisa miles de productos dos veces al día y compara cada precio con su historial. Solo se publican rebajas reales del 30% o más, así que hay días sin publicaciones, a propósito.\n\n🔔 ¿Quieres un aviso de un producto concreto? Envía a @{bot}: /alert y la palabra\n\nAlgunos enlaces son de afiliado, sin coste extra para ti.",
        "weekly": "🏆 Las 5 ofertas más calientes de la semana",
    },
    "en": {
        "start": "Hi! I'm the {title} bot.\n\nTo get a ping when there's a deal on something specific, send:\n/alert earbuds\n(up to 5). /alerts lists yours, /stop clears all.\n\nChannel: {channel}",
        "added": "✅ Alert added: {kw}",
        "limit": "Up to 5 alerts. Send /stop to start over.",
        "list": "Your alerts: {kws}",
        "none": "No active alerts. Example: /alert coffee",
        "stopped": "All alerts removed.",
        "hit": "🔔 Deal matching your alert \"{kw}\":",
        "welcome": "👋 Welcome to {title}!\n\n🔎 An automated system checks thousands of products twice a day against each item's own price history. Only real discounts of 30%+ get posted, so some days are quiet, on purpose.\n\n🔔 Want an alert for a specific product? Send @{bot}: /alert and the word\n\nSome links are affiliate links, at no extra cost to you.",
        "weekly": "🏆 This week's 5 hottest deals",
    },
}


def _token():
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _channel(lang):
    return os.environ.get(LANGS[lang]["channel_env"])


def _setup(hist: History):
    hist.db.executescript("""
        CREATE TABLE IF NOT EXISTS alerts(chat TEXT, lang TEXT, kw TEXT, PRIMARY KEY(chat, kw));
        CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT);
    """)


def _get(hist, k):
    r = hist.db.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone()
    return r[0] if r else None


def _set(hist, k, v):
    hist.db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (k, str(v)))
    hist.db.commit()


def _lang_of(user: dict) -> str:
    code = (user.get("language_code") or "en")[:2]
    return code if code in LANGS else ("he" if code == "iw" else "en")


def _send(chat, text, **extra):
    return _call(_token(), "sendMessage", {"chat_id": chat, "text": text,
                                           "disable_web_page_preview": "true", **extra})


# ---------------------------------------------------------------- alerts ----
def process_commands(hist: History) -> int:
    """Read pending private messages and answer /start /alert /alerts /stop."""
    if not _token():
        return 0
    _setup(hist)
    offset = int(_get(hist, "update_offset") or 0)
    res = _call(_token(), "getUpdates", {"offset": offset, "timeout": 0,
                                        "allowed_updates": json.dumps(["message"])})
    handled = 0
    for upd in res.get("result", []):
        offset = max(offset, upd["update_id"] + 1)
        msg = upd.get("message") or {}
        chat = msg.get("chat", {})
        if chat.get("type") != "private":
            continue
        cid, txt = str(chat["id"]), (msg.get("text") or "").strip()
        lang = _lang_of(msg.get("from", {}))
        t, c = TEXT[lang], LANGS[lang]
        cmd, _, arg = txt.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "/alert" and arg.strip():
            kw = arg.strip().lower()[:40]
            n = hist.db.execute("SELECT COUNT(*) FROM alerts WHERE chat=?", (cid,)).fetchone()[0]
            if n >= MAX_ALERTS_PER_USER:
                _send(cid, t["limit"])
            else:
                hist.db.execute("INSERT OR IGNORE INTO alerts VALUES(?,?,?)", (cid, lang, kw))
                hist.db.commit()
                _send(cid, t["added"].format(kw=kw))
        elif cmd == "/alerts":
            kws = [r[0] for r in hist.db.execute("SELECT kw FROM alerts WHERE chat=?", (cid,))]
            _send(cid, t["list"].format(kws=", ".join(kws)) if kws else t["none"])
        elif cmd == "/stop":
            hist.db.execute("DELETE FROM alerts WHERE chat=?", (cid,))
            hist.db.commit()
            _send(cid, t["stopped"])
        else:
            _send(cid, t["start"].format(title=c["site_title"], channel=c["channel_url"]))
        handled += 1
    _set(hist, "update_offset", offset)
    return handled


def send_alerts(hist: History, lang: str, deals: list, links: dict) -> int:
    """links: pid -> click url. Matches keywords against English and local titles."""
    if not _token() or not deals:
        return 0
    _setup(hist)
    subs = hist.db.execute("SELECT chat, kw FROM alerts WHERE lang=?", (lang,)).fetchall()
    sent, per_chat = 0, {}
    for chat, kw in subs:
        for d in deals:
            hay = f"{d.product.title} {d.product.title_local}".lower()
            if kw in hay and per_chat.get(chat, 0) < MAX_ALERT_MSGS_PER_RUN:
                title = d.product.title_local or d.product.title
                _send(chat, f"{TEXT[lang]['hit'].format(kw=kw)}\n{title}\n{links.get(d.product.pid, '')}")
                per_chat[chat] = per_chat.get(chat, 0) + 1
                sent += 1
    return sent


# ------------------------------------------------------- channel extras ----
def ensure_welcome(hist: History):
    """Post + pin one intro message per channel (once)."""
    if not _token():
        return
    _setup(hist)
    for lang, c in LANGS.items():
        key = f"welcome_{lang}"
        if _get(hist, key) or not _channel(lang):
            continue
        res = _send(_channel(lang), TEXT[lang]["welcome"].format(title=c["site_title"], bot=BOT_USERNAME))
        if res.get("ok"):
            mid = res["result"]["message_id"]
            pin = _call(_token(), "pinChatMessage", {"chat_id": _channel(lang), "message_id": mid,
                                                     "disable_notification": "true"})
            _set(hist, key, mid)
            if not pin.get("ok"):
                notify_owner(f"ℹ️ Welcome message posted in {lang} channel; pin it manually (bot has post-only rights).")


def weekly(hist: History, today: str):
    """Sunday morning: top-5 summary per channel + private owner report."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 6 or now.hour >= 12 or _get(hist, "weekly_done") == today:
        return
    _setup(hist)
    week_ago = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
    report = ["📊 Weekly report"]
    for lang, c in LANGS.items():
        f = DATA / f"deals_{lang}.json"
        archive = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        week = [d for d in archive if d.get("day", "") >= week_ago]
        top = sorted(week, key=lambda d: d["heat"], reverse=True)[:5]
        if top and _token() and _channel(lang):
            base = os.environ.get("SITE_BASE_URL", SETTINGS["site_base_url"]).rstrip("/")
            lines = [f"<b>{TEXT[lang]['weekly']}</b>", ""]
            for i, d in enumerate(top, 1):
                t = html.escape((d.get("title_local") or d["title"])[:70])
                lines.append(f"{i}. <a href=\"{base}/{lang}/deal/{d['slug']}.html\">{t}</a> (-{round(d['discount'] * 100)}%)")
            _call(_token(), "sendMessage", {"chat_id": _channel(lang), "text": "\n".join(lines),
                                            "parse_mode": "HTML", "disable_web_page_preview": "true"})
        members = "?"
        if _token() and _channel(lang):
            members = _call(_token(), "getChatMemberCount", {"chat_id": _channel(lang)}).get("result", "?")
        alerts = hist.db.execute("SELECT COUNT(DISTINCT chat) FROM alerts WHERE lang=?", (lang,)).fetchone()[0]
        report.append(f"{lang}: {members} subscribers · {len(week)} deals this week · {alerts} alert users")
    notify_owner("\n".join(report))
    _set(hist, "weekly_done", today)


def cleanup(hist: History) -> int:
    """One-time: delete the bot's posts that came after each channel's welcome message
    (Telegram allows bots to delete their own channel posts for 48 hours)."""
    import urllib.parse, urllib.request
    if not _token():
        return 0
    _setup(hist)
    deleted = 0
    for lang in LANGS:
        wid, ch = _get(hist, f"welcome_{lang}"), _channel(lang)
        if not wid or not ch:
            continue
        for mid in range(int(wid) + 1, int(wid) + 90):
            data = urllib.parse.urlencode({"chat_id": ch, "message_id": mid}).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        f"https://api.telegram.org/bot{_token()}/deleteMessage", data=data), timeout=15) as r:
                    deleted += bool(json.loads(r.read()).get("ok"))
            except Exception:
                pass
    print(f"[bot] cleanup deleted {deleted} messages", flush=True)
    return deleted


EVENT_TEXT = {"he": "🎯 {t}\n\nהדילים הכי חמים היום, כל אחד נבדק מול היסטוריית המחיר שלו:",
              "es": "🎯 {t}\n\nLas ofertas más calientes de hoy, cada una comparada con su historial de precio:",
              "en": "🎯 {t}\n\nToday's hottest deals, each checked against its own price history:"}
EVENT_ALL = {"he": "כל דילי האירוע באתר", "es": "Todas las ofertas del evento", "en": "All event deals"}


def event_posts(hist: History, today: str):
    """On an event's main day (e.g. 11.11), one summary post per channel linking the event page."""
    if not _token():
        return
    _setup(hist)
    base = os.environ.get("SITE_BASE_URL", SETTINGS["site_base_url"]).rstrip("/")
    for ev in SETTINGS.get("events", []):
        if ev.get("post_on") != today:
            continue
        for lang in LANGS:
            key = f"event_{ev['key']}_{lang}"
            if _get(hist, key) or not _channel(lang):
                continue
            f = DATA / f"deals_{lang}.json"
            live = [d for d in (json.loads(f.read_text(encoding="utf-8")) if f.exists() else []) if not d.get("expired")]
            top = sorted(live, key=lambda d: d["heat"], reverse=True)[:5]
            if not top:
                continue
            lines = [f"<b>{html.escape(EVENT_TEXT[lang].format(t=ev['title'][lang]))}</b>", ""]
            for i, d in enumerate(top, 1):
                t = html.escape((d.get("title_local") or d["title"])[:70])
                lines.append(f"{i}. <a href=\"{base}/{lang}/deal/{d['slug']}.html\">{t}</a> (-{round(d['discount'] * 100)}%)")
            lines += ["", f"👉 <a href=\"{base}/{lang}/event/{ev['key']}.html\">{EVENT_ALL[lang]}</a>"]
            res = _call(_token(), "sendMessage", {"chat_id": _channel(lang), "text": "\n".join(lines),
                                                  "parse_mode": "HTML", "disable_web_page_preview": "true"})
            if res.get("ok"):
                _set(hist, key, res["result"]["message_id"])

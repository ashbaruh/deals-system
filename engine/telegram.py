"""Telegram posting. Without TELEGRAM_BOT_TOKEN it runs in dry-run mode."""
from __future__ import annotations

import html
import json
import os
import time
import urllib.parse
import urllib.request

from .core import LANGS, Deal

API = "https://api.telegram.org/bot{token}/{method}"


def fmt_price(usd: float, lang: str) -> str:
    cfg = LANGS[lang]
    v = usd * cfg["currency_rate_from_usd"]
    return f"{cfg['currency']}{v:,.2f}" if lang != "he" else f"{v:,.2f} {cfg['currency']}"


LABELS = {"he": {"verified": "מאומת מול 30 יום", "store": "מול מחיר החנות"},
          "es": {"verified": "verificado vs 30 días", "store": "vs precio de la tienda"},
          "en": {"verified": "verified vs 30 days", "store": "vs store price"}}


def caption(deal: Deal, site_url: str) -> str:
    s = LANGS[deal.lang]["strings"]
    p = deal.product
    pct = round(deal.discount * 100)
    verified = len([1 for _ in deal.history]) >= 7
    label = LABELS[deal.lang]["verified" if verified else "store"]
    lines = [
        f"🔥 <b>{html.escape((p.title_local or p.title)[:120])}</b>",
    ]
    if p.why:
        lines.append(f"💡 {html.escape(p.why[:90])}")
    lines += [
        "",
        f"{s['now']}: <b>{fmt_price(p.price_usd, deal.lang)}</b>  "
        f"({s['was']}: <s>{fmt_price(deal.median_30d, deal.lang)}</s>)",
        f"📉 {pct}% {s['off']} ({label})",
    ]
    if p.rating:
        extra = f"⭐ {p.rating:.1f}"
        if p.orders:
            extra += f"  ·  {p.orders:,} {s['orders']}"
        lines.append(extra)
    lines += ["", f"<i>{html.escape(s['price_note'])}</i>"]
    return "\n".join(lines)


def _call(token: str, method: str, payload: dict) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(API.format(token=token, method=method), data=data)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read() or b"{}")
            retry = body.get("parameters", {}).get("retry_after")
            if e.code == 429 and retry:
                time.sleep(int(retry) + 1)
                continue
            if attempt == 2:
                raise
            time.sleep(3)
    return {}


def post_deal(deal: Deal, click_url: str, site_url: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get(LANGS[deal.lang]["channel_env"])
    s = LANGS[deal.lang]["strings"]
    markup = json.dumps({"inline_keyboard": [[{"text": f"🛒 {s['go']}", "url": click_url}]]})
    text = caption(deal, site_url)
    if not token or not chat:
        print(f"[dry-run:{deal.lang}] {deal.product.title[:60]} -> {click_url}")
        return True
    payload = {"chat_id": chat, "caption": text, "parse_mode": "HTML",
               "reply_markup": markup}
    if deal.product.image:
        payload["photo"] = deal.product.image
        res = _call(token, "sendPhoto", payload)
    else:
        payload.pop("caption")
        payload["text"] = text
        res = _call(token, "sendMessage", payload)
    return bool(res.get("ok"))


def notify_owner(text: str):
    """Private message to the owner (alerts + weekly report)."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not token or not chat:
        print("[owner-alert]", text)
        return
    _call(token, "sendMessage", {"chat_id": chat, "text": text})

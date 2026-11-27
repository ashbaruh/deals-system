"""'We're live' notice for the Telegram channels and Bluesky, sent ~40 s after the stream starts.
Usage: python -m video.announce youtube|twitch"""
import os
import sys

from engine.telegram import _call

YT = "https://www.youtube.com/channel/UCr7x4aSFKZV4tDVCCZ-M1BA/live"
TEXT = {
    "youtube": {
        "he": "🔴 עכשיו בשידור חי ביוטיוב: 30 ירידות מחיר אמיתיות מאליאקספרס (באנגלית)\n▶️ {yt}\n🛒 כל הדילים מהשידור ברשימה אחת: https://dealim.net/l/",
        "es": "🔴 EN DIRECTO en YouTube: 30 bajadas de precio reales de AliExpress (en inglés)\n▶️ {yt}\n🛒 Todas las ofertas del directo: https://dealim.net/l/",
        "en": "🔴 LIVE NOW on YouTube: 30 real AliExpress price drops\n▶️ {yt}\n🛒 Every deal from the stream in one list: https://dealim.net/l/",
    },
    "twitch": {
        "he": "🎮 עכשיו בשידור חי: דילים על ציוד גיימינג (מקלדות, עכברים, אוזניות)\n▶️ https://www.twitch.tv/dealim1\n▶️ https://kick.com/dealim1\n🛒 כל הדילים: https://dealim.net/g/",
        "es": "🎮 EN DIRECTO: ofertas de gaming (teclados, ratones, auriculares)\n▶️ https://www.twitch.tv/dealim1\n▶️ https://kick.com/dealim1\n🛒 Todas las ofertas: https://dealim.net/g/",
        "en": "🎮 LIVE NOW: gaming gear deals (keyboards, mice, headsets)\n▶️ https://www.twitch.tv/dealim1\n▶️ https://kick.com/dealim1\n🛒 Every deal from the stream: https://dealim.net/g/",
    },
}


def is_live(target: str) -> bool:
    """Poll the public page until the stream is really on air (max ~2.5 min). No announce otherwise."""
    import time, urllib.request
    url = YT if target == "youtube" else "https://decapi.me/twitch/uptime/dealim1"
    for _ in range(10):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            ok = '"isLiveNow":true' in body if target == "youtube" else ("offline" not in body.lower() and "error" not in body.lower())
            print("live check", target, ok)
            if ok:
                return True
        except Exception as e:
            print("live check error", e)
        time.sleep(15)
    return False


def main(target: str) -> None:
    if not is_live(target):
        print("NOT LIVE - announcement skipped")
        return
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    for lang, chat in (("he", "@mivtzaim_kuponim"), ("es", "@ofertas_descuentos_es"), ("en", "@discount_deals_promo")):
        if tok:
            try:
                _call(tok, "sendMessage", {"chat_id": chat, "text": TEXT[target][lang].format(yt=YT)})
                print("telegram", lang, "ok")
            except Exception as e:
                print("telegram", lang, e)
    try:
        from engine import bluesky
        link = YT if target == "youtube" else "https://www.twitch.tv/dealim1"
        t = TEXT[target]["en"].format(yt=YT).split("\n")[0] + " #AliExpress #deals" + (" #gaming" if target == "twitch" else "")
        print("bluesky", bluesky.post(t, link, "LIVE: real AliExpress price drops", "Every deal from the stream: dealim.net", None))
    except Exception as e:
        print("bluesky", e)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "youtube")

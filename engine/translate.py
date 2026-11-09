"""Short, natural product titles per language via the free Gemini API.

No GEMINI_API_KEY -> titles stay as in the feed. Results are cached in SQLite,
so each product is translated once per language.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .core import History

LANG_NAMES = {"he": "Hebrew", "es": "Spanish (Spain)", "en": "English"}
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"


def _cache(hist: History):
    hist.db.execute("CREATE TABLE IF NOT EXISTS titles(pid TEXT, lang TEXT, title TEXT, PRIMARY KEY(pid, lang))")
    return hist.db


def localize(deals, lang: str, hist: History) -> None:
    db = _cache(hist)
    todo = []
    for d in deals:
        row = db.execute("SELECT title FROM titles WHERE pid=? AND lang=?", (d.product.pid, lang)).fetchone()
        if row:
            d.product.title_local = row[0]
        else:
            todo.append(d)
    key = os.environ.get("GEMINI_API_KEY")
    if not todo or not key:
        return
    items = {str(i): d.product.title for i, d in enumerate(todo)}
    prompt = (
        f"Rewrite each product title as a short, natural {LANG_NAMES[lang]} shopping title "
        "(max 60 characters). Keep brand names, model numbers and key specs; drop SEO keyword "
        "stuffing; no emojis; do not invent features. Return only a JSON object mapping the same "
        f"keys to the new titles.\n{json.dumps(items, ensure_ascii=False)}"
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}).encode()
    try:
        req = urllib.request.Request(URL.format(m=MODEL, k=key), data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read())
        text = out["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except Exception as e:  # quota/network: keep feed titles, try again next run
        print(f"[translate:{lang}] skipped: {e.__class__.__name__}")
        return
    for i, d in enumerate(todo):
        t = str(result.get(str(i), "")).strip()
        if 3 <= len(t) <= 90:
            d.product.title_local = t
            db.execute("INSERT OR REPLACE INTO titles VALUES(?,?,?)", (d.product.pid, lang, t))
    db.commit()

"""Short, natural product titles per language via the free Gemini API.

No GEMINI_API_KEY -> titles stay as in the feed. Results are cached in SQLite,
so each product is translated once per language.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .core import History

LANG_NAMES = {"he": "Hebrew", "es": "Spanish (Spain)", "en": "English"}
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"


def _cache(hist: History):
    hist.db.execute("CREATE TABLE IF NOT EXISTS titles(pid TEXT, lang TEXT, title TEXT, PRIMARY KEY(pid, lang))")
    hist.db.execute("CREATE TABLE IF NOT EXISTS whys(pid TEXT, lang TEXT, why TEXT, PRIMARY KEY(pid, lang))")
    return hist.db


import re as _re
_FOREIGN = _re.compile(r"[\u0400-\u04FF\u0600-\u06FF\u4e00-\u9fff]")  # stray Cyrillic/Arabic/CJK = bad output


def localize(deals, lang: str, hist: History) -> None:
    db = _cache(hist)
    todo = []
    for d in deals:
        row = db.execute("SELECT title FROM titles WHERE pid=? AND lang=?", (d.product.pid, lang)).fetchone()
        w = db.execute("SELECT why FROM whys WHERE pid=? AND lang=?", (d.product.pid, lang)).fetchone()
        if row and (w or not hasattr(d.product, "why")):
            d.product.title_local = row[0] if not _FOREIGN.search(row[0] or "") else ""
            if w:
                d.product.why = w[0]
        else:
            todo.append(d)
    key = os.environ.get("GEMINI_API_KEY")
    if not todo or not key:
        return
    for i in range(0, len(todo), 25):
        _batch(todo[i:i + 25], lang, key, db)
    db.commit()


def _batch(todo, lang, key, db):
    items = {str(i): d.product.title for i, d in enumerate(todo)}
    prompt = (
        f"For each product title, write in {LANG_NAMES[lang]}: (t) a short, natural shopping title "
        "(max 60 characters; keep brand, model numbers and key specs; drop SEO keyword stuffing) and "
        "(w) one short line on why a buyer would want it (max 70 characters, a concrete benefit taken "
        "from the title only). No emojis, do not invent features or specs. Return only a JSON object "
        f"mapping the same keys to {{\"t\": ..., \"w\": ...}}.\n{json.dumps(items, ensure_ascii=False)}"
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}).encode()
    result = None
    for model in (MODEL, "gemini-3.5-flash-lite", "gemini-flash-latest"):
        try:
            req = urllib.request.Request(URL.format(m=model, k=key), data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                out = json.loads(r.read())
            result = json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
            break
        except urllib.error.HTTPError as e:   # log the reason (key, quota, model) without the key
            detail = e.read()[:300].decode("utf-8", "replace").replace(key, "***")
            print(f"[translate:{lang}] {model} HTTP {e.code}: {detail}", flush=True)
        except Exception as e:
            print(f"[translate:{lang}] {model} failed: {e.__class__.__name__}", flush=True)
    if not result:
        return
    for i, d in enumerate(todo):
        v = result.get(str(i), "")
        t, w = (v.get("t", ""), v.get("w", "")) if isinstance(v, dict) else (v, "")
        t, w = str(t).strip(), str(w).strip()
        if 3 <= len(t) <= 90:
            d.product.title_local = t if not _FOREIGN.search(t or "") else ""
            db.execute("INSERT OR REPLACE INTO titles VALUES(?,?,?)", (d.product.pid, lang, t))
        if 3 <= len(w) <= 100 and hasattr(d.product, "why"):
            d.product.why = w
            db.execute("INSERT OR REPLACE INTO whys VALUES(?,?,?)", (d.product.pid, lang, w))

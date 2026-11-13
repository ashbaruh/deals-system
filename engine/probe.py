"""Inspect an Admitad feed (columns, samples, currency, category counts) without saving it.

    python -m engine.probe <feed_id> [max_rows]
"""
from __future__ import annotations

import collections
import csv
import itertools
import re
import sys

from .core import _lines
from .run import feed_sources


def main() -> int:
    feed_id, limit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 300000
    src = [u for s, u in feed_sources("en") if u.startswith("http")][0]
    url = re.sub(r"feed_id=\d+", f"feed_id={feed_id}", src)
    if len(sys.argv) > 3:
        url = re.sub(r"format=\w+", f"format={sys.argv[3]}", url)
        if sys.argv[3] == "xml":
            import urllib.request
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "deals-bot/1.0"}), timeout=120)
            buf, total = "", 0
            while total < 60_000_000:
                chunk = r.read(1_000_000)
                if not chunk:
                    break
                total += len(chunk)
                buf += chunk.decode("utf-8", "replace")
                i = buf.find("<offer ")
                if i >= 0 and buf.count("</offer>") >= 6:
                    print("CATEGORIES_BYTES_BEFORE_OFFERS:", total)
                    print("OFFERS:", buf[i:i+7000])
                    break
                if i < 0:
                    buf = buf[-2000:]
            print("read", total, "bytes; oldprice tags:", buf.count("<oldprice>"))
            return 0
    import hashlib, urllib.parse
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    h = lambda v: hashlib.sha256(v.encode()).hexdigest()[:8]
    print("HOST", urllib.parse.urlparse(url).netloc, "PATH", urllib.parse.urlparse(url).path,
          "code#", h(q.get("code", [""])[0]), "user#", h(q.get("user", [""])[0]), "keys", list(q))
    it = _lines(url, deadline_s=1500)
    first = next(it, "")
    raw = [first] + [next(it, "") for _ in range(4)]
    for i, l in enumerate(raw):
        print(f"RAW{i}:", repr(l[:600]))
    it = itertools.chain(raw[1:], it)
    delim = ";" if first.count(";") > first.count(",") else ","
    rd = csv.DictReader(itertools.chain([first], it), delimiter=delim)
    print("COLUMNS:", rd.fieldnames)
    cats, cur, n, disc = collections.Counter(), collections.Counter(), 0, 0
    for row in rd:
        n += 1
        if n <= 3:
            print("SAMPLE:", {k: (v or "")[:120] for k, v in row.items()})
        cats[row.get("categoryId") or row.get("category") or ""] += 1
        cur[row.get("currencyId", "")] += 1
        try:
            if float(row.get("oldprice") or 0) > float(row.get("price") or 0) * 1.5:
                disc += 1
        except ValueError:
            pass
        if n >= limit:
            break
    print(f"ROWS {n}  currency {dict(cur)}  with>=33%off {disc}")
    for c, k in cats.most_common(150):
        print(f"CAT {k:7d}  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

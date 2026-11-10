"""Download ONE AliExpress price-bucket feed and save the niche-matching products.

The single "hot products" feed is cut off by the server after ~25 min (we only ever got
~45% of it, whole categories missing). Admitad also offers the same catalogue split into
price buckets (<$10, $10-25, ...); each bucket is small enough to finish. The workflow runs
one job per bucket in parallel, then the main run loads all saved files (FEED_CACHE_DIR).

    python -m engine.fetch <feed_id>     -> cache/products_<feed_id>.json.gz
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from .core import stream_products
from .run import _keep, feed_sources

OUT = Path(__file__).resolve().parent.parent / "cache"


def main() -> int:
    feed_id = sys.argv[1]
    srcs = [u for s, u in feed_sources("en") if s == "aliexpress" and u.startswith("http")]
    if not srcs:
        print("no aliexpress feed configured"); return 1
    url, n = re.subn(r"feed_id=\d+", f"feed_id={feed_id}", srcs[0])
    if not n:
        print("feed URL has no feed_id parameter; cannot select a bucket"); return 1
    OUT.mkdir(exist_ok=True)
    items = []
    for attempt in range(2):
        try:
            items = stream_products(url, "aliexpress", _keep, None)
            break
        except Exception as e:
            print(f"[fetch {feed_id}] attempt {attempt + 1} failed: {e}", flush=True)
    if not items:
        return 1
    with gzip.open(OUT / f"products_{feed_id}.json.gz", "wt", encoding="utf-8") as f:
        json.dump([asdict(p) for p in items], f, ensure_ascii=False)
    print(f"[fetch {feed_id}] saved {len(items)} products", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

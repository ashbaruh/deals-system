"""Post deals to Bluesky (free AT Protocol API). Needs BLUESKY_HANDLE + BLUESKY_APP_PASSWORD;
does nothing without them. Each post: short text + link card (image, title) to the deal page on dealim.net."""
import json
import os
import urllib.request

API = "https://bsky.social/xrpc"


def _call(method, body, token=None, ctype="application/json"):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"Content-Type": ctype}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}/{method}", data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")
_session = None


def _login():
    global _session
    if _session is None:
        h, p = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
        if not (h and p):
            _session = False
        else:
            _session = _call("com.atproto.server.createSession", {"identifier": h, "password": p})
    return _session


def _thumb(s, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=20).read()
        if len(data) > 950_000:
            return None
        return _call("com.atproto.repo.uploadBlob", data, s["accessJwt"], "image/jpeg")["blob"]
    except Exception:
        return None


def post(text: str, link: str, title: str, desc: str, image: str | None) -> bool:
    s = _login()
    if not s:
        return False
    from datetime import datetime, timezone
    ext = {"uri": link, "title": title[:300], "description": desc[:300]}
    blob = _thumb(s, image) if image else None
    if blob:
        ext["thumb"] = blob
    tags = [w for w in text.split() if w.startswith("#")]
    rec = {"$type": "app.bsky.feed.post", "text": text[:300], "createdAt": datetime.now(timezone.utc).isoformat(),
           "langs": ["en"], "embed": {"$type": "app.bsky.embed.external", "external": ext}}
    # hashtags become clickable only with facets (byte offsets)
    b, facets = text[:300].encode(), []
    for t in tags:
        i = b.find(t.encode())
        if i >= 0:
            facets.append({"index": {"byteStart": i, "byteEnd": i + len(t.encode())},
                           "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": t[1:]}]})
    if facets:
        rec["facets"] = facets
    _call("com.atproto.repo.createRecord", {"repo": s["did"], "collection": "app.bsky.feed.post", "record": rec}, s["accessJwt"])
    return True

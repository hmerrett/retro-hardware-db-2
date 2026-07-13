"""Fetch a photo for an item from its reference URL.

Wikipedia URLs use the free summary API to get the page's lead image. Any other
site is a best effort grab of its Open Graph image (`og:image`). The bytes are
downscaled and re-saved as JPEG; known placeholder images are skipped. No bot
protection is bypassed, so a Cloudflare-gated site may simply return nothing.
"""
from __future__ import annotations

import hashlib
import io
import re
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from PIL import Image

USER_AGENT = "RetroHardwareDB/1.0 (+https://db.2600.me)"
MAX_PX = 1000

# SHA1s of "please send a picture" placeholder images to ignore.
SKIP_SHA1 = {
    "0e07517a48ddafd09fe2834ef5e50d52dbbaeec0",
    "b1b631422579c64ffd1f7eaf392d9c6c36ca8a16",
}


def _client():
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0,
                        follow_redirects=True)


def _wikipedia_image(client, url):
    m = re.search(r"/wiki/([^?#]+)", url)
    if not m:
        return None
    title = unquote(m.group(1))
    host = urlparse(url).hostname or "en.wikipedia.org"
    lang = host.split(".")[0] if host.endswith("wikipedia.org") else "en"
    api = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    resp = client.get(api)
    if resp.status_code >= 400:
        return None
    data = resp.json()
    return (data.get("originalimage") or data.get("thumbnail") or {}).get("source")


def _og_image(client, url):
    resp = client.get(url)
    if resp.status_code >= 400:
        return None
    html = resp.text
    for prop in ("og:image", "twitter:image"):
        m = (re.search(r'<meta[^>]+(?:property|name)=["\']' + prop
                       + r'["\'][^>]+content=["\']([^"\']+)', html, re.I)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']'
                          + prop, html, re.I))
        if m:
            return urljoin(url, m.group(1))
    return None


def fetch_jpeg(url):
    """Return downscaled JPEG bytes for the item's reference URL, or None if
    nothing usable was found."""
    url = (url or "").strip()
    if not url:
        return None
    try:
        with _client() as client:
            img_url = None
            if "wikipedia.org" in url.lower():
                img_url = _wikipedia_image(client, url)
            if not img_url:
                img_url = _og_image(client, url)
            if not img_url:
                return None
            resp = client.get(img_url)
            if resp.status_code >= 400 or not resp.content:
                return None
            raw = resp.content
    except Exception:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    img.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    data = buf.getvalue()
    if hashlib.sha1(data).hexdigest() in SKIP_SHA1:
        return None
    return data

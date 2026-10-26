"""Best-effort per-IP rate limiting for the plain-stdlib Vercel Python
functions in api/.

This is in-memory and scoped to one warm container — on Vercel that means
it resets on cold starts and isn't shared across concurrent instances. For
a free-tier portfolio demo that's a reasonable trade-off: the goal is
cutting down casual/bot traffic against the free upstream APIs
(Nominatim/Overpass/Open-Topo-Data) the live-compute path depends on, not
bulletproof abuse prevention. For real production traffic, swap this for a
shared store (Vercel KV / Upstash Redis).
"""

import time

_hits: dict[str, list[float]] = {}


def client_ip(handler) -> str:
    # Vercel's edge network sets x-forwarded-for on every request.
    fwd = handler.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip()
    return ip or handler.client_address[0]


def allow(handler, limit: int, window_s: float = 60.0) -> bool:
    """Return True if this client is under `limit` requests per window_s."""
    ip = client_ip(handler)
    now = time.time()
    hits = _hits.setdefault(ip, [])
    hits[:] = [t for t in hits if now - t < window_s]
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


def same_origin(handler) -> bool:
    """
    Best-effort check that the request came from our own frontend rather
    than a script on another site scraping the API directly.

    Fails open (True) when neither Origin nor Referer is present — some
    legitimate clients omit both, and spoofing either header is trivial for
    a determined scraper. This is a deterrent against casual/naive bots,
    not an auth boundary.
    """
    origin = handler.headers.get("origin") or handler.headers.get("referer")
    if not origin:
        return True
    host = handler.headers.get("host", "")
    return bool(host) and host in origin

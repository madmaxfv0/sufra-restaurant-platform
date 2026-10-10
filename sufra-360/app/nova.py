"""The bridge to SUFRA OS — the restaurant's operational source of truth.

SUFRA 360 does not own any restaurant state. It owns the room: geometry,
lighting, cameras, the 3D scene. Everything that is *the restaurant* —
tables, capacities, reservations, holds, the waitlist, the menu, opening
hours, the clock — lives in SUFRA OS and is read and written through here.

There is deliberately no second database. This module is the only place in
SUFRA 360 that knows the OS's address, and every endpoint in main.py that
touches restaurant state goes through it.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("SUFRA_OS_BASE", "http://127.0.0.1:8123").rstrip("/")
TIMEOUT = float(os.environ.get("SUFRA_OS_TIMEOUT", "12"))


class NovaUnavailable(Exception):
    """SUFRA OS could not be reached. Never faked over with local data."""


class NovaRefused(Exception):
    """SUFRA OS answered, and the answer was no. Carries its own reason."""

    def __init__(self, status, payload):
        super().__init__((payload or {}).get("message") or "refused")
        self.status = status
        self.payload = payload or {}


def _request(method, path, body=None, session_id=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if session_id:
        # One guest, one session, across both applications: this is what makes
        # "the table you are holding" mean the same thing on both sides.
        req.add_header("Cookie", "sufra_sid=" + session_id)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"message": raw[:300].decode("utf-8", "replace")}
        raise NovaRefused(exc.code, payload)
    except Exception as exc:
        raise NovaUnavailable(str(exc))


def get(path, session_id=None):
    return _request("GET", path, None, session_id)


def post(path, body=None, session_id=None):
    return _request("POST", path, body or {}, session_id)


def delete(path, session_id=None):
    return _request("DELETE", path, None, session_id)


def raw(path):
    """Fetch a non-JSON body (the calendar file) straight through."""
    with urllib.request.urlopen(BASE + path, timeout=TIMEOUT) as resp:
        return resp.read(), resp.headers.get("Content-Type", "text/plain")


# ------------------------------------------------------------ small cache
# Venue identity and the table registry change when a manager edits them,
# not between two frames of a 3D scene. A few seconds of cache keeps the
# scene's boot fast without ever serving stale operational state: live
# tables, availability, reservations and the menu are never cached here.

_lock = threading.Lock()
_cache = {}
CACHE_SECONDS = 8.0


def cached(path, seconds=CACHE_SECONDS):
    now = time.time()
    with _lock:
        hit = _cache.get(path)
        if hit and now - hit[0] < seconds:
            return hit[1]
    value = get(path)
    with _lock:
        _cache[path] = (now, value)
    return value


def invalidate():
    with _lock:
        _cache.clear()


# ------------------------------------------------------- restaurant reads

def venue():
    return cached("/api/public/venue", 20)


def tables():
    return cached("/api/public/tables", 8)["tables"]


def table_map():
    return {t["id"]: t for t in tables()}


def live(session_id=None):
    return get("/api/public/live", session_id)


def availability(date, time_hhmm, party_size, duration=None, session_id=None):
    q = {"date": date, "time": time_hhmm, "party_size": party_size}
    if duration:
        q["duration"] = duration
    return get("/api/public/availability?" + urllib.parse.urlencode(q), session_id)


def menu():
    return get("/api/public/menu")


def health():
    try:
        v = venue()
        return {"reachable": True, "restaurant": v["restaurant"]["name"],
                "timezone": v["timezone"], "base": BASE}
    except NovaUnavailable as exc:
        return {"reachable": False, "base": BASE, "detail": str(exc)}

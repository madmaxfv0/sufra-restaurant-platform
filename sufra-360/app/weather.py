"""Weather service: one cached fetch per venue every 10 minutes.

Open-Meteo is free, keyless and CORS-friendly. This service exists so the
3D scene never talks to the internet itself and so a failure returns the
last good reading instead of an error. Location comes from the venue
record, so a different restaurant gets its own weather.
"""
import json
import threading
import time
import urllib.request

TTL = 600            # seconds between fetches
TIMEOUT = 6
_lock = threading.Lock()
_cache = {"key": None, "at": 0.0, "data": None, "error": None}

CODES = {
    0: "clear", 1: "mostly_clear", 2: "partly_cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "drizzle", 53: "drizzle", 55: "drizzle",
    56: "drizzle", 57: "drizzle", 61: "rain", 63: "rain", 65: "heavy_rain",
    66: "rain", 67: "heavy_rain", 71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "heavy_rain", 85: "snow", 86: "snow",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def _ssl_context():
    """python.org macOS builds ship without root certificates until
    'Install Certificates.command' is run; certifi, if present, fixes that."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


def _fetch(lat, lng, tz):
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,precipitation,cloud_cover,wind_speed_10m,"
           "wind_direction_10m,is_day,weather_code,relative_humidity_2m"
           "&timezone=%s" % (lat, lng, urllib.request.quote(tz)))
    ctx = _ssl_context()
    with urllib.request.urlopen(url, timeout=TIMEOUT, context=ctx) as r:
        j = json.loads(r.read().decode("utf-8"))
    c = j.get("current") or {}
    code = int(c.get("weather_code", 3))
    return {
        "condition": CODES.get(code, "overcast"),
        "code": code,
        "temp_c": c.get("temperature_2m"),
        "precip_mm": c.get("precipitation", 0.0),
        "cloud": (c.get("cloud_cover") or 0) / 100.0,
        "wind_kmh": c.get("wind_speed_10m", 0.0),
        "wind_deg": c.get("wind_direction_10m", 0.0),
        "humidity": c.get("relative_humidity_2m"),
        "is_day": int(c.get("is_day", 0)),
        "observed_at": c.get("time"),
        "utc_offset_seconds": j.get("utc_offset_seconds", 0),
        "timezone": j.get("timezone", tz),
    }


def current(lat, lng, tz="UTC", city=""):
    key = (round(float(lat), 3), round(float(lng), 3), tz)
    now = time.time()
    with _lock:
        fresh = _cache["key"] == key and now - _cache["at"] < TTL and _cache["data"]
        if fresh:
            return dict(_cache["data"], cached=True, age_s=int(now - _cache["at"]),
                        city=city, source="open-meteo")
    try:
        data = _fetch(lat, lng, tz)
        with _lock:
            _cache.update(key=key, at=now, data=data, error=None)
        return dict(data, cached=False, age_s=0, city=city, source="open-meteo")
    except Exception as e:  # network down, slow, or rate limited
        with _lock:
            stale = _cache["data"] if _cache["key"] == key else None
            _cache["error"] = str(e)
        if stale:
            return dict(stale, cached=True, stale=True, age_s=int(now - _cache["at"]),
                        city=city, source="open-meteo", error=str(e))
        # neutral fallback: calm, overcast evening, never an exception
        return {"condition": "partly_cloudy", "code": 2, "temp_c": 18.0, "precip_mm": 0.0,
                "cloud": 0.4, "wind_kmh": 12.0, "wind_deg": 350.0, "humidity": 55,
                "is_day": 0, "observed_at": None, "utc_offset_seconds": 0,
                "timezone": tz, "cached": False, "fallback": True, "city": city,
                "source": "fallback", "error": str(e)}

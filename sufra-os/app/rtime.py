"""The restaurant clock.

One authoritative time source for the whole system: the operating system's
clock, read through the venue's IANA timezone (Asia/Baku by default). No
fake clock, no hard-coded "+04:00", no browser-side time. The OS keeps the
machine clock correct through NTP; this module only decides which wall
clock the restaurant is reading it in.

The database stores naive datetimes, so everything here returns naive
values that are already in restaurant-local wall-clock terms. That keeps a
single comparison rule everywhere: naive == restaurant local.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

TZ_NAME = os.getenv("SUFRA_TZ", "Asia/Baku")
TZ = ZoneInfo(TZ_NAME)


def now() -> datetime:
    """Restaurant-local wall clock, naive, microseconds kept."""
    return datetime.now(TZ).replace(tzinfo=None)


def today() -> date:
    return now().date()


def aware(dt: datetime) -> datetime:
    """Attach the restaurant timezone to a naive local datetime."""
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def to_utc(dt: datetime) -> datetime:
    from datetime import timezone as _tz
    return aware(dt).astimezone(_tz.utc)


def parse_local(value: str) -> datetime:
    """ISO in, naive restaurant-local out. Accepts a trailing Z or offset."""
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone(TZ).replace(tzinfo=None)
    return dt


def combine(day: date, hhmm: str) -> datetime:
    h, m = (hhmm or "00:00").split(":")[:2]
    return datetime.combine(day, dtime(int(h), int(m)))


def minutes_of(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def hhmm(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def clock() -> str:
    return now().strftime("%H:%M")


__all__ = ["TZ", "TZ_NAME", "now", "today", "aware", "to_utc", "parse_local",
           "combine", "minutes_of", "hhmm", "clock", "timedelta"]

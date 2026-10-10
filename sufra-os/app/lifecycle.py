"""Reservation automation: marking a booking late, and the grace-period no-show.

This runs on the server, on a timer, whether or not anybody has a screen
open. It is deliberately the ONLY scheduler in the system: SUFRA 360 does
not run one, so a reservation can never be processed twice by two apps.
No email or SMS is sent to guests anywhere in SUFRA — these are purely
internal state transitions so the floor and the book reflect reality.

Each action claims its work with a conditional UPDATE inside the database
writer lock, so even two copies of this server cannot double-process the
same reservation.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlmodel import Session, select

from . import canon, dblock, events, rtime
from .database import engine
from .models import DiningTable, Reservation, TableStatus
from .availability import sweep_holds

TICK_SECONDS = 30


def _claim(sql: str, params: tuple) -> bool:
    """Atomic claim across processes. True only for the winner."""
    with dblock.immediate() as con:
        if con is None:
            return True
        cur = con.execute(sql, params)
        return cur.rowcount > 0


def run_once() -> dict:
    """One pass. Returns what actually changed, for logging and for tests."""
    now = rtime.now()
    done = {"late": 0, "no_show": 0, "holds": 0}
    with Session(engine, expire_on_commit=False) as s:
        cfg = canon.service_config(s)
        grace = timedelta(minutes=cfg["grace_minutes"])
        done["holds"] = sweep_holds(s)
        s.commit()

        window_lo = now - timedelta(hours=6)
        window_hi = now + timedelta(hours=3)
        rows = s.exec(select(Reservation).where(
            Reservation.starts_at >= window_lo,
            Reservation.starts_at <= window_hi)).all()

        for r in rows:
            status = (r.status or "").lower()
            if status in ("cancelled", "no_show", "completed", "left"):
                continue
            table = s.get(DiningTable, r.table_id) if r.table_id else None

            # 1. Booking time has passed and nobody has been seated: LATE.
            #    No message goes out — SUFRA sends nothing to guests — this
            #    is purely the internal state transition so the floor and
            #    the book reflect reality.
            if status == "confirmed" and now >= r.starts_at + timedelta(minutes=1):
                if _claim("UPDATE reservation SET status='late', updated_at=? "
                          "WHERE id=? AND status='confirmed'", (dblock.ts(now), r.id)):
                    s.expire(r)
                    events.record(s, "guest_late", "Guest marked late",
                                  detail="%s · booked %s" % (r.code, r.starts_at.strftime("%H:%M")),
                                  table_id=table.id if table else None,
                                  table_number=table.number if table else None,
                                  reservation_id=r.id, actor="SUFRA", source="automation",
                                  severity="warning")
                    s.commit()
                    done["late"] += 1
                    status = "late"

            # 2. Grace expired with nobody seated: NO_SHOW, and the table is
            #    released — the row stays in the book as history.
            if status in ("confirmed", "late") and now >= r.starts_at + grace:
                if _claim("UPDATE reservation SET status='no_show', no_show_at=?, "
                          "updated_at=? WHERE id=? AND status IN ('confirmed','late')",
                          (dblock.ts(now), dblock.ts(now), r.id)):
                    s.expire(r)
                    if table is not None and table.status == TableStatus.RESERVED:
                        table.status = TableStatus.AVAILABLE
                        table.party_size = 0
                        table.guest_id = None
                        table.last_touched_at = now
                        s.add(table)
                    events.record(s, "guest_no_show", "Guest marked no-show",
                                  detail="%s · %d minutes after %s" % (
                                      r.code, cfg["grace_minutes"],
                                      r.starts_at.strftime("%H:%M")),
                                  table_id=table.id if table else None,
                                  table_number=table.number if table else None,
                                  reservation_id=r.id, actor="SUFRA", source="automation",
                                  severity="warning")
                    s.commit()
                    done["no_show"] += 1
    return done


async def loop(interval: float = TICK_SECONDS) -> None:
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception as exc:                       # never kill the loop
            print("[lifecycle] tick failed:", exc)
        await asyncio.sleep(interval)

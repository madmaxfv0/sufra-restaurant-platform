"""
The live layer: a WebSocket hub, and a simulation that runs the restaurant.

Why simulate? A restaurant OS that only changes when you click it is a slide
deck. The loop below moves parties through the whole service — seated,
ordering, cooking, food ready, dining, bill, cleaning — so every screen has
something real to react to, and so the prediction models have moving data.

In production you delete simulation_loop() and keep everything else. The
WebSocket contract stays identical.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta

from fastapi import WebSocket
from sqlmodel import Session, select

from . import rtime
from .database import engine
from .models import (
    DiningTable, Guest, ItemState, MenuItem, Order, OrderItem, Reservation,
    Role, Staff, TableStatus, Task, TaskKind,
)

rng = random.Random()


class Hub:
    """Every open browser tab, in one list. Broadcast, don't poll."""

    def __init__(self) -> None:
        self.clients: list[WebSocket] = []

    async def join(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.append(ws)

    def leave(self, ws: WebSocket) -> None:
        if ws in self.clients:
            self.clients.remove(ws)

    async def send(self, event: str, payload: dict | None = None) -> None:
        dead = []
        message = json.dumps({"event": event, "payload": payload or {},
                              "at": rtime.now().isoformat()})
        for ws in self.clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.leave(ws)


hub = Hub()


# ------------------------------------------------------------------ helpers

def touch(t: DiningTable) -> None:
    t.last_touched_at = rtime.now()


def open_task(s: Session, table: DiningTable, kind: TaskKind,
              message: str, priority: int = 2) -> None:
    existing = s.exec(select(Task).where(
        Task.table_id == table.id, Task.kind == kind, Task.done == False)).first()  # noqa: E712
    if existing:
        return
    s.add(Task(table_id=table.id, kind=kind, message=message, priority=priority))


def close_tasks(s: Session, table_id: int, kind: TaskKind | None = None) -> None:
    q = select(Task).where(Task.table_id == table_id, Task.done == False)  # noqa: E712
    if kind:
        q = q.where(Task.kind == kind)
    for task in s.exec(q).all():
        task.done = True
        s.add(task)


def seat_party(s: Session, table: DiningTable, size: int | None = None) -> None:
    guests = s.exec(select(Guest)).all()
    table.status = TableStatus.SEATED
    table.party_size = size or min(table.seats, rng.choice([2, 2, 2, 3, 4, table.seats]))
    table.seated_at = rtime.now()
    table.guest_id = rng.choice(guests).id if guests and rng.random() < 0.6 else None
    touch(table)
    s.add(table)


def fire_order(s: Session, table: DiningTable) -> None:
    """Create an order for a seated table, with a believable dish mix."""
    from .intelligence import predict_prep_time

    menu = s.exec(select(MenuItem).where(MenuItem.available == True)).all()  # noqa: E712
    if not menu:
        return
    by_course: dict[str, list[MenuItem]] = {}
    for m in menu:
        by_course.setdefault(m.course, []).append(m)

    order = Order(table_id=table.id, waiter_id=table.waiter_id)
    s.add(order)
    s.commit()
    s.refresh(order)

    picks: list[MenuItem] = []
    for _ in range(table.party_size):
        picks.append(rng.choice(by_course.get("Main", menu)))
        if rng.random() < 0.55:
            picks.append(rng.choice(by_course.get("Starter", menu)))
        if rng.random() < 0.7:
            picks.append(rng.choice(by_course.get("Drink", menu)))
    if rng.random() < 0.5:
        picks.append(rng.choice(by_course.get("Side", menu)))

    open_per_station: dict[str, int] = {}
    for item in picks:
        open_per_station[item.station] = open_per_station.get(item.station, 0) + 1
        low, high = predict_prep_time(s, item, open_per_station[item.station])
        s.add(OrderItem(order_id=order.id, menu_item_id=item.id, qty=1,
                        station=item.station, state=ItemState.QUEUED,
                        promised_minutes=high))
    table.status = TableStatus.COOKING
    touch(table)
    s.add(table)


# ------------------------------------------------------------------ the loop

def warm_start() -> None:
    """
    Open the doors with the restaurant already mid-service.

    A demo that starts with an empty room and a clear kitchen shows none of
    the product. This drops parties across every stage of service, with
    back-dated clocks, so the first paint has tickets cooking, food at the
    pass and one table already waiting too long.
    """
    with Session(engine) as s:
        tables = s.exec(select(DiningTable)).all()
        if any(t.status != TableStatus.AVAILABLE for t in tables):
            return                                   # already running

        now = rtime.now()
        rng.shuffle(tables)
        plan = [
            (TableStatus.DINING, 6), (TableStatus.COOKING, 5),
            (TableStatus.READY, 2), (TableStatus.SEATED, 2),
            (TableStatus.ORDERING, 2), (TableStatus.NEEDS_WAITER, 2),
            (TableStatus.BILL, 2), (TableStatus.CLEANING, 1),
        ]
        i = 0
        for status, count in plan:
            for _ in range(count):
                if i >= len(tables):
                    break
                t = tables[i]; i += 1
                seat_party(s, t)
                t.seated_at = now - timedelta(minutes=rng.randint(8, 70))
                t.status = status
                # Back-date the clock. One table gets an obviously bad one so
                # the service-risk model has something to flag on first load.
                over = rng.random() < 0.35
                backdated = now - timedelta(
                    minutes=rng.randint(6, 11) if over else rng.randint(0, 4))
                t.last_touched_at = backdated
                s.add(t)
                s.commit()

                if status in (TableStatus.COOKING, TableStatus.READY,
                              TableStatus.DINING, TableStatus.BILL):
                    fire_order(s, t)
                    t.status = status
                    s.add(t)
                    items = s.exec(select(OrderItem).join(Order).where(
                        Order.table_id == t.id)).all()
                    for oi in items:
                        oi.fired_at = now - timedelta(minutes=rng.randint(2, 18))
                        if status == TableStatus.READY:
                            oi.state, oi.ready_at = ItemState.READY, now
                        elif status in (TableStatus.DINING, TableStatus.BILL):
                            oi.state = ItemState.SERVED
                        else:
                            oi.state = rng.choice([ItemState.QUEUED, ItemState.COOKING])
                        s.add(oi)
                    # fire_order() touches the table; put the clock back or
                    # every table reads as just-served on first paint.
                    t.last_touched_at = backdated
                    s.add(t)

                if status == TableStatus.READY:
                    open_task(s, t, TaskKind.RUNNER,
                              f"Food ready at the pass for table {t.number}", 1)
                elif status == TableStatus.NEEDS_WAITER:
                    kind = rng.choice([TaskKind.WATER, TaskKind.CUTLERY, TaskKind.CALL])
                    label = {TaskKind.WATER: "asked for more water",
                             TaskKind.CUTLERY: "needs cutlery",
                             TaskKind.CALL: "pressed call waiter"}[kind]
                    open_task(s, t, kind, f"Table {t.number} {label}", 1)
                elif status == TableStatus.BILL:
                    open_task(s, t, TaskKind.BILL, f"Table {t.number} asked for the bill", 2)
                elif status == TableStatus.CLEANING:
                    open_task(s, t, TaskKind.CLEAR, f"Clear and reset table {t.number}", 3)
                s.commit()


async def simulation_loop(interval: float = 2.5) -> None:
    """One tick every few seconds. Each tick nudges a slice of the room."""
    warm_start()
    await asyncio.sleep(2)
    while True:
        try:
            changed = tick()
            if changed:
                await hub.send("state", {"changed": changed})
        except Exception as exc:                      # never kill the loop
            print("simulation tick failed:", exc)
        await asyncio.sleep(interval)


def tick() -> list[str]:
    now = rtime.now()
    changed: list[str] = []

    with Session(engine) as s:
        tables = s.exec(select(DiningTable)).all()
        free = [t for t in tables if t.status == TableStatus.AVAILABLE]

        # 1. Seat someone, if the room has space and appetite.
        occupied = sum(1 for t in tables if t.status != TableStatus.AVAILABLE)
        target = 0.55 + 0.25 * (1 if 18 <= now.hour <= 22 else 0)
        if free and occupied / len(tables) < target:
            for _ in range(rng.randint(1, 2)):
                if free and rng.random() < 0.7:
                    seat_party(s, free.pop(rng.randrange(len(free))))
                    changed.append("seated")

        # 2. Advance each occupied table one step, on its own clock.
        for t in tables:
            if t.status == TableStatus.AVAILABLE or not t.last_touched_at:
                continue
            age = (now - t.last_touched_at).total_seconds()

            if t.status == TableStatus.SEATED and age > rng.uniform(10, 24):
                t.status = TableStatus.ORDERING
                touch(t); s.add(t); changed.append("ordering")

            elif t.status == TableStatus.ORDERING and age > rng.uniform(12, 30):
                fire_order(s, t); changed.append("fired")

            elif t.status == TableStatus.COOKING:
                items = s.exec(select(OrderItem).join(Order).where(
                    Order.table_id == t.id,
                    OrderItem.state.in_([ItemState.QUEUED, ItemState.COOKING]))).all()
                for oi in items:
                    mins = (now - oi.fired_at).total_seconds() / 60
                    if oi.state == ItemState.QUEUED and mins > oi.promised_minutes * 0.06:
                        oi.state = ItemState.COOKING; s.add(oi)
                    elif oi.state == ItemState.COOKING and mins > oi.promised_minutes * 0.20:
                        oi.state = ItemState.READY; oi.ready_at = now; s.add(oi)
                if items and all(i.state == ItemState.READY for i in items):
                    t.status = TableStatus.READY
                    touch(t); s.add(t)
                    open_task(s, t, TaskKind.RUNNER,
                              f"Food ready at the pass for table {t.number}", 1)
                    changed.append("ready")

            elif t.status == TableStatus.READY and age > rng.uniform(18, 45):
                for oi in s.exec(select(OrderItem).join(Order).where(
                        Order.table_id == t.id, OrderItem.state == ItemState.READY)).all():
                    oi.state = ItemState.SERVED; s.add(oi)
                close_tasks(s, t.id, TaskKind.RUNNER)
                t.status = TableStatus.DINING
                touch(t); s.add(t); changed.append("served")

            elif t.status == TableStatus.DINING and age > rng.uniform(45, 110):
                if rng.random() < 0.28:
                    t.status = TableStatus.NEEDS_WAITER
                    kind = rng.choice([TaskKind.WATER, TaskKind.CUTLERY, TaskKind.CALL])
                    label = {TaskKind.WATER: "asked for more water",
                             TaskKind.CUTLERY: "needs cutlery",
                             TaskKind.CALL: "pressed call waiter"}[kind]
                    open_task(s, t, kind, f"Table {t.number} {label}", 1)
                else:
                    t.status = TableStatus.BILL
                    open_task(s, t, TaskKind.BILL, f"Table {t.number} asked for the bill", 2)
                touch(t); s.add(t); changed.append("request")

            elif t.status == TableStatus.NEEDS_WAITER and age > rng.uniform(25, 60):
                close_tasks(s, t.id)
                t.status = TableStatus.DINING
                touch(t); s.add(t); changed.append("resolved")

            elif t.status == TableStatus.BILL and age > rng.uniform(30, 70):
                order = s.exec(select(Order).where(
                    Order.table_id == t.id, Order.paid == False)).first()  # noqa: E712
                if order:
                    order.paid = True; order.closed_at = now
                    order.tip = round(rng.uniform(0.05, 0.16) * 100, 2)
                    s.add(order)
                close_tasks(s, t.id)
                t.status = TableStatus.CLEANING
                open_task(s, t, TaskKind.CLEAR, f"Clear and reset table {t.number}", 3)
                touch(t); s.add(t); changed.append("paid")

            elif t.status == TableStatus.CLEANING and age > rng.uniform(20, 50):
                close_tasks(s, t.id)
                t.status = TableStatus.AVAILABLE
                t.party_size = 0; t.guest_id = None; t.seated_at = None
                touch(t); s.add(t); changed.append("reset")

        s.commit()
    return changed

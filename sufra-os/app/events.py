"""The live operations stream.

One append-only table, two servers. SUFRA OS and SUFRA 360 run in separate
processes against the same database, so a websocket hub inside one of them
cannot reach the other's clients. Every real state change therefore writes
a LiveEvent row, and each server tails that table and pushes new rows to
its own sockets. That is what makes a waiter's tap in SUFRA OS light up a
guest's 3D room, and a guest's booking appear on the manager's screen,
without either process knowing the other exists.

Nothing writes a row unless something genuinely happened. There is no
generator, no filler and no random activity: an empty stream means a quiet
restaurant, and the UI says so.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from sqlmodel import Session, select

from .database import engine
from .live import hub
from .models import LiveEvent
from . import rtime

# English title -> (Azerbaijani, Russian). The stream is composed once, on
# the server, in all three languages, so a Russian manager and an English
# owner see the same event in their own words without a second round trip.
PHRASES = {
    "Reservation created": ("Rezervasiya yaradıldı", "Бронирование создано"),
    "Reservation updated": ("Rezervasiya yeniləndi", "Бронирование обновлено"),
    "Reservation cancelled": ("Rezervasiya ləğv edildi", "Бронирование отменено"),
    "Reservation moved": ("Rezervasiya köçürüldü", "Бронирование перенесено"),
    "Guest seated": ("Qonaq oturdu", "Гость посажен"),
    "Guest marked late": ("Qonaq gecikir", "Гость опаздывает"),
    "Guest marked no-show": ("Qonaq gəlmədi", "Гость не пришёл"),
    "Reservation completed": ("Rezervasiya tamamlandı", "Бронирование завершено"),
    "Table marked occupied": ("Masa dolu olaraq işarələndi", "Стол отмечен занятым"),
    "Table marked free": ("Masa boş olaraq işarələndi", "Стол отмечен свободным"),
    "Table status changed": ("Masa statusu dəyişdi", "Статус стола изменён"),
    "Waitlist entry added": ("Gözləmə siyahısına əlavə edildi", "Добавлено в лист ожидания"),
    "Waitlist converted to reservation": ("Gözləmə siyahısı rezervasiyaya çevrildi",
                                          "Лист ожидания преобразован в бронирование"),
    "Waitlist entry closed": ("Gözləmə qeydi bağlandı", "Запись листа ожидания закрыта"),
    "Menu item changed": ("Menyu maddəsi dəyişdi", "Позиция меню изменена"),
    "Menu availability changed": ("Menyu mövcudluğu dəyişdi", "Доступность меню изменена"),
    "Table held": ("Masa saxlanılır", "Стол удерживается"),
    "Hold released": ("Saxlama ləğv edildi", "Удержание снято"),
    "Guest confirmed attendance": ("Qonaq iştirakını təsdiqlədi", "Гость подтвердил визит"),
    "Confirmation sent": ("Təsdiq göndərildi", "Подтверждение отправлено"),
    "Reminder sent": ("Xatırlatma göndərildi", "Напоминание отправлено"),
}

TABLE_WORD = ("Masa", "Стол")
GUESTS_WORD = ("qonaq", "гостей")


def _translate(title: str, table_number: Optional[int], suffix_az: str = "",
               suffix_ru: str = "") -> tuple[str, str]:
    az, ru = PHRASES.get(title, (title, title))
    if table_number is not None:
        az += " — %s %d" % (TABLE_WORD[0], table_number)
        ru += " — %s %d" % (TABLE_WORD[1], table_number)
    return az + suffix_az, ru + suffix_ru


def record(s: Session, kind: str, title: str, *, detail: str = "",
           table_id: Optional[int] = None, table_number: Optional[int] = None,
           reservation_id: Optional[int] = None, waitlist_id: Optional[int] = None,
           actor: str = "SUFRA", source: str = "sufra_os",
           audience: str = "staff", severity: str = "note",
           title_az: str = "", title_ru: str = "") -> LiveEvent:
    """Append one real event. The caller must already have done the thing."""
    english = title if table_number is None else "%s — Table %d" % (title, table_number)
    if not title_az or not title_ru:
        az, ru = _translate(title, table_number)
        title_az = title_az or az
        title_ru = title_ru or ru
    ev = LiveEvent(at=rtime.now(), kind=kind, title=english, title_az=title_az,
                   title_ru=title_ru, detail=detail, table_id=table_id,
                   table_number=table_number, reservation_id=reservation_id,
                   waitlist_id=waitlist_id, actor=actor, source=source,
                   audience=audience, severity=severity)
    s.add(ev)
    return ev


def payload(ev: LiveEvent) -> dict:
    return {
        "id": ev.id, "at": ev.at.isoformat(timespec="seconds"),
        "time": ev.at.strftime("%H:%M"), "kind": ev.kind,
        "title": ev.title, "title_az": ev.title_az, "title_ru": ev.title_ru,
        "detail": ev.detail, "table_number": ev.table_number,
        "reservation_id": ev.reservation_id, "waitlist_id": ev.waitlist_id,
        "actor": ev.actor, "source": ev.source, "severity": ev.severity,
    }


def recent(s: Session, limit: int = 40, after_id: int = 0) -> list[dict]:
    q = select(LiveEvent)
    if after_id:
        q = q.where(LiveEvent.id > after_id)
    rows = s.exec(q.order_by(LiveEvent.id.desc()).limit(max(1, min(200, limit)))).all()
    return [payload(e) for e in reversed(rows)]


async def tail_loop(interval: float = 1.0) -> None:
    """Push new rows — from any process — to this server's websockets."""
    last = 0
    with Session(engine) as s:
        row = s.exec(select(LiveEvent).order_by(LiveEvent.id.desc()).limit(1)).first()
        last = row.id if row else 0
    while True:
        try:
            with Session(engine) as s:
                rows = s.exec(select(LiveEvent).where(LiveEvent.id > last)
                              .order_by(LiveEvent.id).limit(50)).all()
                fresh = [payload(e) for e in rows]
                if rows:
                    last = rows[-1].id
            if fresh:
                await hub.send("ops", {"events": fresh})
                await hub.send("state", {"changed": sorted({e["kind"] for e in fresh})})
        except Exception as exc:                      # never kill the tail
            print("[events] tail failed:", exc)
        await asyncio.sleep(interval)

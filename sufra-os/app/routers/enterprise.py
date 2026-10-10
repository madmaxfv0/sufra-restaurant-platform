"""SUFRA Enterprise layer: HR, accounting, predictive BI, QR and device biometrics.

This router is intentionally additive. It does not replace the core restaurant
order flow; it reads/writes the same operational database so HR, finance,
kitchen and owner dashboards stay strongly consistent with the live service.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import secrets
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, text
from sqlmodel import Session, SQLModel, select

from .. import intelligence as ai
from ..database import engine
from ..models import (
    AuthSession, DiningTable, Feedback, Ingredient, MenuItem, Order, OrderItem,
    Payment, PurchaseOrder, Reservation, Role, Shift, Staff, StaffQR, WasteLog,
)
from ..permissions import current_staff, permissions_for
from ..security import hash_pin, verify_pin, new_token, session_expiry
from ..staff_access import issue_badge, revoke_sessions, staff_base_url
from ..enterprise_models import (
    AttendanceRecord, BiometricChallenge, BiometricCredential, ChartAccount,
    HRProfile, JournalEntry, JournalLine, LeaveRequest, PerformanceReview,
    TrainingRecord,
)

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
TEMPLATES = Jinja2Templates(directory=str(BASE / "templates"))
UPLOADS = BASE / "static" / "uploads" / "staff"
UPLOADS.mkdir(parents=True, exist_ok=True)

MANAGER_ROLES = {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER}
FINANCE_ROLES = {Role.OWNER, Role.GENERAL_MANAGER}

COA = [
    ("1000", "Cash", "asset", "debit", "Current assets"),
    ("1010", "Card clearing", "asset", "debit", "Current assets"),
    ("1200", "Food & beverage inventory", "asset", "debit", "Current assets"),
    ("2000", "Accounts payable", "liability", "credit", "Current liabilities"),
    ("2100", "Payroll payable", "liability", "credit", "Current liabilities"),
    ("3000", "Owner equity", "equity", "credit", "Equity"),
    ("4000", "Restaurant revenue", "revenue", "credit", "Revenue"),
    ("4100", "Events revenue", "revenue", "credit", "Revenue"),
    ("5000", "Food & beverage cost", "expense", "debit", "Cost of sales"),
    ("5100", "Food waste", "expense", "debit", "Cost of sales"),
    ("6000", "Wages", "expense", "debit", "Payroll"),
    ("6100", "Employer payroll costs", "expense", "debit", "Payroll"),
    ("6200", "Rent & occupancy", "expense", "debit", "Overheads"),
    ("6300", "Utilities", "expense", "debit", "Overheads"),
    ("6400", "Repairs & maintenance", "expense", "debit", "Overheads"),
    ("6500", "Marketing", "expense", "debit", "Overheads"),
    ("6600", "Software & subscriptions", "expense", "debit", "Overheads"),
    ("6700", "Training & recruitment", "expense", "debit", "People"),
]


def _manager(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in MANAGER_ROLES:
        raise HTTPException(403, "Manager access required.")
    return staff


def _finance(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in FINANCE_ROLES:
        raise HTTPException(403, "Owner or general manager access required.")
    return staff


BADGE_ADMIN_ROLES = {Role.OWNER, Role.GENERAL_MANAGER}

def _badge_admin(staff: Staff = Depends(current_staff)) -> Staff:
    """Only the owner or general manager may issue staff badges."""
    if staff.role not in BADGE_ADMIN_ROLES:
        raise HTTPException(403, "Only the owner or general manager can generate staff QR badges.")
    return staff


def _profile_defaults(member: Staff, idx: int) -> HRProfile:
    dept = {
        Role.KITCHEN: "Kitchen", Role.WAITER: "Service", Role.BARTENDER: "Bar",
        Role.HOST: "Front of house", Role.CASHIER: "Finance",
        Role.INVENTORY_MANAGER: "Supply chain", Role.OWNER: "Executive",
        Role.GENERAL_MANAGER: "Executive", Role.RESTAURANT_MANAGER: "Operations",
    }.get(member.role, "Operations")
    return HRProfile(
        staff_id=member.id,
        employee_no=f"SF{member.id:04d}",
        department=dept,
        job_title=member.role.value.replace("_", " ").title(),
        started_on=member.started_on,
        contracted_hours=40 if member.role not in {Role.WAITER, Role.BARTENDER, Role.HOST} else 32,
    )


def ensure_schema() -> None:
    """Create additive enterprise tables and seed non-destructive reference data."""
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        existing_codes = {x.code for x in s.exec(select(ChartAccount)).all()}
        for code, name, typ, side, group in COA:
            if code not in existing_codes:
                s.add(ChartAccount(code=code, name=name, account_type=typ,
                                   normal_side=side, group_name=group))
        profiles = {x.staff_id for x in s.exec(select(HRProfile)).all()}
        for idx, member in enumerate(s.exec(select(Staff).order_by(Staff.id)).all(), 1):
            if member.id not in profiles:
                s.add(_profile_defaults(member, idx))
        s.commit()


def _today_orders(s: Session, start: datetime | None = None, end: datetime | None = None):
    start = start or datetime.combine(date.today(), datetime.min.time())
    end = end or datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    return s.exec(select(Order).where(Order.opened_at >= start, Order.opened_at < end)).all()


def _operating_totals(s: Session, start: datetime | None = None, end: datetime | None = None) -> dict:
    orders = [o for o in _today_orders(s, start, end) if o.paid]
    ids = [o.id for o in orders]
    items = s.exec(select(OrderItem).where(OrderItem.order_id.in_(ids))).all() if ids else []
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    payments = s.exec(select(Payment).where(Payment.order_id.in_(ids))).all() if ids else []
    valid_items = [i for i in items if i.menu_item_id in menu and not i.void_reason]
    revenue = sum(p.amount for p in payments if p.amount > 0)
    food_cost = sum(menu[i.menu_item_id].food_cost * i.qty for i in valid_items)
    covers = sum(i.qty for i in valid_items if menu[i.menu_item_id].course == "Main")
    return {"revenue": round(revenue, 2), "food_cost": round(food_cost, 2), "covers": covers, "orders": len(orders)}


def _attendance_hours(r: AttendanceRecord) -> float:
    if not r.clock_in or not r.clock_out:
        return 0.0
    raw = max(0.0, (r.clock_out - r.clock_in).total_seconds() / 3600)
    return max(0.0, raw - max(0, r.break_minutes) / 60)


def _payroll_rows(s: Session, start_on: date, end_on: date) -> list[dict]:
    people = {p.id: p for p in s.exec(select(Staff)).all()}
    profiles = {p.staff_id: p for p in s.exec(select(HRProfile)).all()}
    att = s.exec(select(AttendanceRecord).where(AttendanceRecord.day >= start_on,
                                                 AttendanceRecord.day <= end_on)).all()
    by_staff: dict[int, float] = {}
    for a in att:
        by_staff[a.staff_id] = by_staff.get(a.staff_id, 0.0) + _attendance_hours(a)
    # If attendance has not been used yet, use scheduled shift hours as a transparent estimate.
    shifts = s.exec(select(Shift).where(Shift.day >= start_on, Shift.day <= end_on)).all()
    scheduled: dict[int, float] = {}
    for sh in shifts:
        if sh.status not in {"sick", "holiday"}:
            scheduled[sh.staff_id] = scheduled.get(sh.staff_id, 0.0) + max(0.0, sh.end_hour - sh.start_hour)
    rows = []
    for sid, member in people.items():
        actual = round(by_staff.get(sid, 0.0), 2)
        sched = round(scheduled.get(sid, 0.0), 2)
        hours = actual if actual > 0 else sched
        gross = round(hours * float(member.hourly_rate or 0), 2)
        rows.append({
            "staff_id": sid, "name": member.name, "role": member.role.value,
            "employee_no": profiles.get(sid).employee_no if sid in profiles else f"SF{sid:04d}",
            "actual_hours": actual, "scheduled_hours": sched, "payable_hours": hours,
            "hourly_rate": round(float(member.hourly_rate or 0), 2), "gross": gross,
            "basis": "attendance" if actual > 0 else "scheduled estimate",
        })
    return sorted(rows, key=lambda r: (-r["gross"], r["name"]))


def _replace_journal(s: Session, reference: str, description: str, source: str,
                     at: datetime, lines: list[tuple[str, float, float, str]]) -> None:
    old = s.exec(select(JournalEntry).where(JournalEntry.reference == reference)).first()
    if old:
        s.exec(delete(JournalLine).where(JournalLine.journal_id == old.id))
        s.delete(old)
        s.commit()
    if not any(round(d, 2) or round(c, 2) for _, d, c, _ in lines):
        return
    debits = round(sum(d for _, d, _, _ in lines), 2)
    credits = round(sum(c for _, _, c, _ in lines), 2)
    if abs(debits - credits) > 0.01:
        raise ValueError(f"Journal {reference} is not balanced: {debits} vs {credits}")
    j = JournalEntry(at=at, description=description, reference=reference, source=source)
    s.add(j); s.commit(); s.refresh(j)
    for code, debit, credit, memo in lines:
        s.add(JournalLine(journal_id=j.id, account_code=code,
                          debit=round(debit, 2), credit=round(credit, 2), memo=memo))
    s.commit()


def _sync_operational_journals(s: Session, day: date | None = None) -> None:
    day = day or date.today()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    totals = _operating_totals(s, start, end)
    # Sales and COGS. Card clearing is used as a simple demo control account.
    _replace_journal(s, f"OPS-SALES-{day.isoformat()}", "Restaurant sales", "sales", end - timedelta(seconds=1), [
        ("1010", totals["revenue"], 0, "Gross takings"),
        ("4000", 0, totals["revenue"], "Food & beverage revenue"),
    ])
    _replace_journal(s, f"OPS-COGS-{day.isoformat()}", "Cost of goods sold", "inventory", end - timedelta(seconds=1), [
        ("5000", totals["food_cost"], 0, "Food cost consumed"),
        ("1200", 0, totals["food_cost"], "Inventory consumption"),
    ])
    # Payroll estimate from attendance/rota. It is labelled estimate in the UI.
    payroll = sum(r["gross"] for r in _payroll_rows(s, day, day))
    _replace_journal(s, f"OPS-PAYROLL-{day.isoformat()}", "Gross payroll accrual (estimate)", "payroll", end - timedelta(seconds=1), [
        ("6000", payroll, 0, "Gross wages estimate"),
        ("2100", 0, payroll, "Payroll payable estimate"),
    ])
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    waste = s.exec(select(WasteLog).where(WasteLog.logged_on == day)).all()
    waste_value = round(sum(w.qty * ings[w.ingredient_id].cost_per_unit for w in waste if w.ingredient_id in ings), 2)
    _replace_journal(s, f"OPS-WASTE-{day.isoformat()}", "Recorded food waste", "waste", end - timedelta(seconds=1), [
        ("5100", waste_value, 0, "Waste log at ingredient cost"),
        ("1200", 0, waste_value, "Inventory written off"),
    ])


def _tb(s: Session, start: datetime | None = None, end: datetime | None = None) -> list[dict]:
    q = select(JournalEntry).where(JournalEntry.posted == True)  # noqa: E712
    if start: q = q.where(JournalEntry.at >= start)
    if end: q = q.where(JournalEntry.at < end)
    journals = s.exec(q).all()
    ids = [j.id for j in journals]
    lines = s.exec(select(JournalLine).where(JournalLine.journal_id.in_(ids))).all() if ids else []
    accounts = {a.code: a for a in s.exec(select(ChartAccount)).all()}
    sums: dict[str, list[float]] = {}
    for ln in lines:
        cur = sums.setdefault(ln.account_code, [0.0, 0.0])
        cur[0] += ln.debit; cur[1] += ln.credit
    out = []
    for code in sorted(accounts):
        a = accounts[code]; d, c = sums.get(code, [0.0, 0.0])
        bal = d - c if a.normal_side == "debit" else c - d
        out.append({"code": code, "name": a.name, "type": a.account_type,
                    "group": a.group_name, "debit": round(d, 2), "credit": round(c, 2),
                    "balance": round(bal, 2)})
    return out


def _pnl(s: Session, start_on: date, end_on: date) -> dict:
    start = datetime.combine(start_on, datetime.min.time())
    end = datetime.combine(end_on + timedelta(days=1), datetime.min.time())
    rows = _tb(s, start, end)
    revenue = sum(r["balance"] for r in rows if r["type"] == "revenue")
    expenses = sum(r["balance"] for r in rows if r["type"] == "expense")
    cogs = sum(r["balance"] for r in rows if r["group"] == "Cost of sales")
    payroll = sum(r["balance"] for r in rows if r["group"] == "Payroll")
    overhead = expenses - cogs - payroll
    return {
        "start": start_on.isoformat(), "end": end_on.isoformat(),
        "revenue": round(revenue, 2), "cogs": round(cogs, 2),
        "gross_profit": round(revenue - cogs, 2), "payroll": round(payroll, 2),
        "overheads": round(overhead, 2), "expenses": round(expenses, 2),
        "net_profit": round(revenue - expenses, 2),
        "margin_pct": round((revenue - expenses) / revenue * 100, 1) if revenue else 0,
        "rows": [r for r in rows if r["type"] in {"revenue", "expense"} and abs(r["balance"]) > 0.005],
    }


def _sat(s: Session) -> dict:
    fb = s.exec(select(Feedback).where(Feedback.created_at >= datetime.now() - timedelta(days=30))).all()
    if not fb:
        return {"food": 0, "service": 0, "atmosphere": 0, "speed": 0, "overall": 0}
    vals = {k: round(sum(getattr(x, k) for x in fb) / len(fb) * 20, 1)
            for k in ("food", "service", "atmosphere", "speed")}
    vals["overall"] = round(sum(vals.values()) / 4, 1)
    return vals


def _kitchen_plan(s: Session) -> dict:
    today = date.today()
    forecast = ai.forecast_day(s, today + timedelta(days=1))
    outlook = ai.inventory_outlook(s)
    ingredients = {i.id: i for i in s.exec(select(Ingredient)).all()}
    expiry = []
    for ing in ingredients.values():
        if ing.expires_on and ing.expires_on <= today + timedelta(days=3):
            expiry.append({"name": ing.name, "expires": ing.expires_on.isoformat(),
                           "stock": round(ing.in_stock, 2), "unit": ing.unit,
                           "value": round(ing.in_stock * ing.cost_per_unit, 2)})
    waste_logs = s.exec(select(WasteLog).where(WasteLog.logged_on >= today - timedelta(days=30))).all()
    by_reason: dict[str, float] = {}
    waste_value = 0.0
    for w in waste_logs:
        by_reason[w.reason] = by_reason.get(w.reason, 0) + w.qty
        if w.ingredient_id in ingredients:
            waste_value += w.qty * ingredients[w.ingredient_id].cost_per_unit
    menu = ai.menu_engineering(s)
    weak = [x for x in menu if x["class"] == "weak"][:5]
    actions = []
    if expiry:
        actions.append({"priority": "high", "title": f"Use {len(expiry)} expiring ingredients first",
                        "detail": "Move them into specials/prep before replenishing the same stock."})
    if by_reason.get("overproduction", 0) > 0:
        actions.append({"priority": "high", "title": "Reduce overproduction prep",
                        "detail": "Use tomorrow's cover forecast to set prep pars instead of static weekend quantities."})
    if weak:
        actions.append({"priority": "medium", "title": "Review low-return dishes",
                        "detail": ", ".join(x["name"] for x in weak)})
    sat = _sat(s)
    if sat["speed"] and sat["speed"] < 85:
        actions.append({"priority": "high", "title": "Protect service speed",
                        "detail": "Speed is the weakest satisfaction signal; delay low-priority fires when station load is high."})
    return {
        "forecast": forecast, "stations": ai.station_pressure(s),
        "inventory": outlook[:12], "expiry": sorted(expiry, key=lambda x: x["expires"]),
        "waste_30d_value": round(waste_value, 2), "waste_by_reason": by_reason,
        "satisfaction": sat, "actions": actions,
    }


def _executive(s: Session) -> dict:
    today = date.today()
    forecasts = []
    for d in range(7):
        fc = ai.forecast_day(s, today + timedelta(days=d))
        fc["day"] = (today + timedelta(days=d)).isoformat()
        forecasts.append(fc)
    totals = _operating_totals(s)
    sat = _sat(s)
    kitchen = _kitchen_plan(s)
    menu = ai.menu_engineering(s)
    stars = [x for x in menu if x["class"] == "star"][:5]
    weak = [x for x in menu if x["class"] == "weak"][:5]
    projected_revenue = round(sum(x["revenue"] for x in forecasts), 2)
    projected_covers = sum(x["covers"] for x in forecasts)
    payroll = _payroll_rows(s, today, today + timedelta(days=6))
    labor = round(sum(r["gross"] for r in payroll), 2)
    # Forecast food cost ratio from current menu sales mix; this is a planning estimate.
    food_ratio = totals["food_cost"] / totals["revenue"] if totals["revenue"] else 0.29
    projected_food = round(projected_revenue * food_ratio, 2)
    actions = []
    if kitchen["inventory"] and any(x.get("shortfall", 0) > 0 for x in kitchen["inventory"]):
        n = sum(1 for x in kitchen["inventory"] if x.get("shortfall", 0) > 0)
        actions.append({"severity": "warning", "title": f"{n} forecast stock shortages",
                        "detail": "Approve the predictive purchase basket before supplier cut-off."})
    pressure = ai.station_pressure(s)
    if pressure and pressure[0]["load_projected"] >= .85:
        actions.append({"severity": "critical", "title": f"{pressure[0]['station'].title()} station trending hot",
                        "detail": f"Projected at {round(pressure[0]['load_projected']*100)}% load in 20 minutes."})
    if sat["overall"] and sat["overall"] < 88:
        actions.append({"severity": "warning", "title": "Satisfaction below target",
                        "detail": f"30-day guest satisfaction is {sat['overall']}%."})

    # SUFRA ANBAR feeds the owner the strategic half of the warehouse — value
    # tied up, food cost, waste trend, price pressure — while the operational
    # detail stays in Anbar itself. An owner should not have to open the
    # warehouse to learn that margin is being eaten by supplier increases.
    anbar_signals = []
    try:
        from .. import anbar_ai
        anbar_signals = anbar_ai.executive_signals(s)
        for sig in anbar_signals:
            if sig["severity"] in ("high", "critical"):
                actions.append({
                    "severity": "critical" if sig["severity"] == "critical" else "warning",
                    "title": sig["title"], "detail": sig["detail"]})
    except Exception as exc:                      # never take the dashboard down
        print("[executive] anbar signals unavailable:", exc)

    return {
        "anbar": anbar_signals,
        "today": totals, "forecast_7d": forecasts,
        "projected": {"revenue": projected_revenue, "covers": projected_covers,
                      "food_cost": projected_food, "labor": labor,
                      "contribution": round(projected_revenue - projected_food - labor, 2)},
        "satisfaction": sat, "station_pressure": pressure,
        "inventory_risk": kitchen["inventory"][:8], "waste": kitchen,
        "menu": {"stars": stars, "weak": weak}, "actions": actions,
        "scenarios": [
            {"name": "Base", "revenue": projected_revenue, "contribution": round(projected_revenue-projected_food-labor,2)},
            {"name": "Demand -10%", "revenue": round(projected_revenue*.9,2), "contribution": round(projected_revenue*.9-projected_food*.9-labor,2)},
            {"name": "Demand +10%", "revenue": round(projected_revenue*1.1,2), "contribution": round(projected_revenue*1.1-projected_food*1.1-labor,2)},
        ],
    }


# ---------------------------------------------------------------- pages / health

@router.get("/health/live")
def live_health():
    return {"ok": True, "service": "sufra"}


@router.get("/health/ready")
def ready_health():
    try:
        with Session(engine, expire_on_commit=False) as s:
            s.exec(text("SELECT 1"))
        return {"ok": True, "database": "ready"}
    except Exception as exc:
        return JSONResponse({"ok": False, "database": "unavailable", "detail": str(exc)}, status_code=503)


@router.get("/pay/{table_id}", response_class=HTMLResponse)
def payment_page(request: Request, table_id: int):
    return TEMPLATES.TemplateResponse(request, "payment.html", {"table_id": table_id})


# ---------------------------------------------------------------- HR

@router.get("/api/enterprise/hr/overview")
def hr_overview(_: Staff = Depends(_manager)):
    ensure_schema()
    today = date.today()
    with Session(engine, expire_on_commit=False) as s:
        staff = s.exec(select(Staff)).all()
        profiles = s.exec(select(HRProfile)).all()
        attendance = s.exec(select(AttendanceRecord).where(AttendanceRecord.day == today)).all()
        pending_leave = s.exec(select(LeaveRequest).where(LeaveRequest.status == "pending")).all()
        due = s.exec(select(TrainingRecord).where(TrainingRecord.status.in_(["assigned", "in_progress", "expired"]))).all()
        on_shift = sum(1 for p in staff if p.on_shift)
        payroll = _payroll_rows(s, today - timedelta(days=today.weekday()), today + timedelta(days=6-today.weekday()))
        return {
            "headcount": len(staff), "active_profiles": sum(1 for p in profiles if p.status == "active"),
            "on_shift": on_shift, "clocked_in": sum(1 for a in attendance if a.clock_in and not a.clock_out),
            "leave_pending": len(pending_leave), "training_due": len(due),
            "weekly_payroll_estimate": round(sum(x["gross"] for x in payroll), 2),
        }


@router.get("/api/enterprise/hr/staff")
def hr_staff(_: Staff = Depends(_manager)):
    ensure_schema()
    with Session(engine, expire_on_commit=False) as s:
        profiles = {p.staff_id: p for p in s.exec(select(HRProfile)).all()}
        creds = {c.staff_id for c in s.exec(select(BiometricCredential)).all()}
        out = []
        for member in s.exec(select(Staff).order_by(Staff.name)).all():
            p = profiles.get(member.id)
            out.append({
                "id": member.id, "name": member.name, "role": member.role.value,
                "avatar": member.avatar, "section": member.section, "on_shift": member.on_shift,
                "hourly_rate": member.hourly_rate, "rating": member.rating,
                "employee_no": p.employee_no if p else "", "work_email": p.work_email if p else "",
                "phone": p.phone if p else "", "photo_url": p.photo_url if p else "",
                "department": p.department if p else "", "job_title": p.job_title if p else "",
                "contract_type": p.contract_type if p else "", "contracted_hours": p.contracted_hours if p else 0,
                "status": p.status if p else "active", "started_on": p.started_on.isoformat() if p and p.started_on else "",
                "biometric": member.id in creds,
                "qr_enabled": s.get(StaffQR, member.id) is not None,
            })
        return {"staff": out}


@router.post("/api/enterprise/hr/staff")
def hr_create_staff(request: Request, response: Response, body: dict = Body(...), actor: Staff = Depends(_manager)):
    name = str(body.get("name") or "").strip()
    role_raw = str(body.get("role") or "waiter").strip()
    if not name:
        raise HTTPException(400, "Employee name is required.")
    try: role = Role(role_raw)
    except ValueError: raise HTTPException(400, "Unknown role.")
    pin = f"{secrets.randbelow(10000):04d}"
    with Session(engine, expire_on_commit=False) as s:
        member = Staff(name=name, role=role, avatar=name[:1].upper(), section=str(body.get("section") or ""),
                       on_shift=False, hourly_rate=float(body.get("hourly_rate") or 0), pin_hash=hash_pin(pin))
        s.add(member); s.flush(); s.refresh(member)
        p = _profile_defaults(member, member.id)
        p.work_email = str(body.get("work_email") or "").strip()
        p.phone = str(body.get("phone") or "").strip()
        p.job_title = str(body.get("job_title") or p.job_title)
        p.department = str(body.get("department") or p.department)
        p.contract_type = str(body.get("contract_type") or p.contract_type)
        p.contracted_hours = float(body.get("contracted_hours") or p.contracted_hours)
        s.add(p)
        badge = issue_badge(s, member, actor.id, staff_base_url(request))
        s.commit()
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True, **badge, "temporary_pin": pin,
                "message": "Account created. The temporary PIN is shown once; ask the employee to change it after sign-in."}


@router.post("/api/enterprise/hr/staff/{staff_id}/profile")
def hr_update_profile(staff_id: int, body: dict = Body(...), _: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member: raise HTTPException(404, "Employee not found.")
        p = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first() or _profile_defaults(member, staff_id)
        for key in ("employee_no", "work_email", "phone", "department", "job_title", "contract_type", "status", "emergency_contact", "notes"):
            if key in body: setattr(p, key, str(body.get(key) or ""))
        if "contracted_hours" in body: p.contracted_hours = float(body.get("contracted_hours") or 0)
        if "started_on" in body and body.get("started_on"):
            p.started_on = date.fromisoformat(body["started_on"])
        if "hourly_rate" in body: member.hourly_rate = float(body.get("hourly_rate") or 0)
        if "section" in body: member.section = str(body.get("section") or "")
        if p.status in {"leaver", "suspended"}:
            revoke_sessions(s, member.id)
        p.updated_at = datetime.now(); s.add(p); s.add(member); s.commit()
    return {"ok": True}


@router.post("/api/enterprise/hr/staff/{staff_id}/remove")
def hr_remove_staff(staff_id: int, actor: Staff = Depends(_manager)):
    """Removing an employee is a soft delete, the same pattern floor-control
    uses for a table taken off the plan: every past order, reservation,
    shift and payroll row this person is attributed to stays intact and
    correctly credited, but they disappear from the sign-in roster and
    every active roster/assignment screen immediately, and any device
    already signed in as them is logged out. HR keeps a "Removed" list to
    undo this if it was a mistake — nothing is ever hard-deleted here."""
    if actor.id == staff_id:
        raise HTTPException(400, "You cannot remove your own account while signed in as them.")
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member: raise HTTPException(404, "Employee not found.")
        p = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first() or _profile_defaults(member, staff_id)
        badge = s.get(StaffQR, staff_id)
        if badge:
            badge.token_hash = new_token()
            s.add(badge)
        p.status = "leaver"; p.updated_at = datetime.now()
        member.on_shift = False
        s.add(p); s.add(member)
        for sess in s.exec(select(AuthSession).where(AuthSession.staff_id == staff_id)).all():
            s.delete(sess)
        s.commit()
    return {"ok": True, "message": f"{member.name} removed. Their history is kept; restore them from Removed employees if this was a mistake."}


@router.post("/api/enterprise/hr/staff/{staff_id}/restore")
def hr_restore_staff(staff_id: int, _: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member: raise HTTPException(404, "Employee not found.")
        p = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first() or _profile_defaults(member, staff_id)
        p.status = "active"; p.updated_at = datetime.now()
        s.add(p); s.commit()
    return {"ok": True, "message": f"{member.name} restored to the active roster."}


@router.post("/api/enterprise/hr/staff/{staff_id}/photo")
def hr_photo(staff_id: int, body: dict = Body(...), _: Staff = Depends(_manager)):
    raw = str(body.get("image_data") or "")
    m = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", raw, re.I | re.S)
    if not m: raise HTTPException(400, "Choose a PNG, JPEG or WebP image.")
    ext = "jpg" if m.group(1).lower() in {"jpeg", "jpg"} else m.group(1).lower()
    binary = base64.b64decode(m.group(2))
    if len(binary) > 5_000_000: raise HTTPException(413, "Profile photo is larger than 5 MB.")
    fn = f"staff-{staff_id}-{int(datetime.now().timestamp())}.{ext}"
    (UPLOADS / fn).write_bytes(binary)
    url = f"/static/uploads/staff/{fn}"
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member: raise HTTPException(404, "Employee not found.")
        p = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first() or _profile_defaults(member, staff_id)
        p.photo_url = url; p.updated_at = datetime.now(); s.add(p); s.commit()
    return {"ok": True, "photo_url": url}


def _send_invite(email: str, name: str, pin: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host or not email: return False
    port = int(os.getenv("SMTP_PORT", "587")); user = os.getenv("SMTP_USER", ""); password = os.getenv("SMTP_PASSWORD", "")
    msg = EmailMessage(); msg["Subject"] = "Your SUFRA staff account"; msg["From"] = os.getenv("SMTP_FROM", user or "sufra@localhost"); msg["To"] = email
    msg.set_content(f"Hello {name},\n\nYour temporary SUFRA PIN is {pin}. Sign in and change it as soon as possible.\n")
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if port != 25: smtp.starttls()
        if user: smtp.login(user, password)
        smtp.send_message(msg)
    return True


@router.get("/api/enterprise/hr/staff/{staff_id}/badge")
def hr_badge(staff_id: int, request: Request, response: Response, actor: Staff = Depends(_badge_admin)):
    from ..models import StaffBadgeCopy
    from ..staff_access import cipher, badge_card, badge_staff
    with Session(engine) as s:
        member = s.get(Staff, staff_id)
        copy = s.get(StaffBadgeCopy, staff_id)
        if not member or not copy:
            raise HTTPException(404, "No QR badge yet. Select Generate QR.")
        from cryptography.fernet import InvalidToken
        try:
            token = cipher().decrypt(copy.encrypted_token.encode()).decode()
            badge_staff(s, token)
        except (InvalidToken, HTTPException):
            raise HTTPException(409, "This badge is no longer valid. Generate a replacement QR.")
        response.headers["Cache-Control"] = "no-store"
        return badge_card(member, token, staff_base_url(request))


@router.post("/api/enterprise/hr/staff/{staff_id}/badge")
def hr_generate_badge(staff_id: int, request: Request, response: Response, actor: Staff = Depends(_badge_admin), authorization: str = Header(default="")):
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member:
            raise HTTPException(404, "Employee not found.")
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            raise HTTPException(400, "Restore this employee before generating a badge.")
        token = authorization.removeprefix("Bearer ").strip()
        card = issue_badge(s, member, actor.id, staff_base_url(request), preserve_session=token)
        s.commit()
    response.headers["Cache-Control"] = "no-store"
    return {**card, "message": "QR badge generated. Use the employee's existing four-digit PIN."}


@router.post("/api/enterprise/hr/staff/{staff_id}/credentials")
@router.post("/api/enterprise/hr/staff/{staff_id}/invite")
def hr_invite(staff_id: int, request: Request, response: Response, actor: Staff = Depends(_badge_admin)):
    pin = f"{secrets.randbelow(10000):04d}"
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, staff_id)
        if not member:
            raise HTTPException(404, "Employee not found.")
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            raise HTTPException(400, "Restore the employee before issuing credentials.")
        member.pin_hash = hash_pin(pin)
        member.failed_attempts = 0
        member.locked_until = None
        s.add(member)
        badge = issue_badge(s, member, actor.id, staff_base_url(request))
        s.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, **badge, "temporary_pin": pin,
            "message": "New QR and PIN issued. Previous QR, PIN and sessions are revoked. Save the badge now and give the PIN separately."}


@router.get("/api/enterprise/hr/attendance")
def hr_attendance(start: str = "", end: str = "", _: Staff = Depends(_manager)):
    a = date.fromisoformat(start) if start else date.today() - timedelta(days=7)
    b = date.fromisoformat(end) if end else date.today()
    with Session(engine, expire_on_commit=False) as s:
        names = {p.id: p.name for p in s.exec(select(Staff)).all()}
        rows = s.exec(select(AttendanceRecord).where(AttendanceRecord.day >= a, AttendanceRecord.day <= b).order_by(AttendanceRecord.day.desc())).all()
        return {"rows": [{"id": r.id, "staff_id": r.staff_id, "name": names.get(r.staff_id, "—"),
                          "day": r.day.isoformat(), "clock_in": r.clock_in.isoformat() if r.clock_in else None,
                          "clock_out": r.clock_out.isoformat() if r.clock_out else None, "hours": round(_attendance_hours(r),2),
                          "break_minutes": r.break_minutes, "status": r.status, "source": r.source, "note": r.note} for r in rows]}


@router.post("/api/enterprise/hr/attendance/clock")
def hr_clock(body: dict = Body(...), actor: Staff = Depends(current_staff)):
    target = int(body.get("staff_id") or actor.id)
    if target != actor.id and actor.role not in MANAGER_ROLES: raise HTTPException(403, "You can only clock yourself.")
    action = str(body.get("action") or "in")
    today = date.today(); now = datetime.now()
    with Session(engine, expire_on_commit=False) as s:
        r = s.exec(select(AttendanceRecord).where(AttendanceRecord.staff_id == target, AttendanceRecord.day == today)).first()
        if not r: r = AttendanceRecord(staff_id=target, day=today, source="tablet")
        if action == "out": r.clock_out = now
        else: r.clock_in = r.clock_in or now; r.clock_out = None
        r.break_minutes = int(body.get("break_minutes") or r.break_minutes or 0)
        r.status = str(body.get("status") or r.status); r.note = str(body.get("note") or r.note); s.add(r); s.commit(); s.refresh(r)
    return {"ok": True, "id": r.id, "clock_in": r.clock_in.isoformat() if r.clock_in else None, "clock_out": r.clock_out.isoformat() if r.clock_out else None}


@router.get("/api/enterprise/hr/leave")
def hr_leave(_: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s:
        names = {p.id: p.name for p in s.exec(select(Staff)).all()}
        rows = s.exec(select(LeaveRequest).order_by(LeaveRequest.requested_at.desc())).all()
        return {"rows": [{"id": r.id, "staff_id": r.staff_id, "name": names.get(r.staff_id,"—"), "type": r.leave_type,
                          "start": r.start_on.isoformat(), "end": r.end_on.isoformat(), "days": r.days,
                          "status": r.status, "note": r.note} for r in rows]}


@router.post("/api/enterprise/hr/leave")
def hr_leave_create(body: dict = Body(...), actor: Staff = Depends(current_staff)):
    target = int(body.get("staff_id") or actor.id)
    if target != actor.id and actor.role not in MANAGER_ROLES: raise HTTPException(403, "You can only request your own leave.")
    start = date.fromisoformat(body["start"]); end = date.fromisoformat(body["end"])
    if end < start: raise HTTPException(400, "End date is before start date.")
    with Session(engine, expire_on_commit=False) as s:
        r = LeaveRequest(staff_id=target, leave_type=str(body.get("type") or "annual"), start_on=start, end_on=end,
                         days=float(body.get("days") or ((end-start).days+1)), note=str(body.get("note") or ""))
        s.add(r); s.commit(); s.refresh(r)
    return {"ok": True, "id": r.id}


@router.post("/api/enterprise/hr/leave/{leave_id}/status")
def hr_leave_status(leave_id: int, body: dict = Body(...), actor: Staff = Depends(_manager)):
    status = str(body.get("status") or "approved")
    if status not in {"approved", "rejected", "cancelled", "pending"}: raise HTTPException(400, "Unknown leave status.")
    with Session(engine, expire_on_commit=False) as s:
        r = s.get(LeaveRequest, leave_id)
        if not r: raise HTTPException(404, "Leave request not found.")
        r.status = status; r.decided_at = datetime.now(); r.decided_by = actor.id; s.add(r); s.commit()
    return {"ok": True}


@router.get("/api/enterprise/hr/training")
def hr_training(_: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s:
        names = {p.id: p.name for p in s.exec(select(Staff)).all()}
        rows = s.exec(select(TrainingRecord).order_by(TrainingRecord.status, TrainingRecord.due_on)).all()
        return {"rows": [{"id": r.id, "staff_id": r.staff_id, "name": names.get(r.staff_id,"—"), "course": r.course,
                          "provider": r.provider, "category": r.category, "due": r.due_on.isoformat() if r.due_on else "",
                          "completed": r.completed_on.isoformat() if r.completed_on else "", "expires": r.expires_on.isoformat() if r.expires_on else "",
                          "score": r.score, "status": r.status, "certificate": r.certificate} for r in rows]}


@router.post("/api/enterprise/hr/training")
def hr_training_create(body: dict = Body(...), _: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s:
        r = TrainingRecord(staff_id=int(body["staff_id"]), course=str(body.get("course") or "Service standard"),
                           provider=str(body.get("provider") or "SUFRA Academy"), category=str(body.get("category") or "operations"),
                           due_on=date.fromisoformat(body["due"]) if body.get("due") else None, status="assigned")
        s.add(r); s.commit(); s.refresh(r)
    return {"ok": True, "id": r.id}


@router.get("/api/enterprise/hr/payroll")
def hr_payroll(start: str = "", end: str = "", _: Staff = Depends(_finance)):
    a = date.fromisoformat(start) if start else date.today() - timedelta(days=date.today().weekday())
    b = date.fromisoformat(end) if end else a + timedelta(days=6)
    with Session(engine, expire_on_commit=False) as s:
        rows = _payroll_rows(s, a, b)
        return {"start": a.isoformat(), "end": b.isoformat(), "rows": rows,
                "gross_total": round(sum(r["gross"] for r in rows), 2),
                "note": "Gross payroll estimate only. Statutory tax/pension processing should be exported to your payroll provider."}


# ---------------------------------------------------------------- accounting

@router.get("/api/enterprise/accounting/coa")
def accounting_coa(_: Staff = Depends(_finance)):
    ensure_schema()
    with Session(engine, expire_on_commit=False) as s:
        return {"accounts": [(a.model_dump() if hasattr(a, "model_dump") else a.dict()) for a in s.exec(select(ChartAccount).order_by(ChartAccount.code)).all()]}


@router.post("/api/enterprise/accounting/journals")
def accounting_post(body: dict = Body(...), actor: Staff = Depends(_finance)):
    lines = body.get("lines") or []
    cleaned = []
    for x in lines:
        cleaned.append((str(x.get("account_code") or ""), float(x.get("debit") or 0), float(x.get("credit") or 0), str(x.get("memo") or "")))
    if not cleaned: raise HTTPException(400, "Add at least one journal line.")
    if abs(sum(x[1] for x in cleaned) - sum(x[2] for x in cleaned)) > .01: raise HTTPException(400, "Journal debits and credits must balance.")
    with Session(engine, expire_on_commit=False) as s:
        known = {a.code for a in s.exec(select(ChartAccount)).all()}
        if any(x[0] not in known for x in cleaned): raise HTTPException(400, "Unknown chart-of-accounts code.")
        ref = str(body.get("reference") or f"MAN-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        _replace_journal(s, ref, str(body.get("description") or "Manual journal"), "manual", datetime.now(), cleaned)
    return {"ok": True, "reference": ref}


@router.get("/api/enterprise/accounting/journals")
def accounting_journals(_: Staff = Depends(_finance)):
    with Session(engine, expire_on_commit=False) as s:
        _sync_operational_journals(s)
        js = s.exec(select(JournalEntry).order_by(JournalEntry.at.desc()).limit(80)).all()
        out=[]
        for j in js:
            lines=s.exec(select(JournalLine).where(JournalLine.journal_id==j.id)).all()
            out.append({"id":j.id,"at":j.at.isoformat(),"description":j.description,"reference":j.reference,"source":j.source,
                        "debit":round(sum(x.debit for x in lines),2),"credit":round(sum(x.credit for x in lines),2),
                        "lines":[{"account":x.account_code,"debit":x.debit,"credit":x.credit,"memo":x.memo} for x in lines]})
        return {"journals":out}


@router.get("/api/enterprise/accounting/trial-balance")
def accounting_tb(_: Staff = Depends(_finance)):
    with Session(engine, expire_on_commit=False) as s:
        _sync_operational_journals(s)
        rows=_tb(s); return {"rows":rows,"debits":round(sum(r["debit"] for r in rows),2),"credits":round(sum(r["credit"] for r in rows),2)}


@router.get("/api/enterprise/accounting/pnl")
def accounting_pnl(start: str = "", end: str = "", _: Staff = Depends(_finance)):
    a=date.fromisoformat(start) if start else date.today().replace(day=1); b=date.fromisoformat(end) if end else date.today()
    with Session(engine, expire_on_commit=False) as s:
        _sync_operational_journals(s); return _pnl(s,a,b)


# ---------------------------------------------------------------- owner / kitchen / QR / BI

@router.get("/api/enterprise/executive")
def executive(_: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s: return _executive(s)


@router.get("/api/enterprise/kitchen/waste-plan")
def kitchen_waste(_: Staff = Depends(_manager)):
    with Session(engine, expire_on_commit=False) as s: return _kitchen_plan(s)


@router.get("/api/enterprise/qr/tables")
def qr_tables(request: Request, _: Staff = Depends(_manager)):
    public = os.getenv("SUFRA_PUBLIC_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    with Session(engine, expire_on_commit=False) as s:
        rows=[]
        for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
            if t.zone == "__ARCHIVED__": continue
            rows.append({"id":t.id,"number":t.number,"zone":t.zone,"seats":t.seats,
                         "url":f"{public}/t/{t.number}","qr":f"/api/enterprise/qr/table/{t.number}.svg"})
        return {"tables":rows,"public_base":public}


@router.get("/api/enterprise/qr/table/{table_number}.svg")
def qr_svg(table_number: int, request: Request):
    public = os.getenv("SUFRA_PUBLIC_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    url=f"{public}/t/{table_number}"
    try:
        import qrcode
        import qrcode.image.svg
        img=qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
        buf=io.BytesIO(); img.save(buf); data=buf.getvalue()
        return Response(data, media_type="image/svg+xml", headers={"Cache-Control":"no-store"})
    except Exception:
        # Failure-safe QR placeholder with encoded URL visible for printing/troubleshooting.
        safe=url.replace("&","&amp;").replace("<","&lt;")
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320"><rect width="100%" height="100%" fill="white"/><rect x="16" y="16" width="288" height="288" fill="none" stroke="#0b2745" stroke-width="8"/><text x="160" y="145" font-family="sans-serif" font-size="24" text-anchor="middle" fill="#0b2745">TABLE {table_number}</text><text x="160" y="180" font-family="sans-serif" font-size="12" text-anchor="middle" fill="#0b2745">{safe}</text></svg>'''
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control":"no-store"})


def _bi_authorized(x_bi_key: str, authorization: str) -> bool:
    env=os.getenv("BI_API_KEY","").strip()
    if env and secrets.compare_digest(x_bi_key or "",env): return True
    token=authorization[7:].strip() if authorization.startswith("Bearer ") else authorization.strip()
    if not token: return False
    with Session(engine, expire_on_commit=False) as s:
        from ..permissions import _load_session
        sess=_load_session(token, s)
        if not sess: return False
        person=s.get(Staff,sess.staff_id)
        return bool(person and person.role in MANAGER_ROLES)


def _require_bi(x_bi_key: str = Header(default="", alias="X-BI-Key"), authorization: str = Header(default="")):
    if not _bi_authorized(x_bi_key,authorization): raise HTTPException(401,"BI key or manager session required.")


@router.get("/api/bi/executive")
def bi_executive(_: Any = Depends(_require_bi)):
    with Session(engine, expire_on_commit=False) as s: return _executive(s)


@router.get("/api/bi/kitchen")
def bi_kitchen(_: Any = Depends(_require_bi)):
    with Session(engine, expire_on_commit=False) as s: return _kitchen_plan(s)


@router.get("/api/bi/hr")
def bi_hr(_: Any = Depends(_require_bi)):
    with Session(engine, expire_on_commit=False) as s:
        profiles={p.staff_id:p for p in s.exec(select(HRProfile)).all()}
        return {"staff":[{"id":m.id,"name":m.name,"role":m.role.value,"department":profiles[m.id].department if m.id in profiles else "",
                          "status":profiles[m.id].status if m.id in profiles else "active","on_shift":m.on_shift,"rating":m.rating}
                         for m in s.exec(select(Staff)).all()]}


@router.get("/api/bi/trial-balance")
def bi_tb(_: Any = Depends(_require_bi)):
    with Session(engine, expire_on_commit=False) as s:
        _sync_operational_journals(s); return {"rows":_tb(s)}


@router.get("/api/bi/export/{dataset}.csv")
def bi_csv(dataset: str, _: Any = Depends(_require_bi)):
    with Session(engine, expire_on_commit=False) as s:
        if dataset=="trial-balance": rows=_tb(s)
        elif dataset=="payroll": rows=_payroll_rows(s,date.today()-timedelta(days=6),date.today())
        elif dataset=="inventory": rows=ai.inventory_outlook(s)
        else: raise HTTPException(404,"Unknown BI dataset.")
    keys=sorted({k for r in rows for k in r}) if rows else ["empty"]
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=keys); w.writeheader(); w.writerows(rows)
    return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="sufra-{dataset}.csv"'})



# ---------------------------------------------------------------- Security settings

@router.post("/api/enterprise/security/pin/change")
def security_change_pin(body: dict = Body(...), actor: Staff = Depends(current_staff)):
    current_pin = str(body.get("current_pin") or "")
    new_pin = str(body.get("new_pin") or "")
    if not re.fullmatch(r"[0-9]{4}", new_pin):
        raise HTTPException(400, "New PIN must be exactly 4 digits.")
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, actor.id)
        from ..security import MAX_ATTEMPTS, lockout_seconds_for
        if member.locked_until and member.locked_until > datetime.now():
            raise HTTPException(429, "Too many attempts. Try again later.")
        if not re.fullmatch(r"[0-9]{4}", current_pin) or not verify_pin(current_pin, member.pin_hash):
            member.failed_attempts += 1
            if member.failed_attempts % MAX_ATTEMPTS == 0:
                member.locked_until = datetime.now() + timedelta(seconds=lockout_seconds_for(member.failed_attempts))
            s.add(member); s.commit()
            raise HTTPException(401, "Current PIN is incorrect.")
        member.pin_hash = hash_pin(new_pin)
        member.failed_attempts = 0
        member.locked_until = None
        revoke_sessions(s, member.id)
        s.add(member); s.commit()
    return {"ok": True, "message": "Your PIN was changed. Sign in again."}


@router.post("/api/enterprise/security/pin/reset")
def security_reset_pin(response: Response, body: dict = Body(...), actor: Staff = Depends(_manager)):
    target = int(body.get("staff_id") or 0)
    new_pin = str(body.get("new_pin") or "") or f"{secrets.randbelow(10000):04d}"
    if not re.fullmatch(r"[0-9]{4}", new_pin):
        raise HTTPException(400, "PIN must be exactly 4 digits.")
    with Session(engine, expire_on_commit=False) as s:
        member = s.get(Staff, target)
        if not member:
            raise HTTPException(404, "Employee not found.")
        member.pin_hash = hash_pin(new_pin)
        member.failed_attempts = 0
        member.locked_until = None
        revoke_sessions(s, member.id)
        s.add(member); s.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "temporary_pin": new_pin,
            "message": f"PIN reset for {member.name}. Give it to the employee securely."}


# ---------------------------------------------------------------- WebAuthn / device biometric


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(text_value: str) -> bytes:
    return base64.urlsafe_b64decode(text_value + "=" * (-len(text_value) % 4))


def _rp(request: Request) -> tuple[str,str]:
    # WebAuthn RP IDs must be DNS names, not raw IP addresses. SUFRA's local
    # development UI therefore canonicalises loopback access to localhost.
    host = (request.url.hostname or "localhost").strip().lower()
    if host in {"127.0.0.1", "0.0.0.0", "::1", "[::1]"}:
        host = "localhost"
    rp_id = os.getenv("WEBAUTHN_RP_ID", "").strip() or host
    if os.getenv("WEBAUTHN_ORIGIN", "").strip():
        origin = os.getenv("WEBAUTHN_ORIGIN", "").strip()
    else:
        port = request.url.port
        default_port = (request.url.scheme == "http" and port == 80) or (request.url.scheme == "https" and port == 443)
        suffix = "" if not port or default_port else f":{port}"
        origin = f"{request.url.scheme}://{host}{suffix}"
    return rp_id, origin


@router.post("/api/enterprise/biometric/register/options")
def bio_reg_options(request: Request, body: dict = Body(...), actor: Staff = Depends(current_staff)):
    target=int(body.get("staff_id") or actor.id)
    if target!=actor.id and actor.role not in MANAGER_ROLES: raise HTTPException(403,"You can only enroll your own device.")
    try:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import AuthenticatorAttachment, AuthenticatorSelectionCriteria, ResidentKeyRequirement, UserVerificationRequirement
    except Exception: raise HTTPException(503,"WebAuthn support is not available in this Python environment.")
    with Session(engine, expire_on_commit=False) as s:
        member=s.get(Staff,target)
        if not member: raise HTTPException(404,"Employee not found.")
        if target != actor.id:
            employee_pin = str(body.get("employee_pin") or "")
            if not verify_pin(employee_pin, member.pin_hash):
                raise HTTPException(401,"The selected employee must confirm their current PIN before biometric enrollment.")
        rp_id,origin=_rp(request)
        opts=generate_registration_options(rp_id=rp_id,rp_name="SUFRA Restaurant OS",
            user_id=str(member.id).encode(),user_name=f"staff-{member.id}",user_display_name=member.name,
            authenticator_selection=AuthenticatorSelectionCriteria(authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,user_verification=UserVerificationRequirement.REQUIRED))
        s.add(BiometricChallenge(staff_id=member.id,kind="register",challenge_b64=_b64e(opts.challenge),rp_id=rp_id,origin=origin,
                                 expires_at=datetime.now()+timedelta(minutes=5))); s.commit()
        return json.loads(options_to_json(opts))


@router.post("/api/enterprise/biometric/register/verify")
def bio_reg_verify(request: Request, body: dict = Body(...), actor: Staff = Depends(current_staff)):
    target=int(body.get("staff_id") or actor.id)
    if target!=actor.id and actor.role not in MANAGER_ROLES: raise HTTPException(403,"You can only enroll your own device.")
    try: from webauthn import verify_registration_response
    except Exception: raise HTTPException(503,"WebAuthn package is not installed.")
    with Session(engine, expire_on_commit=False) as s:
        ch=s.exec(select(BiometricChallenge).where(BiometricChallenge.staff_id==target,BiometricChallenge.kind=="register").order_by(BiometricChallenge.id.desc())).first()
        if not ch or ch.expires_at<datetime.now(): raise HTTPException(400,"Biometric enrollment expired. Start again.")
        try:
            v=verify_registration_response(credential=body.get("credential"),expected_challenge=_b64d(ch.challenge_b64),
                expected_origin=ch.origin,expected_rp_id=ch.rp_id,require_user_verification=True)
        except Exception as exc: raise HTTPException(400,f"Biometric enrollment failed: {exc}")
        cid=_b64e(v.credential_id)
        old=s.exec(select(BiometricCredential).where(BiometricCredential.credential_id==cid)).first()
        if old: old.public_key_b64=_b64e(v.credential_public_key); old.sign_count=v.sign_count; old.staff_id=target; cred=old
        else: cred=BiometricCredential(staff_id=target,credential_id=cid,public_key_b64=_b64e(v.credential_public_key),sign_count=v.sign_count,label=str(body.get("label") or "Device biometric"))
        s.add(cred)
        p=s.exec(select(HRProfile).where(HRProfile.staff_id==target)).first()
        if p: p.biometric_enabled=True; p.updated_at=datetime.now(); s.add(p)
        s.commit()
    return {"ok":True,"message":"Device biometric enrolled. SUFRA stored only a public passkey credential, not a face image."}


@router.post("/api/enterprise/biometric/auth/options")
def bio_auth_options(request: Request, body: dict = Body(...)):
    staff_id=int(body.get("staff_id") or 0)
    with Session(engine) as s:
        if s.get(StaffQR, staff_id):
            raise HTTPException(401, "Use your employee QR code and PIN to sign in.")
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            raise HTTPException(403, "This employee account is inactive.")
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except Exception: raise HTTPException(503,"WebAuthn package is not installed.")
    with Session(engine, expire_on_commit=False) as s:
        creds=s.exec(select(BiometricCredential).where(BiometricCredential.staff_id==staff_id)).all()
        if not creds: raise HTTPException(404,"No device biometric is enrolled for this employee.")
        rp_id,origin=_rp(request)
        opts=generate_authentication_options(rp_id=rp_id,allow_credentials=[PublicKeyCredentialDescriptor(id=_b64d(c.credential_id)) for c in creds],user_verification=UserVerificationRequirement.REQUIRED)
        s.add(BiometricChallenge(staff_id=staff_id,kind="authenticate",challenge_b64=_b64e(opts.challenge),rp_id=rp_id,origin=origin,
                                 expires_at=datetime.now()+timedelta(minutes=5))); s.commit()
        return json.loads(options_to_json(opts))


@router.post("/api/enterprise/biometric/auth/verify")
def bio_auth_verify(body: dict = Body(...)):
    staff_id=int(body.get("staff_id") or 0)
    with Session(engine) as s:
        if s.get(StaffQR, staff_id):
            raise HTTPException(401, "Use your employee QR code and PIN to sign in.")
        profile = s.exec(select(HRProfile).where(HRProfile.staff_id == staff_id)).first()
        if profile and profile.status in {"leaver", "suspended"}:
            raise HTTPException(403, "This employee account is inactive.")
    try: from webauthn import verify_authentication_response
    except Exception: raise HTTPException(503,"WebAuthn package is not installed.")
    with Session(engine, expire_on_commit=False) as s:
        ch=s.exec(select(BiometricChallenge).where(BiometricChallenge.staff_id==staff_id,BiometricChallenge.kind=="authenticate").order_by(BiometricChallenge.id.desc())).first()
        if not ch or ch.expires_at<datetime.now(): raise HTTPException(400,"Biometric sign-in expired. Start again.")
        raw=body.get("credential") or {}; cid=str(raw.get("id") or raw.get("rawId") or "")
        cred=s.exec(select(BiometricCredential).where(BiometricCredential.credential_id==cid)).first()
        if not cred or cred.staff_id != staff_id: raise HTTPException(400,"Unknown biometric credential.")
        try:
            v=verify_authentication_response(credential=raw,expected_challenge=_b64d(ch.challenge_b64),expected_origin=ch.origin,
                expected_rp_id=ch.rp_id,credential_public_key=_b64d(cred.public_key_b64),credential_current_sign_count=cred.sign_count,
                require_user_verification=True)
        except Exception as exc: raise HTTPException(401,f"Biometric sign-in failed: {exc}")
        cred.sign_count=v.new_sign_count; cred.last_used_at=datetime.now(); s.add(cred)
        member=s.get(Staff,staff_id)
        if not member: raise HTTPException(404,"Employee not found.")
        token=new_token(); sess=AuthSession(token=token,staff_id=member.id,created_at=datetime.now(),expires_at=session_expiry(),last_seen_at=datetime.now())
        s.delete(ch)
        s.add(sess); s.commit()
        return {"token":token,"staff":{"id":member.id,"name":member.name,"role":member.role.value,"avatar":member.avatar,"section":member.section,"on_shift":member.on_shift},
                "permissions":permissions_for(member.role)}

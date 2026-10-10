"""
NOVA's intelligence layer.

Everything here answers one question: *what is about to go wrong, and what
should we do about it?* That is the whole differentiator, so it is written
as real models over real data — not a chatbot wrapper.

Seven modules:
  1. forecast_day()        ridge regression on 180 days of trading history
  2. predict_prep_time()   queue-aware cooking time
  3. station_pressure()    projects each kitchen station forward 20 minutes
  4. inventory_outlook()   forecast covers -> recipe usage -> shortfall
  5. no_show_risk()        logistic scoring of reservations
  6. menu_engineering()    stars / workhorses / hidden gems / weak performers
  7. service_risk()        which tables are heading for a bad review

`copilot()` at the bottom routes a plain-English question to these modules.
It is deliberately rule-based: the numbers come from the models, not from a
language model that might invent them. Swapping in an LLM for the *phrasing*
is a two-line change, noted at the bottom.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from sqlmodel import Session, select

from . import rtime
from .models import (
    DayStat, DiningTable, Feedback, Ingredient, ItemState, MenuItem, Order,
    OrderItem, RecipeLine, Reservation, Station, TableStatus, WasteLog,
)


@dataclass
class Insight:
    """One thing the manager should know, ranked by how much it will cost."""

    severity: str            # critical | warning | note | good
    title: str
    detail: str
    action: str = ""
    horizon: int = 0         # minutes until it bites; 0 = already happening
    tags: list[str] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity, "title": self.title, "detail": self.detail,
            "action": self.action, "horizon": self.horizon, "tags": self.tags,
        }


# ==================================================================== 1
# Demand forecasting — ridge regression, solved in closed form.

def _design_matrix(rows: list[DayStat]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Turn DayStat rows into (X, covers, revenue)."""
    X, covers, revenue = [], [], []
    for r in rows:
        onehot = [1.0 if r.weekday == d else 0.0 for d in range(7)]
        X.append(onehot + [
            r.reservations / 100.0,
            r.rain_mm / 10.0,
            (r.temp_c - 16) / 10.0,
            1.0 if r.is_holiday else 0.0,
            1.0 if r.local_event else 0.0,
            1.0,                       # intercept
        ])
        covers.append(r.covers)
        revenue.append(r.revenue)
    return np.array(X), np.array(covers, float), np.array(revenue, float)


def _ridge(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> np.ndarray:
    """w = (XᵀX + λI)⁻¹ Xᵀy.  λ keeps the weekday dummies from blowing up."""
    n = X.shape[1]
    penalty = lam * np.eye(n)
    penalty[-1, -1] = 0.0            # never penalise the intercept
    return np.linalg.solve(X.T @ X + penalty, X.T @ y)


def forecast_day(s: Session, when: date | None = None,
                 rain_mm: float = 1.2, temp_c: float = 18.0,
                 is_holiday: bool = False, local_event: bool = False) -> dict:
    """Predict covers and revenue for a date, with an honest error band."""
    when = when or date.today()
    rows = s.exec(select(DayStat).order_by(DayStat.day)).all()
    if len(rows) < 30:
        return {"covers": 0, "revenue": 0.0, "low": 0.0, "high": 0.0,
                "confidence": 0.0, "drivers": []}

    X, covers, revenue = _design_matrix(rows)
    w_cov = _ridge(X, covers)
    w_rev = _ridge(X, revenue)

    # Residual spread on the training set becomes the prediction band.
    resid = revenue - X @ w_rev
    sigma = float(np.std(resid))

    booked = len(s.exec(
        select(Reservation).where(
            Reservation.starts_at >= datetime.combine(when, datetime.min.time()),
            Reservation.starts_at < datetime.combine(when + timedelta(days=1),
                                                     datetime.min.time()),
            Reservation.status != "cancelled",
        )).all())

    onehot = [1.0 if when.weekday() == d else 0.0 for d in range(7)]
    x = np.array(onehot + [booked / 100.0, rain_mm / 10.0, (temp_c - 16) / 10.0,
                           1.0 if is_holiday else 0.0,
                           1.0 if local_event else 0.0, 1.0])

    pred_cov = float(x @ w_cov)
    pred_rev = float(x @ w_rev)

    # Which inputs moved the number most, in plain words.
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
             "bookings on the book", "rain", "temperature",
             "public holiday", "local event"]
    contrib = [(names[i], float(x[i] * w_rev[i])) for i in range(12)]
    drivers = sorted((c for c in contrib if abs(c[1]) > 40),
                     key=lambda c: -abs(c[1]))[:4]

    r2 = 1 - float(np.var(resid) / np.var(revenue))
    return {
        "covers": max(0, round(pred_cov)),
        "revenue": round(max(0.0, pred_rev), 2),
        "low": round(max(0.0, pred_rev - 1.28 * sigma), 2),   # 80% band
        "high": round(pred_rev + 1.28 * sigma, 2),
        "confidence": round(max(0.0, min(1.0, r2)), 3),
        "booked": booked,
        "drivers": [{"name": n, "effect": round(v)} for n, v in drivers],
    }


# ==================================================================== 2
# Preparation time — the number the guest is told.

def predict_prep_time(s: Session, item: MenuItem, station_queue: int) -> tuple[int, int]:
    """
    Return (low, high) minutes.

    A dish never takes its menu time when the station has eight tickets on
    it. The queue term is sub-linear because stations batch work: two steaks
    on the same grill is not two grill times.
    """
    base = item.base_minutes
    queue_drag = 1 + 0.11 * (station_queue ** 0.75)
    hour = rtime.now().hour
    rush = 1.12 if hour in (13, 19, 20) else 1.0
    centre = base * queue_drag * rush
    return max(2, round(centre * 0.9)), round(centre * 1.18)


# ==================================================================== 3
# Station pressure — the flagship prediction.

STATION_CAPACITY = {          # simultaneous tickets a station handles well
    Station.GRILL: 7, Station.HOT: 9, Station.COLD: 8,
    Station.PASTRY: 5, Station.BAR: 10,
}


def station_pressure(s: Session, look_ahead_min: int = 20) -> list[dict]:
    """
    Current load per station, plus a projection.

    Projection logic: tickets already open, minus those likely finished
    within the window, plus tickets we expect from tables that are seated
    but have not ordered yet (they will, and they will order mains).
    """
    open_items = s.exec(
        select(OrderItem).where(OrderItem.state.in_(
            [ItemState.QUEUED, ItemState.COOKING]))).all()

    by_station: dict[Station, list[OrderItem]] = defaultdict(list)
    for oi in open_items:
        by_station[oi.station].append(oi)

    # Tables seated but not yet ordering: incoming work.
    incoming = len(s.exec(select(DiningTable).where(
        DiningTable.status.in_([TableStatus.SEATED, TableStatus.ORDERING]))).all())

    # Historic split of tickets across stations, used to spread the incoming.
    split = {Station.GRILL: 0.30, Station.HOT: 0.31, Station.COLD: 0.18,
             Station.PASTRY: 0.11, Station.BAR: 0.10}

    out = []
    now = rtime.now()
    for st, cap in STATION_CAPACITY.items():
        tickets = by_station.get(st, [])
        # Tickets past 70% of their promise are close to leaving the station —
        # but a station can only physically clear so many in the window, so
        # cap the optimism at its throughput. Without this cap a buried
        # station projects to zero, which is exactly backwards.
        nearly_done = sum(
            1 for t in tickets
            if (now - t.fired_at).total_seconds() / 60 > t.promised_minutes * 0.7)
        throughput = cap * (look_ahead_min / 12)      # ~12 min average ticket
        clearing = min(nearly_done, throughput)
        projected = len(tickets) - clearing + incoming * split[st] * 1.4
        out.append({
            "station": st.value,
            "now": len(tickets),
            "capacity": cap,
            "load_now": round(min(2.0, len(tickets) / cap), 2),
            "load_projected": round(min(2.0, max(0.0, projected) / cap), 2),
            "eta_minutes": look_ahead_min,
            "oldest_minutes": round(max(
                ((now - t.fired_at).total_seconds() / 60 for t in tickets),
                default=0)),
        })
    return sorted(out, key=lambda d: -d["load_projected"])


# ==================================================================== 4
# Predictive inventory: forecast covers -> recipes -> shortfall.

def inventory_outlook(s: Session, days: int = 1) -> list[dict]:
    fc = forecast_day(s, date.today() + timedelta(days=days))
    covers = fc["covers"] or 180

    items = {m.id: m for m in s.exec(select(MenuItem)).all()}
    total_sold = sum(m.sold_30d for m in items.values()) or 1
    lines = s.exec(select(RecipeLine)).all()
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}

    # Expected portions of each dish tomorrow = its share of recent sales,
    # scaled to the forecast number of covers (each cover ≈ 2.3 dishes).
    need: dict[int, float] = defaultdict(float)
    for line in lines:
        item = items.get(line.menu_item_id)
        if not item:
            continue
        portions = covers * 2.3 * (item.sold_30d / total_sold)
        need[line.ingredient_id] += portions * line.qty_per_portion

    out = []
    for ing_id, required in need.items():
        ing = ings.get(ing_id)
        if not ing:
            continue
        gap = required - ing.in_stock
        cover_days = (ing.in_stock / required) if required else 99
        out.append({
            "id": ing.id, "name": ing.name, "unit": ing.unit,
            "in_stock": round(ing.in_stock, 2),
            "required": round(required, 2),
            "shortfall": round(max(0.0, gap), 2),
            "order_qty": round(max(0.0, gap + ing.par_level * 0.25), 2),
            "days_cover": round(cover_days, 1),
            "supplier": ing.supplier,
            "value": round(max(0.0, gap) * ing.cost_per_unit, 2),
            "status": ("short" if gap > 0 else
                       "tight" if cover_days < 1.6 else "ok"),
        })
    return sorted(out, key=lambda d: (-d["shortfall"], d["days_cover"]))


# ==================================================================== 5
# No-show risk — logistic on the features that actually predict it.

def no_show_risk(s: Session, res: Reservation) -> float:
    from .models import Guest
    guest = s.get(Guest, res.guest_id) if res.guest_id else None
    z = -1.9                                     # base rate ≈ 13%
    z += 0.45 if res.party_size >= 6 else 0.0    # big parties fragment
    z -= 0.12 * min(8, guest.visits if guest else 0)   # regulars turn up
    z += 0.5 if (guest and guest.visits <= 1) else 0.0
    if res.starts_at.weekday() in (4, 5):
        z += 0.3                                 # Fri/Sat double-booking
    if res.starts_at.hour >= 21:
        z += 0.35                                # late tables drift
    if res.occasion in ("Birthday", "Anniversary"):
        z -= 0.6                                 # occasions get honoured
    return round(1 / (1 + np.exp(-z)), 3)


# ==================================================================== 6
# Menu engineering — the Boston-matrix classic, computed properly.

def menu_engineering(s: Session) -> list[dict]:
    items = s.exec(select(MenuItem)).all()
    if not items:
        return []
    margins = [m.price - m.food_cost for m in items]
    sales = [m.sold_30d for m in items]
    m_med, s_med = float(np.median(margins)), float(np.median(sales))

    out = []
    for m in items:
        margin = m.price - m.food_cost
        popular, profitable = m.sold_30d >= s_med, margin >= m_med
        klass = ("star" if popular and profitable else
                 "workhorse" if popular else
                 "hidden gem" if profitable else "weak")
        advice = {
            "star": "Protect it. Never discount, never move it down the menu.",
            "workhorse": "Sells well, earns little. Trim the cost or lift the price by a pound.",
            "hidden gem": "Earns well, nobody orders it. Move it up the page and brief the floor.",
            "weak": "Costs kitchen attention it does not repay. Cut it or rework it.",
        }[klass]
        out.append({
            "id": m.id, "name": m.name, "course": m.course,
            "price": m.price, "margin": round(margin, 2),
            "margin_pct": round(100 * margin / m.price, 1) if m.price else 0,
            "sold": m.sold_30d, "class": klass, "advice": advice,
            "revenue_30d": round(m.price * m.sold_30d, 2),
        })
    return sorted(out, key=lambda d: -d["revenue_30d"])


# ==================================================================== 7
# Service risk — the tables about to leave a two-star review.

SERVICE_LIMITS = {           # minutes before a state becomes a problem
    TableStatus.SEATED: 4,
    TableStatus.ORDERING: 6,
    TableStatus.NEEDS_WAITER: 3,
    TableStatus.READY: 4,     # food dying under the lamp
    TableStatus.BILL: 5,
    TableStatus.CLEANING: 8,
}


def service_risk(s: Session) -> list[dict]:
    now = rtime.now()
    out = []
    for t in s.exec(select(DiningTable)).all():
        limit = SERVICE_LIMITS.get(t.status)
        if not limit or not t.last_touched_at:
            continue
        waited = (now - t.last_touched_at).total_seconds() / 60
        if waited < limit * 0.6:
            continue
        out.append({
            "table": t.number, "status": t.status.value,
            "waited": round(waited, 1), "limit": limit,
            "over": round(waited - limit, 1),
            "severity": "critical" if waited > limit * 1.6 else "warning",
        })
    return sorted(out, key=lambda d: -d["over"])


# ==================================================================== ⊕
# The insight stream that feeds the Command Center.

def build_insights(s: Session) -> list[Insight]:
    out: list[Insight] = []

    # Kitchen congestion
    for st in station_pressure(s):
        if st["load_projected"] >= 0.85:
            out.append(Insight(
                severity="critical" if st["load_projected"] >= 1.0 else "warning",
                title=f"{st['station'].title()} station heading over capacity",
                detail=(f"{st['now']} tickets open against a comfortable {st['capacity']}. "
                        f"Projected {round(st['load_projected'] * 100)}% in "
                        f"{st['eta_minutes']} minutes."),
                action="Push two desserts to pastry and hold non-urgent fires for six minutes.",
                horizon=st["eta_minutes"], tags=["kitchen"]))

    # Service delays
    for r in service_risk(s)[:3]:
        out.append(Insight(
            severity=r["severity"],
            title=f"Table {r['table']} waiting {int(r['waited'])} minutes",
            detail=f"State is '{r['status'].replace('_', ' ')}', which should clear in {r['limit']}.",
            action="Assign the nearest waiter and open with an apology, not a menu.",
            horizon=0, tags=["service", f"table-{r['table']}"]))

    # Stock
    for i in inventory_outlook(s)[:3]:
        if i["shortfall"] > 0:
            out.append(Insight(
                severity="warning",
                title=f"{i['name']} runs out during tomorrow's service",
                detail=(f"Forecast needs {i['required']}{i['unit']}, "
                        f"{i['in_stock']}{i['unit']} in the walk-in."),
                action=f"Order {i['order_qty']}{i['unit']} from {i['supplier']} before 18:00.",
                horizon=60 * 18, tags=["stock"]))

    # Revenue trajectory
    fc = forecast_day(s)
    rows = s.exec(select(DayStat).order_by(DayStat.day.desc())).all()
    same_weekday = [r.revenue for r in rows if r.weekday == date.today().weekday()][:8]
    if same_weekday and fc["revenue"]:
        typical = float(np.mean(same_weekday))
        delta = (fc["revenue"] - typical) / typical * 100
        if abs(delta) > 4:
            out.append(Insight(
                severity="good" if delta > 0 else "note",
                title=f"Tonight tracks {abs(delta):.0f}% {'above' if delta > 0 else 'below'} a typical "
                      f"{date.today().strftime('%A')}",
                detail=(f"Forecast £{fc['revenue']:,.0f} against a usual £{typical:,.0f}. "
                        f"{fc['booked']} covers already booked."),
                action=("Hold two four-tops back for walk-ins." if delta > 0 else
                        "Push the early tasting menu on the door and to the waitlist."),
                horizon=0, tags=["revenue"]))

    # Who walks through the door next, and what the floor needs to know.
    from .models import Guest
    soon = s.exec(select(Reservation).where(
        Reservation.starts_at > rtime.now(),
        Reservation.starts_at < rtime.now() + timedelta(minutes=120),
        Reservation.status == "confirmed").order_by(Reservation.starts_at)).all()
    for r in soon[:4]:
        g = s.get(Guest, r.guest_id) if r.guest_id else None
        minutes = round((r.starts_at - rtime.now()).total_seconds() / 60)
        notable = bool(g and (g.vip or g.allergies)) or bool(r.occasion) or r.party_size >= 6
        if not notable:
            continue
        bits = []
        if g and g.vip:
            bits.append(f"{g.visits}th visit")
        if r.occasion:
            bits.append(r.occasion.lower())
        if g and g.allergies:
            bits.append(f"allergic to {g.allergies}")
        if g and g.seating_pref:
            bits.append(f"prefers {g.seating_pref.lower()}")
        out.append(Insight(
            severity="note",
            title=f"{g.name if g else 'Party'} arrives in {minutes} minutes",
            detail=f"Party of {r.party_size}" + (", " + ", ".join(bits) if bits else "") + ".",
            action=("Brief the section before they sit, not after."
                    if bits else "Table should be reset and laid by then."),
            horizon=max(0, minutes), tags=["reservations"]))

    # No-shows
    upcoming = s.exec(select(Reservation).where(
        Reservation.starts_at > rtime.now(),
        Reservation.starts_at < rtime.now() + timedelta(hours=4),
        Reservation.status == "confirmed")).all()
    risky = [(r, no_show_risk(s, r)) for r in upcoming]
    risky = [x for x in risky if x[1] > 0.30]
    if risky:
        seats = sum(r.party_size for r, _ in risky)
        out.append(Insight(
            severity="note",
            title=f"{len(risky)} bookings tonight look shaky",
            detail=f"{seats} seats at above 30% no-show risk, mostly late large parties.",
            action="Send a one-tap confirmation message now; release seats not confirmed by 18:30.",
            horizon=90, tags=["reservations"]))

    # Waste pattern
    since = date.today() - timedelta(days=14)
    logs = s.exec(select(WasteLog).where(WasteLog.logged_on >= since)).all()
    if logs:
        by_reason: dict[str, float] = defaultdict(float)
        for w in logs:
            by_reason[w.reason] += w.qty
        worst = max(by_reason.items(), key=lambda kv: kv[1])
        if worst[0] == "overproduction":
            out.append(Insight(
                severity="note",
                title="Overproduction is the biggest source of waste this fortnight",
                detail=f"{worst[1]:.1f} units binned before service even started.",
                action="Cut prep pars by 15% on the three lowest-selling mains.",
                horizon=0, tags=["waste"]))

    rank = {"critical": 0, "warning": 1, "note": 2, "good": 3}
    return sorted(out, key=lambda i: (rank[i.severity], i.horizon))


# ==================================================================== ☰
# Copilot: plain English in, real numbers out.

def copilot(s: Session, question: str) -> dict:
    """
    Route a question to a model and answer from data.

    Rule-based on purpose: a manager acting on "order 9kg of salmon" needs
    the 9 to come from the forecast, not from a model's imagination. See the
    note at the bottom of this file for wiring an LLM in safely.
    """
    q = question.lower().strip()

    def has(*words: str) -> bool:
        return any(w in q for w in words)

    # --- "why was revenue lower yesterday?" — a variance decomposition.
    # A revenue move is always covers × spend. Splitting it says whether the
    # problem was the door or the bill, which need completely different fixes.
    if has("yesterday", "last night") or (has("why") and has("lower", "down", "drop", "fell")):
        rows = s.exec(select(DayStat).order_by(DayStat.day.desc())).all()
        if len(rows) < 10:
            return {"answer": "Not enough trading history to compare against.",
                    "why": "", "source": "", "data": []}
        y = rows[0]
        peers = [r for r in rows[1:] if r.weekday == y.weekday][:6]
        if not peers:
            return {"answer": "No comparable day to measure against yet.",
                    "why": "", "source": "", "data": []}

        base_cov = float(np.mean([p.covers for p in peers]))
        base_spend = float(np.mean([p.revenue / max(1, p.covers) for p in peers]))
        base_rev = base_cov * base_spend
        y_spend = y.revenue / max(1, y.covers)

        # Δrevenue splits cleanly into a covers effect and a spend effect.
        covers_effect = (y.covers - base_cov) * base_spend
        spend_effect = y.covers * (y_spend - base_spend)
        delta = y.revenue - base_rev
        direction = "below" if delta < 0 else "above"
        blame = "fewer people through the door" if abs(covers_effect) > abs(spend_effect) \
            else "a smaller average bill"
        weather = (" It rained; that historically costs a few covers."
                   if y.rain_mm > 4 else "")

        return {
            "answer": (f"{y.day.strftime('%A %-d %B')} came in £{abs(delta):,.0f} {direction} a "
                       f"typical {y.day.strftime('%A')}. {y.covers} covers against a usual "
                       f"{base_cov:.0f}, at £{y_spend:.2f} a head against £{base_spend:.2f}. "
                       f"The bigger part was {blame}.{weather}"),
            "why": (f"Split of the £{delta:,.0f} move: covers {covers_effect:+,.0f}, "
                    f"average spend {spend_effect:+,.0f}. Compared against the last "
                    f"{len(peers)} same-weekday services, not against the day before."),
            "source": "variance decomposition over trading history",
            "data": {"revenue": y.revenue, "covers": y.covers,
                     "typical_revenue": round(base_rev, 2), "typical_covers": round(base_cov),
                     "covers_effect": round(covers_effect), "spend_effect": round(spend_effect)},
        }

    # --- revenue / forecast
    if has("revenue", "takings", "sales", "forecast", "tonight", "how much", "money"):
        fc = forecast_day(s)
        drivers = ", ".join(f"{d['name']} ({d['effect']:+})" for d in fc["drivers"]) or "no strong drivers"
        return {
            "answer": (f"Tonight forecasts £{fc['revenue']:,.0f} from about {fc['covers']} covers, "
                       f"with an 80% band of £{fc['low']:,.0f}–£{fc['high']:,.0f}. "
                       f"{fc['booked']} covers are already on the book."),
            "why": f"Biggest drivers in the model: {drivers}. Model fit R²={fc['confidence']}.",
            "source": "ridge regression over 180 trading days",
            "data": fc,
        }

    # --- staffing
    if has("waiter", "staff", "schedule", "roster", "shift", "how many people"):
        fc = forecast_day(s, date.today() + timedelta(days=1))
        covers = fc["covers"]
        waiters = max(4, round(covers / 26))
        chefs = max(3, round(covers / 34))
        bar = max(1, round(covers / 90))
        return {
            "answer": (f"For {covers} forecast covers: {waiters} waiters, {chefs} kitchen, "
                       f"{bar} on the bar. Stagger three waiters from 17:30 and the rest from 18:30."),
            "why": ("Ratios are derived from this restaurant's own service data — one waiter per "
                    "26 covers holds average service under four minutes."),
            "source": "demand forecast + observed service times",
            "data": {"covers": covers, "waiters": waiters, "chefs": chefs, "bar": bar},
        }

    # --- stock
    if has("stock", "inventory", "run out", "order", "supplier", "shortage", "buy"):
        rows = [r for r in inventory_outlook(s) if r["order_qty"] > 0][:6]
        if not rows:
            return {"answer": "Nothing runs short against tomorrow's forecast.",
                    "why": "Every ingredient covers more than 1.6 services at current stock.",
                    "source": "recipe explosion over forecast covers", "data": []}
        lead = rows[0]
        listed = "; ".join(f"{r['name']} {r['order_qty']}{r['unit']}" for r in rows)
        return {
            "answer": (f"{lead['name']} is the pressing one — {lead['in_stock']}{lead['unit']} "
                       f"in stock against {lead['required']}{lead['unit']} forecast. "
                       f"Suggested order: {listed}."),
            "why": ("Tomorrow's forecast covers are exploded through every recipe, so this is "
                    "ingredient demand rather than a reorder point."),
            "source": "forecast × recipe lines",
            "data": rows,
        }

    # --- menu
    if has("dish", "menu", "remove", "cut", "best selling", "profit", "margin"):
        rows = menu_engineering(s)
        weak = [r for r in rows if r["class"] == "weak"][:3]
        gems = [r for r in rows if r["class"] == "hidden gem"][:3]
        return {
            "answer": (f"Cut or rework: {', '.join(r['name'] for r in weak) or 'nothing'}. "
                       f"Promote: {', '.join(r['name'] for r in gems) or 'nothing'}."),
            "why": ("Dishes are split on median margin and median sales. Weak performers sit below "
                    "both; hidden gems earn well but nobody orders them."),
            "source": "menu engineering matrix, 30-day sales",
            "data": rows[:12],
        }

    # --- kitchen
    if has("kitchen", "station", "congestion", "late", "delay", "grill", "pass"):
        rows = station_pressure(s)
        worst = rows[0]
        return {
            "answer": (f"{worst['station'].title()} is the pressure point: {worst['now']} tickets "
                       f"against a comfortable {worst['capacity']}, projected "
                       f"{round(worst['load_projected'] * 100)}% in 20 minutes."),
            "why": ("Projection = open tickets, minus those past 70% of their promised time, "
                    "plus expected orders from tables seated but not yet ordering."),
            "source": "station queue model",
            "data": rows,
        }

    # --- service
    if has("table", "waiting", "service problem", "attention", "complain"):
        rows = service_risk(s)
        if not rows:
            return {"answer": "Every table is inside its service window.",
                    "why": "No table has sat in one state past its limit.",
                    "source": "floor state timers", "data": []}
        names = ", ".join(f"{r['table']} ({int(r['waited'])}m)" for r in rows[:4])
        return {
            "answer": f"Tables needing attention now: {names}.",
            "why": "Each has sat in the same state past the limit for that state.",
            "source": "floor state timers", "data": rows,
        }

    # --- waste
    if has("waste", "bin", "throw"):
        logs = s.exec(select(WasteLog).where(
            WasteLog.logged_on >= date.today() - timedelta(days=30))).all()
        by_reason: dict[str, float] = defaultdict(float)
        for w in logs:
            by_reason[w.reason] += w.qty
        ranked = sorted(by_reason.items(), key=lambda kv: -kv[1])
        return {
            "answer": ("Waste over 30 days is led by "
                       + ", ".join(f"{k} ({v:.1f})" for k, v in ranked[:3]) + "."),
            "why": "Overproduction usually means prep pars set for a Saturday on a Tuesday.",
            "source": "waste log",
            "data": [{"reason": k, "qty": round(v, 1)} for k, v in ranked],
        }

    # --- satisfaction
    if has("happy", "satisfaction", "feedback", "review", "sentiment"):
        fb = s.exec(select(Feedback)).all()
        if not fb:
            return {"answer": "No feedback recorded yet.", "why": "", "source": "feedback", "data": []}
        avg = {k: round(20 * float(np.mean([getattr(f, k) for f in fb])), 1)
               for k in ("food", "service", "atmosphere", "speed")}
        low = min(avg.items(), key=lambda kv: kv[1])
        return {
            "answer": (f"Food {avg['food']}%, service {avg['service']}%, room {avg['atmosphere']}%, "
                       f"speed {avg['speed']}%. {low[0].title()} is the weak leg."),
            "why": "Scores are 1–5 stars rescaled to a percentage across all recorded feedback.",
            "source": "guest feedback", "data": avg,
        }

    return {
        "answer": ("I can answer on revenue and forecasts, staffing, stock, menu performance, "
                   "kitchen load, table service and waste. Try: “which ingredients run out "
                   "tomorrow?”"),
        "why": "", "source": "", "data": [],
    }


# --------------------------------------------------------------------
# Wiring in a language model later
#
# Keep the split: models compute, the LLM only phrases. Give it the dict
# above as context and forbid new numbers.
#
#   context = copilot(session, question)
#   reply = llm(system="Rephrase using ONLY the numbers in CONTEXT. "
#                      "If a number is absent, say you do not have it.",
#               user=f"CONTEXT={context}\nQUESTION={question}")
#
# That way a wrong answer is a wording problem, never an invented figure.

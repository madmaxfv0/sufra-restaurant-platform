"""SUFRA ANBAR — intelligence.

Every number here is derived from rows in this restaurant's own database.
Where the history is too thin to support a claim, the function says so
(`confidence: "low"`, or a "not enough history" reason) rather than
inventing precision. That honesty is the feature: a manager who has been
told once that a confident-looking forecast was guesswork stops trusting
the whole screen.

Each recommendation carries a `why` list — the actual inputs that produced
it — so the UI can open an explanation instead of asking anyone to take
the number on faith.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from . import anbar, intelligence as ai
from .anbar_models import (GoodsReceipt, GoodsReceiptLine, InvBatch, InvCategory,
                           InvItem, InvTxn, SupplierItem)
from .models import (Ingredient, MenuItem, Order, OrderItem, PriceHistory,
                     PurchaseLine, PurchaseOrder, RecipeLine, Reservation,
                     Supplier, WasteLog)

# Enough history to speak with confidence. Below the low bar Anbar will
# still give a rules-based recommendation, but labels it as such.
CONF_HIGH_DAYS = 21
CONF_MED_DAYS = 7


def _confidence(days_of_history: int, sample: int) -> str:
    if days_of_history >= CONF_HIGH_DAYS and sample >= 20:
        return "high"
    if days_of_history >= CONF_MED_DAYS and sample >= 5:
        return "medium"
    return "low"


def _history_days(s: Session) -> int:
    """How many distinct days of settled trade this restaurant actually has."""
    rows = s.exec(select(Order).where(Order.paid == True)).all()  # noqa: E712
    return len({o.opened_at.date() for o in rows})


def _ledger_days(s: Session) -> int:
    rows = s.exec(select(InvTxn).where(
        InvTxn.txn_type == "SALE_CONSUMPTION")).all()
    return len({r.at.date() for r in rows})


# ---------------------------------------------------------------- demand


def expected_covers(s: Session, days_ahead: int = 1) -> dict:
    """Covers expected on a future service.

    Reservations already on the book are hard data. The forecast model in
    intelligence.py supplies the walk-in half. When the book is materially
    bigger than the model expects, the book wins — a party of 40 booked for
    tomorrow is not a statistical anomaly to be smoothed away.
    """
    target = date.today() + timedelta(days=days_ahead)
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    booked_rows = s.exec(select(Reservation).where(
        Reservation.starts_at >= start, Reservation.starts_at < end)).all()
    booked = sum(r.party_size for r in booked_rows
                 if (r.status or "") not in ("cancelled", "no_show"))
    try:
        model = ai.forecast_day(s, target)
        modelled = int(model.get("covers") or 0)
    except Exception:
        modelled = 0
    covers = max(modelled, int(booked * 1.35)) if booked else modelled
    return {
        "day": target.isoformat(), "covers": covers,
        "booked_covers": booked, "modelled_covers": modelled,
        "reservations": len(booked_rows),
    }


def _menu_mix(s: Session, days: int = 30) -> dict[int, float]:
    """Share of portions each dish takes, measured from settled bills.

    Falls back to MenuItem.sold_30d when there is not enough real trade yet,
    which is the seeded popularity figure rather than observed sales — the
    caller lowers its confidence accordingly.
    """
    cutoff = datetime.now() - timedelta(days=days)
    orders = s.exec(select(Order).where(
        Order.paid == True, Order.opened_at >= cutoff)).all()  # noqa: E712
    ids = [o.id for o in orders]
    counts: dict[int, float] = defaultdict(float)
    if ids:
        lines = s.exec(select(OrderItem).where(OrderItem.order_id.in_(ids))).all()
        for line in lines:
            if not line.void_reason:
                counts[line.menu_item_id] += line.qty
    if not counts:
        for m in s.exec(select(MenuItem)).all():
            if m.sold_30d:
                counts[m.id] = float(m.sold_30d)
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def ingredient_demand(s: Session, days_ahead: int = 1) -> dict:
    """Expected consumption of every recipe ingredient on a future day.

    covers -> dishes (via observed dishes-per-cover) -> portions per dish
    (via observed menu mix) -> ingredients (via recipes).
    """
    cover_info = expected_covers(s, days_ahead)
    covers = cover_info["covers"]
    mix = _menu_mix(s)
    hist_days = _history_days(s)

    # Dishes per cover, observed rather than assumed.
    orders = s.exec(select(Order).where(Order.paid == True)).all()  # noqa: E712
    ids = [o.id for o in orders]
    lines = s.exec(select(OrderItem).where(
        OrderItem.order_id.in_(ids))).all() if ids else []
    sold = sum(l.qty for l in lines if not l.void_reason)
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    covers_seen = sum(l.qty for l in lines if not l.void_reason
                      and menu.get(l.menu_item_id)
                      and menu[l.menu_item_id].course == "Main") or 0
    per_cover = (sold / covers_seen) if covers_seen >= 10 else 2.3

    items = anbar.items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    need: dict[int, float] = defaultdict(float)
    for r in s.exec(select(RecipeLine)).all():
        share = mix.get(r.menu_item_id, 0.0)
        if share <= 0:
            continue
        portions = covers * per_cover * share
        item = items.get(r.ingredient_id)
        need[r.ingredient_id] += r.qty_per_portion * portions

    rows = []
    for ing_id, qty in need.items():
        ing = ings.get(ing_id)
        if not ing:
            continue
        item = items.get(ing_id)
        rows.append({
            "ingredient_id": ing_id, "name": ing.name,
            "unit": item.base_unit if item else ing.unit,
            "required": round(qty, 3),
            "in_stock": round(float(ing.in_stock or 0.0), 3),
            "gap": round(max(0.0, qty - float(ing.in_stock or 0.0)), 3),
        })
    rows.sort(key=lambda r: -r["gap"])
    return {
        "day": cover_info["day"], "covers": covers,
        "booked_covers": cover_info["booked_covers"],
        "reservations": cover_info["reservations"],
        "dishes_per_cover": round(per_cover, 2),
        "rows": rows,
        "confidence": _confidence(hist_days, len(lines)),
        "history_days": hist_days,
        "basis": ("settled bills over the last 30 days"
                  if covers_seen >= 10 else "seeded menu popularity (no trading history yet)"),
    }


# ---------------------------------------------------------------- reordering


def reorder_plan(s: Session, horizon_days: int = 3) -> dict:
    """What to buy, how much, and the reasoning behind each number.

    Suggested quantity covers demand over the supplier's lead time plus the
    horizon, tops the item back up to its target, respects minimum order
    quantity, and subtracts stock already on its way in.
    """
    demand = ingredient_demand(s, 1)
    per_day = {r["ingredient_id"]: r["required"] for r in demand["rows"]}
    items = anbar.items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    suppliers = {x.id: x for x in s.exec(select(Supplier)).all()}
    supplier_items = defaultdict(list)
    for si in s.exec(select(SupplierItem).where(SupplierItem.active == True)).all():  # noqa: E712
        supplier_items[si.ingredient_id].append(si)

    # Stock already ordered but not yet received does not need ordering again.
    incoming: dict[int, float] = defaultdict(float)
    open_pos = s.exec(select(PurchaseOrder).where(
        PurchaseOrder.status.in_(["draft", "pending", "approved", "sent", "partial"]))).all()
    if open_pos:
        for pl in s.exec(select(PurchaseLine).where(
                PurchaseLine.order_id.in_([p.id for p in open_pos]))).all():
            qty_base = float(getattr(pl, "qty_base", 0.0) or 0.0) or pl.qty
            incoming[pl.ingredient_id] += max(
                0.0, qty_base - float(getattr(pl, "received_qty", 0.0) or 0.0))

    rows = []
    for ing in s.exec(select(Ingredient)).all():
        item = items.get(ing.id)
        if item and not item.active:
            continue
        stock = float(ing.in_stock or 0.0)
        on_order = incoming.get(ing.id, 0.0)
        daily = per_day.get(ing.id, 0.0)
        if not daily:
            # No recipe demand: fall back to observed ledger usage.
            used = anbar.usage(s, ing.id, 14)
            daily = used / 14 if used else 0.0
        lead = item and item.secondary_supplier_id
        sup = suppliers.get(ing.supplier_id)
        lead_days = sup.lead_time_days if sup else 1
        offers = sorted(supplier_items.get(ing.id, []),
                        key=lambda x: (not x.preferred, x.price_per_pack))
        if offers and offers[0].lead_time_days:
            lead_days = offers[0].lead_time_days

        cover_days = lead_days + horizon_days
        needed = daily * cover_days
        safety = (item.min_stock if item else 0.0) or daily * 1.0
        target = (item.target_stock if item and item.target_stock else 0.0) or (needed + safety)
        shortfall = max(0.0, needed + safety - stock - on_order)
        if shortfall <= 0:
            continue
        suggested = max(shortfall, target - stock - on_order)

        moq = offers[0].min_order_qty if offers else 0.0
        if moq and suggested < moq:
            suggested = moq
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0.0
        unit = item.base_unit if item else ing.unit

        rows.append({
            "ingredient_id": ing.id, "name": ing.name, "unit": unit,
            "in_stock": round(stock, 3), "on_order": round(on_order, 3),
            "daily_demand": round(daily, 3),
            "suggested": round(suggested, 2),
            "value": round(suggested * cost, 2),
            "supplier": sup.name if sup else (ing.supplier or "—"),
            "supplier_id": ing.supplier_id,
            "lead_time_days": lead_days,
            "status": anbar.status_for(ing, item),
            "why": [
                f"{round(daily * cover_days, 2)} {unit} expected demand over "
                f"{cover_days} days ({lead_days}d supplier lead time + {horizon_days}d cover)",
                f"{round(stock, 2)} {unit} on hand"
                + (f", {round(on_order, 2)} {unit} already on order" if on_order else ""),
                f"safety stock {round(safety, 2)} {unit}",
            ] + ([f"supplier minimum order {moq} {unit}"] if moq else []),
        })
    rows.sort(key=lambda r: -r["value"])
    return {
        "rows": rows,
        "total_value": round(sum(r["value"] for r in rows), 2),
        "confidence": demand["confidence"],
        "basis": demand["basis"],
        "horizon_days": horizon_days,
    }


# ---------------------------------------------------------------- expiry


def expiry_risk(s: Session) -> dict:
    """Batches approaching their date, and whether demand will actually use them."""
    today = date.today()
    items = anbar.items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    demand = {r["ingredient_id"]: r["required"]
              for r in ingredient_demand(s, 1)["rows"]}

    buckets = {"today": [], "1d": [], "3d": [], "7d": []}
    value_at_risk = 0.0
    rows = []
    batches = s.exec(select(InvBatch).where(
        InvBatch.status == "active", InvBatch.qty_base > 0,
        InvBatch.expires_on != None)).all()  # noqa: E711
    for b in batches:
        days = (b.expires_on - today).days
        if days > 7:
            continue
        ing = ings.get(b.ingredient_id)
        if not ing:
            continue
        item = items.get(b.ingredient_id)
        value = b.qty_base * (b.unit_cost or (item.avg_cost if item else ing.cost_per_unit) or 0)
        daily = demand.get(b.ingredient_id, 0.0)
        will_use = daily * max(0, days)
        at_risk = max(0.0, b.qty_base - will_use)
        row = {
            "batch_id": b.id, "ingredient_id": b.ingredient_id, "name": ing.name,
            "batch_code": b.batch_code, "qty": round(b.qty_base, 3),
            "unit": item.base_unit if item else ing.unit,
            "expires_on": b.expires_on.isoformat(), "days": days,
            "value": round(value, 2),
            "expected_use": round(will_use, 3),
            "at_risk_qty": round(at_risk, 3),
            "at_risk_value": round(at_risk * (b.unit_cost or 0), 2),
        }
        rows.append(row)
        value_at_risk += row["at_risk_value"]
        key = "today" if days <= 0 else ("1d" if days <= 1 else ("3d" if days <= 3 else "7d"))
        buckets[key].append(row)

    # Items with a single expiry date on the ingredient itself (no batch tracking).
    for ing in ings.values():
        if not ing.expires_on or float(ing.in_stock or 0) <= 0:
            continue
        days = (ing.expires_on - today).days
        if days > 7 or any(r["ingredient_id"] == ing.id for r in rows):
            continue
        item = items.get(ing.id)
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0.0
        daily = demand.get(ing.id, 0.0)
        at_risk = max(0.0, float(ing.in_stock) - daily * max(0, days))
        row = {
            "batch_id": None, "ingredient_id": ing.id, "name": ing.name,
            "batch_code": "", "qty": round(float(ing.in_stock), 3),
            "unit": item.base_unit if item else ing.unit,
            "expires_on": ing.expires_on.isoformat(), "days": days,
            "value": round(float(ing.in_stock) * cost, 2),
            "expected_use": round(daily * max(0, days), 3),
            "at_risk_qty": round(at_risk, 3),
            "at_risk_value": round(at_risk * cost, 2),
        }
        rows.append(row)
        value_at_risk += row["at_risk_value"]
        key = "today" if days <= 0 else ("1d" if days <= 1 else ("3d" if days <= 3 else "7d"))
        buckets[key].append(row)

    rows.sort(key=lambda r: (r["days"], -r["at_risk_value"]))
    return {
        "rows": rows, "value_at_risk": round(value_at_risk, 2),
        "counts": {k: len(v) for k, v in buckets.items()},
    }


# ---------------------------------------------------------------- anomalies


def anomalies(s: Session) -> list[dict]:
    """Unusual stock behaviour, stated as observations rather than accusations.

    Anbar never says an employee took anything. It says the numbers do not
    reconcile and shows the arithmetic — the investigation is a human's job,
    and an algorithm that names a culprit from a variance is both unfair and
    frequently wrong.
    """
    out: list[dict] = []
    today = date.today()
    items = anbar.items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}

    # 1. Consumption well above its own recent baseline.
    for ing in ings.values():
        recent = anbar.usage(s, ing.id, 7)
        prior = anbar.usage(s, ing.id, 28) - recent
        if prior <= 0 or recent <= 0:
            continue
        weekly_prior = prior / 3.0
        if weekly_prior < 0.001:
            continue
        delta = (recent - weekly_prior) / weekly_prior
        if delta >= 0.25 and recent > 0:
            item = items.get(ing.id)
            unit = item.base_unit if item else ing.unit
            out.append({
                "kind": "consumption", "severity": "high" if delta >= 0.5 else "attention",
                "ingredient_id": ing.id,
                "title": f"{ing.name} usage {round(delta * 100)}% above its 4-week average",
                "body": f"{round(recent, 2)} {unit} used in the last 7 days against a "
                        f"{round(weekly_prior, 2)} {unit} weekly average.",
                "why": [f"last 7 days: {round(recent, 2)} {unit}",
                        f"prior 3 weeks averaged {round(weekly_prior, 2)} {unit}/week"],
            })

    # 2. Stock leaving without a sale behind it — the beverage case especially.
    cutoff = datetime.now() - timedelta(days=7)
    by_item: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in s.exec(select(InvTxn).where(InvTxn.at >= cutoff)).all():
        by_item[t.ingredient_id][t.txn_type] += t.qty_base
    for ing_id, totals in by_item.items():
        ing = ings.get(ing_id)
        if not ing:
            continue
        adjustments = abs(totals.get("MANUAL_ADJUSTMENT", 0.0))
        sales = abs(totals.get("SALE_CONSUMPTION", 0.0))
        if adjustments > 0 and adjustments > max(0.15 * sales, 0.001) and adjustments > 0.05:
            item = items.get(ing_id)
            unit = item.base_unit if item else ing.unit
            cost = (item.avg_cost if item else ing.cost_per_unit) or 0
            out.append({
                "kind": "variance", "severity": "attention",
                "ingredient_id": ing_id,
                "title": f"{ing.name}: repeated manual adjustment this week",
                "body": f"{round(adjustments, 2)} {unit} (₼{round(adjustments * cost, 2)}) "
                        f"was adjusted by hand against {round(sales, 2)} {unit} sold. "
                        f"Worth reviewing why the book and the shelf disagree.",
                "why": [f"manual adjustments: {round(adjustments, 3)} {unit}",
                        f"sales consumption: {round(sales, 3)} {unit}"],
            })

    # 3. Supplier price moving faster than the recent norm.
    for row in price_moves(s):
        if row["change_pct"] >= 10:
            out.append({
                "kind": "price",
                "severity": "high" if row["change_pct"] >= 20 else "attention",
                "ingredient_id": row["ingredient_id"],
                "title": f"{row['name']} purchase price up {row['change_pct']}%",
                "body": f"₼{row['previous']} to ₼{row['current']} per "
                        f"{row['unit']}{(' from ' + row['supplier']) if row['supplier'] else ''}.",
                "why": [f"previous price ₼{row['previous']}",
                        f"latest price ₼{row['current']}",
                        f"{row['points']} price points on record"],
            })

    # 4. Negative or impossible balances.
    for ing in ings.values():
        if float(ing.in_stock or 0) < 0:
            out.append({
                "kind": "variance", "severity": "critical", "ingredient_id": ing.id,
                "title": f"{ing.name} shows a negative balance",
                "body": "More stock has been consumed than was ever received. "
                        "A delivery is probably unrecorded, or a recipe quantity is wrong.",
                "why": [f"on hand: {round(float(ing.in_stock), 3)}"],
            })

    order = {"critical": 0, "high": 1, "attention": 2, "info": 3}
    out.sort(key=lambda r: order.get(r["severity"], 9))
    return out


# ---------------------------------------------------------------- price & supplier


def price_moves(s: Session) -> list[dict]:
    """Price change per ingredient, from PriceHistory plus received invoices."""
    items = anbar.items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    sups = {x.id: x for x in s.exec(select(Supplier)).all()}
    series: dict[int, list[tuple[date, float, Optional[int]]]] = defaultdict(list)
    for p in s.exec(select(PriceHistory).order_by(PriceHistory.on_day)).all():
        series[p.ingredient_id].append((p.on_day, p.price, p.supplier_id))
    for line in s.exec(select(GoodsReceiptLine)).all():
        receipt = s.get(GoodsReceipt, line.receipt_id)
        if receipt and receipt.status == "confirmed" and line.unit_price:
            series[line.ingredient_id].append(
                (receipt.delivered_on, line.unit_price, receipt.supplier_id))

    out = []
    for ing_id, points in series.items():
        if len(points) < 2:
            continue
        points.sort(key=lambda p: p[0])
        current, previous = points[-1][1], points[-2][1]
        if not previous:
            continue
        ing = ings.get(ing_id)
        if not ing:
            continue
        item = items.get(ing_id)
        sup = sups.get(points[-1][2]) if points[-1][2] else None
        cutoff30 = date.today() - timedelta(days=30)
        cutoff90 = date.today() - timedelta(days=90)
        p30 = [p[1] for p in points if p[0] >= cutoff30]
        p90 = [p[1] for p in points if p[0] >= cutoff90]
        out.append({
            "ingredient_id": ing_id, "name": ing.name,
            "unit": item.base_unit if item else ing.unit,
            "current": round(current, 3), "previous": round(previous, 3),
            "change_pct": round(100 * (current - previous) / previous, 1),
            "trend_30d": round(100 * (p30[-1] - p30[0]) / p30[0], 1) if len(p30) > 1 and p30[0] else 0.0,
            "trend_90d": round(100 * (p90[-1] - p90[0]) / p90[0], 1) if len(p90) > 1 and p90[0] else 0.0,
            "supplier": sup.name if sup else "",
            "points": len(points),
            "history": [{"day": d.isoformat(), "price": round(p, 3)} for d, p, _ in points[-12:]],
        })
    out.sort(key=lambda r: -abs(r["change_pct"]))
    return out


def cost_impact(s: Session) -> list[dict]:
    """Which dishes a price rise actually hurts, and by how much per month."""
    moves = {m["ingredient_id"]: m for m in price_moves(s) if m["change_pct"] >= 5}
    if not moves:
        return []
    items = anbar.items_by_ingredient(s)
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    affected: dict[int, dict] = {}
    for r in s.exec(select(RecipeLine)).all():
        move = moves.get(r.ingredient_id)
        dish = menu.get(r.menu_item_id)
        if not move or not dish:
            continue
        item = items.get(r.ingredient_id)
        qty_base = r.qty_per_portion
        delta_per_portion = qty_base * (move["current"] - move["previous"])
        entry = affected.setdefault(dish.id, {
            "menu_item_id": dish.id, "name": dish.name, "price": round(dish.price, 2),
            "sold_30d": dish.sold_30d, "delta_per_portion": 0.0, "drivers": [],
        })
        entry["delta_per_portion"] += delta_per_portion
        entry["drivers"].append({"name": move["name"], "change_pct": move["change_pct"]})

    out = []
    for entry in affected.values():
        monthly = entry["delta_per_portion"] * entry["sold_30d"]
        detail = anbar.dish_cost(s, entry["menu_item_id"])
        price = entry["price"]
        out.append({
            **entry,
            "delta_per_portion": round(entry["delta_per_portion"], 3),
            "monthly_impact": round(monthly, 2),
            "cost_now": round(detail["cost"], 2),
            "food_cost_pct": round(100 * detail["cost"] / price, 1) if price else 0.0,
        })
    out.sort(key=lambda r: -r["monthly_impact"])
    return out


def supplier_intelligence(s: Session) -> list[dict]:
    """Rank suppliers on the whole picture, not just the invoice."""
    sups = s.exec(select(Supplier)).all()
    receipts = s.exec(select(GoodsReceipt).where(
        GoodsReceipt.status == "confirmed")).all()
    lines_by_receipt = defaultdict(list)
    for line in s.exec(select(GoodsReceiptLine)).all():
        lines_by_receipt[line.receipt_id].append(line)
    pos = s.exec(select(PurchaseOrder)).all()

    out = []
    for sup in sups:
        mine = [r for r in receipts if r.supplier_id == sup.id]
        delivered = len(mine)
        on_time = 0
        rejected_qty = total_qty = 0.0
        spend = 0.0
        issues = 0
        for r in mine:
            po = s.get(PurchaseOrder, r.purchase_order_id) if r.purchase_order_id else None
            expected = getattr(po, "expected_on", None) or (po.deliver_on if po else None)
            if expected is None or r.delivered_on <= expected:
                on_time += 1
            if r.issues:
                issues += 1
            spend += r.total_value
            for line in lines_by_receipt.get(r.id, []):
                rejected_qty += line.rejected_qty
                total_qty += max(line.delivered_qty, line.accepted_qty + line.rejected_qty)

        their_pos = [p for p in pos if p.supplier_id == sup.id]
        committed = sum(p.total for p in their_pos
                        if p.status in ("draft", "pending", "approved", "sent", "partial"))
        on_time_pct = round(100 * on_time / delivered, 1) if delivered else None
        reject_pct = round(100 * rejected_qty / total_qty, 1) if total_qty else 0.0

        # Reliability score blends punctuality, acceptance and price stability.
        # Where a supplier has no delivery history the declared figures on the
        # supplier record stand in, and `basis` says so.
        if delivered:
            score = 0.5 * (on_time_pct or 0) + 0.3 * (100 - reject_pct) + 0.2 * sup.quality
            basis = f"{delivered} confirmed deliveries"
        else:
            score = 0.6 * sup.reliability + 0.4 * sup.quality
            basis = "declared reliability — no deliveries recorded yet"
        out.append({
            "id": sup.id, "name": sup.name, "category": sup.category,
            "contact": getattr(sup, "contact_person", "") or sup.contact,
            "phone": getattr(sup, "phone", ""), "email": getattr(sup, "email", ""),
            "lead_time_days": sup.lead_time_days,
            "payment_terms": getattr(sup, "payment_terms", ""),
            "preferred": bool(getattr(sup, "preferred", False)),
            "deliveries": delivered, "on_time_pct": on_time_pct,
            "reject_pct": reject_pct, "issues": issues,
            "spend": round(spend, 2), "committed": round(committed, 2),
            "orders": len(their_pos),
            "score": round(score, 1), "basis": basis,
            "last_delivery": max((r.delivered_on for r in mine), default=None).isoformat()
                             if mine else None,
        })
    out.sort(key=lambda r: -r["score"])
    return out


def supplier_comparison(s: Session) -> list[dict]:
    """Where two suppliers quote the same ingredient, say which to use and why."""
    offers = defaultdict(list)
    for si in s.exec(select(SupplierItem).where(SupplierItem.active == True)).all():  # noqa: E712
        offers[si.ingredient_id].append(si)
    scores = {x["id"]: x for x in supplier_intelligence(s)}
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    out = []
    for ing_id, rows in offers.items():
        if len(rows) < 2:
            continue
        ing = ings.get(ing_id)
        if not ing:
            continue
        priced = []
        for si in rows:
            per_base = si.price_per_pack / si.pack_size_base if si.pack_size_base else si.price_per_pack
            meta = scores.get(si.supplier_id, {})
            priced.append({
                "supplier_id": si.supplier_id, "supplier": meta.get("name", "—"),
                "price_per_base": round(per_base, 3),
                "score": meta.get("score", 0), "lead_time_days": si.lead_time_days,
                "on_time_pct": meta.get("on_time_pct"),
                "reject_pct": meta.get("reject_pct", 0),
            })
        priced.sort(key=lambda r: r["price_per_base"])
        cheapest, best = priced[0], max(priced, key=lambda r: r["score"])
        note = ""
        if best["supplier_id"] != cheapest["supplier_id"]:
            diff = best["price_per_base"] - cheapest["price_per_base"]
            note = (f"{best['supplier']} costs ₼{round(diff, 2)} more per "
                    f"{ing.unit} but scores {round(best['score'] - cheapest['score'], 1)} "
                    f"points higher on delivery reliability and acceptance. "
                    f"On a perishable line the cheaper quote can cost more once a "
                    f"rejected delivery leaves the kitchen short.")
        else:
            note = f"{cheapest['supplier']} is both the cheapest and the best rated."
        out.append({"ingredient_id": ing_id, "name": ing.name,
                    "offers": priced, "recommendation": note})
    return out


# ---------------------------------------------------------------- waste


def waste_intelligence(s: Session, days: int = 30) -> dict:
    rows = anbar.waste_window(s, days)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    items = anbar.items_by_ingredient(s)
    cats = {c.id: c for c in s.exec(select(InvCategory)).all()}

    by_reason: dict[str, float] = defaultdict(float)
    by_item: dict[str, float] = defaultdict(float)
    by_category: dict[str, float] = defaultdict(float)
    by_weekday: dict[int, float] = defaultdict(float)
    by_staff: dict[str, float] = defaultdict(float)
    total = 0.0
    for w in rows:
        ing = ings.get(w.ingredient_id)
        item = items.get(w.ingredient_id)
        cost = float(getattr(w, "cost_value", 0.0) or 0.0)
        if not cost:
            unit_cost = (item.avg_cost if item and item.avg_cost
                         else (ing.cost_per_unit if ing else 0.0))
            cost = (w.qty or 0.0) * unit_cost
        total += cost
        by_reason[w.reason or "other"] += cost
        if ing:
            by_item[ing.name] += cost
        cat = cats.get(item.category_id) if item and item.category_id else None
        by_category[cat.name if cat else "Other"] += cost
        by_weekday[w.logged_on.weekday()] += cost
        who = str(getattr(w, "staff_name", "") or "")
        if who:
            by_staff[who] += cost

    # Purchases in the same window, so waste can be stated as a percentage
    # of what was bought rather than as a bare number nobody can size.
    purchases = sum(
        r.total_value for r in s.exec(select(GoodsReceipt).where(
            GoodsReceipt.status == "confirmed",
            GoodsReceipt.delivered_on >= date.today() - timedelta(days=days))).all())

    findings = []
    if total > 0:
        top_cat = max(by_category.items(), key=lambda kv: kv[1], default=None)
        if top_cat and top_cat[1] / total >= 0.2:
            findings.append({
                "title": f"{top_cat[0]} is {round(100 * top_cat[1] / total)}% of waste value",
                "body": f"₼{round(top_cat[1], 2)} of ₼{round(total, 2)} wasted over "
                        f"{days} days came from {top_cat[0].lower()}.",
            })
        if by_weekday:
            names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
            worst = max(by_weekday.items(), key=lambda kv: kv[1])
            share = worst[1] / total
            if share >= 0.25:
                findings.append({
                    "title": f"{names[worst[0]]} accounts for {round(100 * share)}% of waste",
                    "body": f"₼{round(worst[1], 2)} of waste is logged on {names[worst[0]]}s. "
                            f"Compare {names[worst[0]]} ordering against actual "
                            f"{names[worst[0]]} covers before the next delivery.",
                })
        top_item = max(by_item.items(), key=lambda kv: kv[1], default=None)
        if top_item and top_item[1] / total >= 0.15:
            findings.append({
                "title": f"{top_item[0]} is the single largest wasted line",
                "body": f"₼{round(top_item[1], 2)} over {days} days. Check par level, "
                        f"order frequency and prep batch size for this item.",
            })

    return {
        "days": days, "total": round(total, 2), "entries": len(rows),
        "purchases": round(purchases, 2),
        "waste_pct_of_purchases": round(100 * total / purchases, 1) if purchases else None,
        "by_reason": sorted(({"name": k, "value": round(v, 2)} for k, v in by_reason.items()),
                            key=lambda r: -r["value"]),
        "by_item": sorted(({"name": k, "value": round(v, 2)} for k, v in by_item.items()),
                          key=lambda r: -r["value"])[:10],
        "by_category": sorted(({"name": k, "value": round(v, 2)} for k, v in by_category.items()),
                              key=lambda r: -r["value"]),
        "by_source": sorted(({"name": k, "value": round(v, 2)} for k, v in by_staff.items()),
                            key=lambda r: -r["value"])[:8],
        "findings": findings,
    }


# ---------------------------------------------------------------- food cost


def food_cost_intelligence(s: Session) -> dict:
    table = anbar.food_cost_table(s)
    if not table:
        return {"dishes": [], "findings": [],
                "note": "No dish has a recipe yet, so food cost cannot be calculated."}
    with_sales = [d for d in table if d["sold_30d"] > 0]
    pool = with_sales or table
    avg_pct = round(statistics.mean(d["food_cost_pct"] for d in pool if d["price"]), 1)

    findings = []
    worst = [d for d in pool if d["food_cost_pct"] >= 35][:5]
    for d in worst:
        findings.append({
            "menu_item_id": d["menu_item_id"],
            "title": f"{d['name']} runs at {d['food_cost_pct']}% food cost",
            "body": f"₼{d['cost']} of ingredients against a ₼{d['price']} menu price "
                    f"(₼{d['margin']} contribution). House average is {avg_pct}%.",
        })
    best = sorted(pool, key=lambda d: -d["monthly_margin"])[:5]
    drift = []
    for d in pool:
        if d["stated_cost"] and d["cost"] > d["stated_cost"] * 1.1:
            drift.append({
                "menu_item_id": d["menu_item_id"],
                "title": f"{d['name']} now costs more than the menu assumes",
                "body": f"Recipe cost is ₼{d['cost']} against the ₼{d['stated_cost']} "
                        f"the menu was priced on — "
                        f"{round(100 * (d['cost'] / d['stated_cost'] - 1))}% higher.",
            })
    return {
        "dishes": table, "average_food_cost_pct": avg_pct,
        "highest": worst, "best_margin": best, "drift": drift[:5],
        "findings": findings,
        "costed_dishes": len(table),
        "total_dishes": len(s.exec(select(MenuItem)).all()),
    }


# ---------------------------------------------------------------- daily brief


def daily_brief(s: Session) -> dict:
    """The paragraph a manager reads first. Only real findings reach it."""
    points: list[dict] = []
    items = anbar.items_by_ingredient(s)
    ings = list(s.exec(select(Ingredient)).all())

    # Stock that will not survive the next service.
    demand = ingredient_demand(s, 1)
    demand_by_id = {r["ingredient_id"]: r for r in demand["rows"]}
    short = []
    for ing in ings:
        item = items.get(ing.id)
        status = anbar.status_for(ing, item)
        row = demand_by_id.get(ing.id)
        if status in ("out", "critical") or (row and row["gap"] > 0):
            short.append((ing, item, status, row))
    for ing, item, status, row in sorted(
            short, key=lambda x: anbar.STATUS_RANK.get(x[2], 9))[:4]:
        unit = item.base_unit if item else ing.unit
        stock = round(float(ing.in_stock or 0), 2)
        if row and row["gap"] > 0:
            points.append({
                "severity": "high" if status in ("out", "critical") else "attention",
                "key": "short_vs_demand",
                "params": {"name": ing.name, "stock": stock, "unit": unit,
                           "required": row["required"]},
                "text": f"{ing.name} may fall below what tomorrow needs — "
                        f"{stock} {unit} on hand against "
                        f"{row['required']} {unit} of expected demand.",
            })
        else:
            points.append({
                "severity": "critical" if status == "out" else "high",
                "key": "out_of_stock" if status == "out" else "below_minimum",
                "params": {"name": ing.name, "stock": stock, "unit": unit},
                "text": f"{ing.name} is {'out of stock' if status == 'out' else 'below minimum stock'} "
                        f"({stock} {unit}).",
            })

    # Expiry.
    exp = expiry_risk(s)
    soon = exp["counts"]["today"] + exp["counts"]["1d"] + exp["counts"]["3d"]
    if soon:
        points.append({
            "severity": "attention", "key": "expiring_soon",
            "params": {"count": soon, "value": exp["value_at_risk"]},
            "text": f"{soon} {'line' if soon == 1 else 'lines'} reach their date within "
                    f"72 hours, ₼{exp['value_at_risk']} of it beyond expected use.",
        })

    # Prices.
    for move in price_moves(s)[:2]:
        if move["change_pct"] >= 8:
            points.append({
                "severity": "attention", "key": "price_up",
                "params": {"name": move["name"], "pct": move["change_pct"],
                           "price": move["current"], "unit": move["unit"]},
                "text": f"{move['name']} purchase price is up {move['change_pct']}% "
                        f"to ₼{move['current']} per {move['unit']}.",
            })

    # Variance / anomaly headline. Anomaly titles are already their own
    # sentences, so they pass through as free text rather than a template.
    for a in anomalies(s)[:2]:
        points.append({"severity": a["severity"], "key": "", "params": {},
                       "text": a["title"] + "."})

    # Tomorrow's book.
    covers = expected_covers(s, 1)
    if covers["reservations"]:
        points.append({
            "severity": "info", "key": "tomorrow_book",
            "params": {"reservations": covers["reservations"],
                       "booked": covers["booked_covers"], "expected": covers["covers"]},
            "text": f"{covers['reservations']} reservations on the book for tomorrow "
                    f"({covers['booked_covers']} covers booked, {covers['covers']} expected "
                    f"including walk-ins).",
        })

    # Approvals waiting.
    pending = s.exec(select(PurchaseOrder).where(
        PurchaseOrder.status == "pending")).all()
    if pending:
        points.append({
            "severity": "attention", "key": "approvals_waiting",
            "params": {"count": len(pending),
                       "value": round(sum(p.total for p in pending), 2)},
            "text": f"{len(pending)} purchase "
                    f"{'order needs' if len(pending) == 1 else 'orders need'} approval "
                    f"(₼{round(sum(p.total for p in pending), 2)}).",
        })

    rank = {"critical": 0, "high": 1, "attention": 2, "info": 3}
    points.sort(key=lambda p: rank.get(p["severity"], 9))
    attention = sum(1 for p in points if p["severity"] != "info")
    if not points:
        headline_key, headline = "all_clear", "Inventory is healthy. Nothing needs attention right now."
    elif attention == 0:
        headline_key, headline = "healthy", "Inventory is healthy."
    else:
        headline_key = "needs_attention"
        headline = (f"Inventory is generally healthy. {attention} "
                    f"{'item' if attention == 1 else 'items'} require attention.")
    return {
        "headline": headline, "headline_key": headline_key,
        "points": points[:8],
        "attention": attention,
        "confidence": demand["confidence"],
        "generated_at": datetime.now().isoformat(timespec="minutes"),
    }


# ---------------------------------------------------------------- executive feed


def executive_signals(s: Session) -> list[dict]:
    """The handful of Anbar facts an owner should see without opening Anbar."""
    out = []
    val = anbar.valuation(s)
    out.append({
        "kind": "inventory_value", "severity": "info",
        "title": "Inventory on hand",
        "value": val["total"],
        "detail": f"₼{val['total']} across {val['items']} lines.",
    })

    fc = food_cost_intelligence(s)
    if fc.get("average_food_cost_pct") is not None and fc.get("dishes"):
        pct = fc["average_food_cost_pct"]
        out.append({
            "kind": "food_cost",
            "severity": "attention" if pct >= 35 else "info",
            "title": "Menu food cost",
            "value": pct,
            "detail": f"{pct}% average across {fc['costed_dishes']} costed dishes.",
        })

    w7 = waste_intelligence(s, 7)
    w_prior = anbar.waste_value(s, [
        x for x in anbar.waste_window(s, 14)
        if x.logged_on < date.today() - timedelta(days=7)])
    if w7["total"] or w_prior:
        change = (round(100 * (w7["total"] - w_prior) / w_prior, 1)
                  if w_prior else None)
        out.append({
            "kind": "waste",
            "severity": "attention" if (change or 0) > 15 else "info",
            "title": "Waste this week",
            "value": w7["total"],
            "detail": (f"₼{w7['total']}"
                       + (f", {'up' if change > 0 else 'down'} {abs(change)}% on last week"
                          if change is not None else "")),
        })

    impacts = cost_impact(s)
    if impacts:
        monthly = round(sum(i["monthly_impact"] for i in impacts), 2)
        if abs(monthly) >= 1:
            out.append({
                "kind": "price_pressure", "severity": "high" if monthly > 0 else "info",
                "title": "Supplier price pressure",
                "value": monthly,
                "detail": f"Recent ingredient price rises are worth about ₼{monthly} "
                          f"a month against current sales volumes, across "
                          f"{len(impacts)} dishes.",
            })

    crit = [a for a in anomalies(s) if a["severity"] in ("critical", "high")]
    if crit:
        out.append({
            "kind": "variance", "severity": "high",
            "title": "Stock discrepancies to review",
            "value": len(crit),
            "detail": crit[0]["title"] + ".",
        })
    return out

"""SUFRA ANBAR — API.

Access is tiered, and the tier is enforced here rather than by hiding
buttons. Three dependencies do the work:

    _view     read the warehouse            managers + inventory manager
    _edit     move stock, receive, count    managers + inventory manager
    _costs    supplier prices, valuation,   owner / GM / restaurant manager
              margins, food cost            + inventory manager
    _approve  release a large purchase      owner / general manager
    _report   report waste or a shortage    the above, plus kitchen

A waiter calling any of these directly gets 403 from the dependency, not a
missing button. Kitchen staff can tell the warehouse something is wrong
without being able to see what anything costs.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .. import anbar, anbar_ai, canon, rtime
from ..anbar import StockError
from ..anbar_models import (GoodsReceipt, GoodsReceiptLine, InvAlert, InvBatch,
                            InvCategory, InvItem, InvLocation, InvStocktake,
                            InvStocktakeLine, InvTransfer, InvTransferLine,
                            InvTxn, SupplierItem)
from ..database import engine
from ..models import (AuditLog, Ingredient, MenuItem, PriceHistory, PurchaseLine,
                      PurchaseOrder, RecipeLine, Role, Staff, Supplier, WasteLog)
from ..permissions import current_staff

router = APIRouter(prefix="/api/anbar")

MANAGE_ROLES = {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER,
                Role.INVENTORY_MANAGER}
COST_ROLES = {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER,
              Role.INVENTORY_MANAGER}
APPROVE_ROLES = {Role.OWNER, Role.GENERAL_MANAGER}
REPORT_ROLES = MANAGE_ROLES | {Role.KITCHEN}

# A purchase order above this needs an owner or general manager. Stored as a
# setting so a venue can tune it without a redeploy.
APPROVAL_SETTING = "anbar_approval_threshold"
DEFAULT_APPROVAL_THRESHOLD = 500.0


def db() -> Session:
    return Session(engine, expire_on_commit=False)


def _view(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in MANAGE_ROLES:
        raise HTTPException(403, "Anbar access requires a management or inventory role.")
    return staff


def _edit(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in MANAGE_ROLES:
        raise HTTPException(403, "Your role cannot change stock.")
    return staff


def _costs(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in COST_ROLES:
        raise HTTPException(403, "Your role cannot see purchasing costs or valuation.")
    return staff


def _approve(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in APPROVE_ROLES:
        raise HTTPException(403, "Owner or general manager approval required.")
    return staff


def _report(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in REPORT_ROLES:
        raise HTTPException(403, "Your role cannot report against the warehouse.")
    return staff


def _err(exc: StockError):
    return JSONResponse({"error": exc.message}, exc.status)


def _threshold(s: Session) -> float:
    try:
        return float(canon.setting(s, APPROVAL_SETTING, str(DEFAULT_APPROVAL_THRESHOLD))
                     or DEFAULT_APPROVAL_THRESHOLD)
    except (TypeError, ValueError):
        return DEFAULT_APPROVAL_THRESHOLD


def _num(body: dict, key: str, default: float = 0.0) -> float:
    try:
        value = float(body.get(key, default))
    except (TypeError, ValueError):
        raise StockError(f"'{key}' must be a number.")
    if value != value or value in (float("inf"), float("-inf")):
        raise StockError(f"'{key}' must be a real number.")
    return value


def _parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


# ==================================================================== overview


@router.get("/overview")
def overview(staff: Staff = Depends(_view)):
    """The Anbar Command Center. Everything here is computed, nothing seeded."""
    with db() as s:
        items = anbar.items_by_ingredient(s)
        ings = list(s.exec(select(Ingredient)).all())
        val = anbar.valuation(s)
        show_money = staff.role in COST_ROLES

        counts = defaultdict(int)
        for ing in ings:
            counts[anbar.status_for(ing, items.get(ing.id))] += 1

        today = date.today()
        waste_today = [w for w in anbar.waste_window(s, 1) if w.logged_on == today]
        waste_week = anbar.waste_window(s, 7)
        waste_month = anbar.waste_window(s, 30)

        month_start = today.replace(day=1)
        receipts = s.exec(select(GoodsReceipt).where(
            GoodsReceipt.status == "confirmed",
            GoodsReceipt.delivered_on >= month_start)).all()

        pending_pos = s.exec(select(PurchaseOrder).where(
            PurchaseOrder.status.in_(["draft", "pending", "approved", "sent", "partial"]))).all()
        awaiting = [p for p in pending_pos if p.status == "pending"]
        expected = [p for p in pending_pos if p.status in ("approved", "sent", "partial")]

        exp = anbar_ai.expiry_risk(s)
        alerts = s.exec(select(InvAlert).where(
            InvAlert.status == "open").order_by(InvAlert.at.desc())).all()
        fc = anbar_ai.food_cost_intelligence(s)

        # Consumption over the ledger, which only exists once bills settle.
        cutoff7 = datetime.now() - timedelta(days=7)
        cutoff30 = datetime.now() - timedelta(days=30)
        txns = s.exec(select(InvTxn).where(InvTxn.at >= cutoff30)).all()
        consumed_7 = round(sum(abs(t.value) for t in txns
                               if t.txn_type == "SALE_CONSUMPTION" and t.at >= cutoff7), 2)
        consumed_30 = round(sum(abs(t.value) for t in txns
                                if t.txn_type == "SALE_CONSUMPTION"), 2)
        received_30 = round(sum(t.value for t in txns
                                if t.txn_type == "PURCHASE_RECEIPT"), 2)

        # Variance: what the ledger says should be here against what is here.
        variance_value = 0.0
        for ing in ings:
            theoretical = anbar.theoretical_stock(s, ing.id)
            if not theoretical:
                continue
            item = items.get(ing.id)
            cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
            variance_value += (float(ing.in_stock or 0) - theoretical) * cost

        daily_series = defaultdict(lambda: {"consumed": 0.0, "received": 0.0, "waste": 0.0})
        for t in txns:
            key = t.at.date().isoformat()
            if t.txn_type == "SALE_CONSUMPTION":
                daily_series[key]["consumed"] += abs(t.value)
            elif t.txn_type == "PURCHASE_RECEIPT":
                daily_series[key]["received"] += t.value
            elif t.txn_type == "WASTE":
                daily_series[key]["waste"] += abs(t.value)

        cards = {
            "inventory_value": val["total"] if show_money else None,
            "active_items": sum(1 for i in items.values() if i.active) or len(ings),
            "low_stock": counts["low"], "critical_stock": counts["critical"],
            "out_of_stock": counts["out"], "over_stocked": counts["over"],
            "expiring_soon": exp["counts"]["today"] + exp["counts"]["1d"] + exp["counts"]["3d"],
            "expiry_value_at_risk": exp["value_at_risk"] if show_money else None,
            "waste_today": anbar.waste_value(s, waste_today) if show_money else None,
            "waste_week": anbar.waste_value(s, waste_week) if show_money else None,
            "waste_month": anbar.waste_value(s, waste_month) if show_money else None,
            "purchases_month": round(sum(r.total_value for r in receipts), 2) if show_money else None,
            "pending_orders": len(awaiting),
            "expected_deliveries": len(expected),
            "food_cost_pct": fc.get("average_food_cost_pct") if show_money else None,
            "variance_value": round(variance_value, 2) if show_money else None,
            "consumed_7d": consumed_7 if show_money else None,
            "consumed_30d": consumed_30 if show_money else None,
            "received_30d": received_30 if show_money else None,
            "open_alerts": len(alerts),
        }

        critical_rows = []
        for ing in ings:
            item = items.get(ing.id)
            status = anbar.status_for(ing, item)
            if status in ("out", "critical", "expired"):
                critical_rows.append({
                    "id": ing.id, "name": ing.name, "name_ru": ing.name_ru, "status": status,
                    "in_stock": round(float(ing.in_stock or 0), 3),
                    "unit": item.base_unit if item else ing.unit,
                    "reorder_point": round((item.reorder_point if item else ing.par_level) or 0, 3),
                    "supplier": ing.supplier or "",
                })
        critical_rows.sort(key=lambda r: anbar.STATUS_RANK.get(r["status"], 9))

        sup_names = {x.id: x.name for x in s.exec(select(Supplier)).all()}
        upcoming = [{
            "id": p.id, "code": getattr(p, "code", "") or f"PO{p.id:05d}",
            "supplier": sup_names.get(p.supplier_id, "—"),
            "status": p.status,
            "expected_on": (getattr(p, "expected_on", None) or p.deliver_on).isoformat()
                           if (getattr(p, "expected_on", None) or p.deliver_on) else None,
            "total": round(p.total, 2) if show_money else None,
        } for p in sorted(expected, key=lambda p: (
            getattr(p, "expected_on", None) or p.deliver_on or date.max))][:8]

        return {
            "cards": cards,
            "stock_health": [{"status": k, "count": v} for k, v in sorted(
                counts.items(), key=lambda kv: anbar.STATUS_RANK.get(kv[0], 9))],
            "value_by_category": val["by_category"] if show_money else [],
            "critical": critical_rows[:10],
            "upcoming_deliveries": upcoming,
            "alerts": [{
                "id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title,
                "body": a.body, "at": a.at.strftime("%d %b %H:%M"),
                "value_at_risk": a.value_at_risk if show_money else None,
            } for a in alerts[:8]],
            "brief": anbar_ai.daily_brief(s),
            "series": [{"day": k, **{kk: round(vv, 2) for kk, vv in v.items()}}
                       for k, v in sorted(daily_series.items())] if show_money else [],
            "can_see_costs": show_money,
            "currency": canon.setting(s, "currency", "₼"),
        }


# ==================================================================== inventory


@router.get("/items")
def list_items(q: str = "", category: int = 0, location: int = 0, status: str = "",
               supplier: int = 0, expiring: str = "", sort: str = "status",
               staff: Staff = Depends(_view)):
    with db() as s:
        items = anbar.items_by_ingredient(s)
        cats = {c.id: c for c in s.exec(select(InvCategory)).all()}
        locs = {l.id: l for l in s.exec(select(InvLocation)).all()}
        sups = {x.id: x.name for x in s.exec(select(Supplier)).all()}
        show_money = staff.role in COST_ROLES
        today = date.today()
        needle = (q or "").strip().lower()

        rows = []
        for ing in s.exec(select(Ingredient)).all():
            item = items.get(ing.id)
            st = anbar.status_for(ing, item, today)
            if needle and needle not in ing.name.lower() and needle not in (
                    item.sku if item else "").lower():
                continue
            if category and (not item or item.category_id != category):
                continue
            if location and (not item or item.location_id != location):
                continue
            if supplier and ing.supplier_id != supplier:
                continue
            if status and st != status:
                continue
            if expiring == "yes" and st not in ("expiring", "expired"):
                continue
            cat = cats.get(item.category_id) if item and item.category_id else None
            loc = locs.get(item.location_id) if item and item.location_id else None
            qty = float(ing.in_stock or 0)
            cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
            rows.append({
                "id": ing.id, "name": ing.name, "name_ru": ing.name_ru,
                "sku": item.sku if item else "",
                "barcode": item.barcode if item else "",
                "category": cat.name if cat else "", "category_id": cat.id if cat else None,
                "location": loc.name if loc else "", "location_id": loc.id if loc else None,
                "unit": item.base_unit if item else ing.unit,
                "purchase_unit": item.purchase_unit if item else ing.unit,
                "recipe_unit": item.recipe_unit if item else ing.unit,
                "recipe_factor": anbar.to_base(item, 1, item.recipe_unit) if item else 1,
                "in_stock": round(qty, 3),
                "min_stock": round(item.min_stock, 3) if item else 0,
                "reorder_point": round((item.reorder_point if item else ing.par_level) or 0, 3),
                "target_stock": round(item.target_stock, 3) if item else 0,
                "max_stock": round(item.max_stock, 3) if item else 0,
                "cost": round(cost, 4) if show_money else None,
                "last_cost": round(item.last_cost, 4) if item and show_money else None,
                "value": round(qty * cost, 2) if show_money else None,
                "supplier": sups.get(ing.supplier_id) or ing.supplier or "",
                "supplier_id": ing.supplier_id,
                "expires_on": ing.expires_on.isoformat() if ing.expires_on else None,
                "status": st,
                "is_food": item.is_food if item else True,
                "active": item.active if item else True,
            })

        keys = {
            "status": lambda r: (anbar.STATUS_RANK.get(r["status"], 9), r["name"]),
            "name": lambda r: r["name"].lower(),
            "value": lambda r: -(r["value"] or 0),
            "stock": lambda r: r["in_stock"],
            "category": lambda r: (r["category"], r["name"]),
        }
        rows.sort(key=keys.get(sort, keys["status"]))
        return {
            "rows": rows, "count": len(rows),
            "can_see_costs": show_money,
            "categories": [{"id": c.id, "name": c.name, "kind": c.kind}
                           for c in sorted(cats.values(), key=lambda c: c.sort_order)],
            "locations": [{"id": l.id, "name": l.name, "kind": l.kind}
                          for l in sorted(locs.values(), key=lambda l: l.sort_order)],
            "suppliers": [{"id": k, "name": v} for k, v in sorted(sups.items(), key=lambda kv: kv[1])],
            "units": anbar.ALL_UNITS,
            "total_value": round(sum(r["value"] or 0 for r in rows), 2) if show_money else None,
        }


@router.get("/items/{ingredient_id}")
def item_detail(ingredient_id: int, staff: Staff = Depends(_view)):
    """Everything known about one line — the product drawer."""
    with db() as s:
        ing = s.get(Ingredient, ingredient_id)
        if not ing:
            return JSONResponse({"error": "That item no longer exists."}, 404)
        item = anbar.item_for(s, ingredient_id)
        show_money = staff.role in COST_ROLES
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
        unit = item.base_unit if item else ing.unit

        txns = s.exec(select(InvTxn).where(
            InvTxn.ingredient_id == ingredient_id).order_by(InvTxn.at.desc())).all()
        batches = s.exec(select(InvBatch).where(
            InvBatch.ingredient_id == ingredient_id,
            InvBatch.qty_base > 0).order_by(InvBatch.expires_on)).all()

        # Which dishes consume it, and what that dish costs.
        menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
        dishes = []
        for r in s.exec(select(RecipeLine).where(
                RecipeLine.ingredient_id == ingredient_id)).all():
            m = menu.get(r.menu_item_id)
            if not m:
                continue
            qty_base = r.qty_per_portion
            dishes.append({
                "menu_item_id": m.id, "name": m.name, "price": round(m.price, 2),
                "qty": round(anbar.from_base(item, r.qty_per_portion, item.recipe_unit) if item else r.qty_per_portion, 4),
                "unit": item.recipe_unit if item else ing.unit,
                "cost_contribution": round(qty_base * cost, 3) if show_money else None,
                "sold_30d": m.sold_30d,
            })

        purchases = []
        for line in s.exec(select(GoodsReceiptLine).where(
                GoodsReceiptLine.ingredient_id == ingredient_id)).all():
            receipt = s.get(GoodsReceipt, line.receipt_id)
            if not receipt:
                continue
            sup = s.get(Supplier, receipt.supplier_id)
            purchases.append({
                "receipt_id": receipt.id, "code": receipt.code,
                "date": receipt.delivered_on.isoformat(),
                "supplier": sup.name if sup else "—",
                "qty": round(line.accepted_qty, 3),
                "unit_price": round(line.unit_price, 4) if show_money else None,
                "status": receipt.status,
            })
        purchases.sort(key=lambda r: r["date"], reverse=True)

        # id descending, not logged_on: several entries share a date, and a
        # date-only sort leaves same-day rows in whatever order the database
        # happens to return, so "the last thing thrown away" moves around.
        waste_rows = s.exec(select(WasteLog).where(
            WasteLog.ingredient_id == ingredient_id).order_by(
            WasteLog.id.desc())).all()

        offers = []
        for si in s.exec(select(SupplierItem).where(
                SupplierItem.ingredient_id == ingredient_id)).all():
            sup = s.get(Supplier, si.supplier_id)
            offers.append({
                "id": si.id, "supplier": sup.name if sup else "—",
                "supplier_id": si.supplier_id,
                "pack_unit": si.pack_unit, "pack_size_base": si.pack_size_base,
                "price_per_pack": round(si.price_per_pack, 3) if show_money else None,
                "price_per_base": round(si.price_per_pack / si.pack_size_base, 4)
                                  if show_money and si.pack_size_base else None,
                "lead_time_days": si.lead_time_days, "preferred": si.preferred,
                "min_order_qty": si.min_order_qty,
            })

        theoretical = anbar.theoretical_stock(s, ingredient_id)
        qty = float(ing.in_stock or 0)
        sup = s.get(Supplier, ing.supplier_id) if ing.supplier_id else None
        demand_row = next((r for r in anbar_ai.ingredient_demand(s, 1)["rows"]
                           if r["ingredient_id"] == ingredient_id), None)

        return {
            "item": {
                "id": ing.id, "name": ing.name, "name_ru": ing.name_ru, "unit": unit,
                "sku": item.sku if item else "", "barcode": item.barcode if item else "",
                "in_stock": round(qty, 3),
                "status": anbar.status_for(ing, item),
                "value": round(qty * cost, 2) if show_money else None,
                "cost": round(cost, 4) if show_money else None,
                "last_cost": round(item.last_cost, 4) if item and show_money else None,
                "min_stock": item.min_stock if item else 0,
                "reorder_point": (item.reorder_point if item else ing.par_level) or 0,
                "target_stock": item.target_stock if item else 0,
                "max_stock": item.max_stock if item else 0,
                "base_unit": unit,
                "purchase_unit": item.purchase_unit if item else ing.unit,
                "purchase_factor": item.purchase_factor if item else 1,
                "recipe_unit": item.recipe_unit if item else ing.unit,
                "recipe_factor": item.recipe_factor if item else 1,
                "category_id": item.category_id if item else None,
                "location_id": item.location_id if item else None,
                "supplier": sup.name if sup else ing.supplier,
                "supplier_id": ing.supplier_id,
                "shelf_life_days": item.shelf_life_days if item else 0,
                "storage_temp": item.storage_temp if item else "",
                "track_batches": item.track_batches if item else False,
                "is_food": item.is_food if item else True,
                "notes": item.notes if item else "",
                "expires_on": ing.expires_on.isoformat() if ing.expires_on else None,
            },
            "usage": {
                "today": anbar.usage(s, ingredient_id, 1),
                "d7": anbar.usage(s, ingredient_id, 7),
                "d30": anbar.usage(s, ingredient_id, 30),
                "expected_tomorrow": demand_row["required"] if demand_row else 0.0,
            },
            "variance": {
                "theoretical": round(theoretical, 3), "physical": round(qty, 3),
                "qty": round(qty - theoretical, 3),
                "value": round((qty - theoretical) * cost, 2) if show_money else None,
            },
            "dishes": sorted(dishes, key=lambda d: -d["sold_30d"]),
            "batches": [{
                "id": b.id, "code": b.batch_code, "qty": round(b.qty_base, 3),
                "unit_cost": round(b.unit_cost, 4) if show_money else None,
                "received_on": b.received_on.isoformat(),
                "expires_on": b.expires_on.isoformat() if b.expires_on else None,
                "days_left": (b.expires_on - date.today()).days if b.expires_on else None,
                "status": b.status,
            } for b in batches],
            "purchases": purchases[:20],
            "offers": offers,
            "waste": [{
                "id": w.id, "qty": round(w.qty, 3), "reason": w.reason,
                "date": w.logged_on.isoformat(),
                "cost": round(float(getattr(w, "cost_value", 0) or 0), 2) if show_money else None,
                "by": str(getattr(w, "staff_name", "") or ""),
            } for w in waste_rows[:20]],
            "ledger": [{
                "id": t.id, "at": t.at.strftime("%d %b %H:%M"), "type": t.txn_type,
                "qty": round(t.qty_base, 3), "balance": round(t.balance_after, 3),
                "value": round(t.value, 2) if show_money else None,
                "by": t.staff_name, "reason": t.reason, "note": t.note,
            } for t in txns[:40]],
            "can_see_costs": show_money,
        }


@router.post("/items")
def create_item(body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Create a new stock line. Writes both the Ingredient and its profile."""
    with db() as s:
        name = str(body.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Give the item a name."}, 400)
        if s.exec(select(Ingredient).where(Ingredient.name == name)).first():
            return JSONResponse({"error": f"'{name}' already exists in inventory."}, 409)
        try:
            base_unit = str(body.get("base_unit") or "kg").strip().lower()
            ing = Ingredient(
                name=name, unit=base_unit,
                in_stock=0.0,
                par_level=_num(body, "reorder_point"),
                cost_per_unit=_num(body, "cost"),
                supplier_id=int(body["supplier_id"]) if body.get("supplier_id") else None,
                store=str(body.get("location_name") or "").strip(),
                expires_on=_parse_date(body.get("expires_on", "")))
            s.add(ing)
            s.flush()
            cat_id = int(body["category_id"]) if body.get("category_id") else None
            cat = s.get(InvCategory, cat_id) if cat_id else None
            item = InvItem(
                ingredient_id=ing.id,
                sku=str(body.get("sku") or f"SKU{ing.id:04d}").strip(),
                barcode=str(body.get("barcode") or "").strip(),
                category_id=cat_id,
                location_id=int(body["location_id"]) if body.get("location_id") else None,
                base_unit=base_unit,
                purchase_unit=str(body.get("purchase_unit") or base_unit).strip().lower(),
                purchase_factor=_num(body, "purchase_factor", 1.0) or 1.0,
                recipe_unit=str(body.get("recipe_unit") or base_unit).strip().lower(),
                recipe_factor=_num(body, "recipe_factor", 1.0) or 1.0,
                min_stock=_num(body, "min_stock"),
                reorder_point=_num(body, "reorder_point"),
                target_stock=_num(body, "target_stock"),
                max_stock=_num(body, "max_stock"),
                avg_cost=_num(body, "cost"), last_cost=_num(body, "cost"),
                shelf_life_days=int(_num(body, "shelf_life_days")),
                storage_temp=str(body.get("storage_temp") or "").strip(),
                track_batches=bool(body.get("track_batches")),
                is_food=(cat.kind != "non_food") if cat else bool(body.get("is_food", True)),
                notes=str(body.get("notes") or "").strip())
            s.add(item)
            opening = _num(body, "opening_qty")
            s.flush()
            if opening > 0:
                anbar.post(s, ingredient_id=ing.id, qty_base=opening,
                           txn_type="MANUAL_ADJUSTMENT", staff=staff,
                           unit_cost=_num(body, "cost"), reason="opening balance",
                           idem_key=f"opening:{ing.id}")
            anbar.audit(s, staff, "anbar_item_create", "ingredient", ing.id,
                        f"{name} created with opening {opening} {base_unit}")
        except StockError as exc:
            return _err(exc)
        s.commit()
        return {"ok": True, "id": ing.id, "message": f"{name} added to inventory."}


@router.post("/items/{ingredient_id}")
def update_item(ingredient_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Edit the profile. Never touches quantity — that is what adjust is for."""
    with db() as s:
        ing = s.get(Ingredient, ingredient_id)
        if not ing:
            return JSONResponse({"error": "That item no longer exists."}, 404)
        item = anbar.item_for(s, ingredient_id)
        if item is None:
            item = InvItem(ingredient_id=ingredient_id, base_unit=ing.unit)
            s.add(item)
            s.flush()
        changes = []
        if "name" in body and str(body["name"]).strip():
            new = str(body["name"]).strip()
            if new != ing.name:
                changes.append(f"name {ing.name} -> {new}")
                ing.name = new
        for field, attr, cast in (
                ("sku", "sku", str), ("barcode", "barcode", str),
                ("category_id", "category_id", int), ("location_id", "location_id", int),
                ("base_unit", "base_unit", str), ("purchase_unit", "purchase_unit", str),
                ("recipe_unit", "recipe_unit", str),
                ("purchase_factor", "purchase_factor", float),
                ("recipe_factor", "recipe_factor", float),
                ("min_stock", "min_stock", float), ("reorder_point", "reorder_point", float),
                ("target_stock", "target_stock", float), ("max_stock", "max_stock", float),
                ("shelf_life_days", "shelf_life_days", int),
                ("storage_temp", "storage_temp", str), ("notes", "notes", str)):
            if field not in body:
                continue
            try:
                value = cast(body[field]) if body[field] not in (None, "") else (
                    "" if cast is str else 0)
            except (TypeError, ValueError):
                return JSONResponse({"error": f"'{field}' is not valid."}, 400)
            old = getattr(item, attr)
            if old != value:
                changes.append(f"{field} {old} -> {value}")
                setattr(item, attr, value)
        if "track_batches" in body:
            item.track_batches = bool(body["track_batches"])
        if "is_food" in body:
            item.is_food = bool(body["is_food"])
        if "active" in body:
            item.active = bool(body["active"])
        if "supplier_id" in body:
            ing.supplier_id = int(body["supplier_id"]) if body["supplier_id"] else None
            sup = s.get(Supplier, ing.supplier_id) if ing.supplier_id else None
            ing.supplier = sup.name if sup else ""
        if "expires_on" in body:
            ing.expires_on = _parse_date(body["expires_on"])
        item.updated_at = datetime.now()
        ing.unit = item.base_unit or ing.unit
        ing.par_level = item.reorder_point or ing.par_level
        s.add(item)
        s.add(ing)
        anbar.audit(s, staff, "anbar_item_update", "ingredient", ingredient_id,
                    "; ".join(changes)[:380] or "no field changed")
        s.commit()
        return {"ok": True, "message": f"{ing.name} updated.", "changes": len(changes)}


@router.post("/items/{ingredient_id}/adjust")
def adjust(ingredient_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Manual correction. Reason is mandatory and everything is a ledger row."""
    with db() as s:
        reason = str(body.get("reason") or "").strip()
        if not reason:
            return JSONResponse({"error": "A reason is required for a manual adjustment."}, 400)
        try:
            item = anbar.item_for(s, ingredient_id)
            qty = _num(body, "qty")
            unit = str(body.get("unit") or (item.base_unit if item else "")).strip()
            qty_base = anbar.to_base(item, qty, unit)
            mode = str(body.get("mode") or "delta")
            ing = s.get(Ingredient, ingredient_id)
            if not ing:
                return JSONResponse({"error": "That item no longer exists."}, 404)
            if mode == "set":
                qty_base = qty_base - float(ing.in_stock or 0)
            if abs(qty_base) < 1e-9:
                return JSONResponse({"error": "That adjustment would change nothing."}, 400)
            txn = anbar.post(s, ingredient_id=ingredient_id, qty_base=qty_base,
                             txn_type="MANUAL_ADJUSTMENT", staff=staff, reason=reason,
                             note=str(body.get("note") or "").strip(),
                             allow_negative=False)
        except StockError as exc:
            return _err(exc)
        anbar.audit(s, staff, "anbar_adjust", "ingredient", ingredient_id,
                    f"{qty_base:+.3f} {ing.unit} — {reason}")
        s.commit()
        return {"ok": True, "balance": round(float(ing.in_stock or 0), 3),
                "message": f"{ing.name} adjusted by {qty_base:+.3f} {ing.unit}."}


# ==================================================================== categories & locations


@router.get("/reference")
def reference(staff: Staff = Depends(_view)):
    with db() as s:
        return {
            "categories": [{
                "id": c.id, "name": c.name, "name_az": c.name_az, "name_ru": c.name_ru,
                "kind": c.kind, "sort_order": c.sort_order, "active": c.active,
                "items": len(s.exec(select(InvItem).where(InvItem.category_id == c.id)).all()),
            } for c in s.exec(select(InvCategory).order_by(InvCategory.sort_order)).all()],
            "locations": [{
                "id": l.id, "name": l.name, "name_az": l.name_az, "name_ru": l.name_ru,
                "kind": l.kind, "temp_c": l.temp_c, "is_default": l.is_default,
                "active": l.active,
                "items": len(s.exec(select(InvItem).where(InvItem.location_id == l.id)).all()),
            } for l in s.exec(select(InvLocation).order_by(InvLocation.sort_order)).all()],
            "units": anbar.ALL_UNITS,
            "waste_reasons": anbar.WASTE_REASONS,
        }


@router.post("/categories")
def create_category(body: dict = Body(...), staff: Staff = Depends(_edit)):
    with db() as s:
        name = str(body.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Give the category a name."}, 400)
        if s.exec(select(InvCategory).where(InvCategory.name == name)).first():
            return JSONResponse({"error": "That category already exists."}, 409)
        c = InvCategory(name=name, name_az=str(body.get("name_az") or "").strip(),
                        name_ru=str(body.get("name_ru") or "").strip(),
                        kind=str(body.get("kind") or "food"),
                        sort_order=int(_num(body, "sort_order", 50)))
        s.add(c)
        anbar.audit(s, staff, "anbar_category_create", "invcategory", None, name)
        s.commit()
        return {"ok": True, "id": c.id, "message": f"Category '{name}' added."}


@router.post("/locations")
def create_location(body: dict = Body(...), staff: Staff = Depends(_edit)):
    with db() as s:
        name = str(body.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Give the storage location a name."}, 400)
        if s.exec(select(InvLocation).where(InvLocation.name == name)).first():
            return JSONResponse({"error": "That location already exists."}, 409)
        temp = body.get("temp_c")
        l = InvLocation(name=name, name_az=str(body.get("name_az") or "").strip(),
                        name_ru=str(body.get("name_ru") or "").strip(),
                        kind=str(body.get("kind") or "warehouse"),
                        temp_c=float(temp) if temp not in (None, "") else None,
                        sort_order=int(_num(body, "sort_order", 50)))
        s.add(l)
        anbar.audit(s, staff, "anbar_location_create", "invlocation", None, name)
        s.commit()
        return {"ok": True, "id": l.id, "message": f"Location '{name}' added."}


# ==================================================================== suppliers


@router.get("/suppliers")
def suppliers(staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        rows = anbar_ai.supplier_intelligence(s)
        if not show_money:
            for r in rows:
                r["spend"] = r["committed"] = None
        return {
            "rows": rows,
            "comparison": anbar_ai.supplier_comparison(s) if show_money else [],
            "price_moves": anbar_ai.price_moves(s)[:20] if show_money else [],
            "can_see_costs": show_money,
        }


@router.post("/suppliers")
def create_supplier(body: dict = Body(...), staff: Staff = Depends(_edit)):
    with db() as s:
        name = str(body.get("name") or "").strip()
        if not name:
            return JSONResponse({"error": "Give the supplier a name."}, 400)
        sup = Supplier(
            name=name, category=str(body.get("category") or "Produce").strip(),
            contact=str(body.get("contact") or "").strip(),
            lead_time_days=int(_num(body, "lead_time_days", 1)),
            reliability=int(_num(body, "reliability", 90)),
            quality=int(_num(body, "quality", 90)),
            notes=str(body.get("notes") or "").strip())
        for field in ("legal_name", "contact_person", "phone", "email", "address",
                      "payment_terms", "delivery_days"):
            if hasattr(sup, field):
                setattr(sup, field, str(body.get(field) or "").strip())
        if hasattr(sup, "min_order_value"):
            sup.min_order_value = _num(body, "min_order_value")
        if hasattr(sup, "preferred"):
            sup.preferred = bool(body.get("preferred"))
        s.add(sup)
        s.flush()
        anbar.audit(s, staff, "anbar_supplier_create", "supplier", sup.id, name)
        s.commit()
        return {"ok": True, "id": sup.id, "message": f"{name} added."}


@router.post("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    with db() as s:
        sup = s.get(Supplier, supplier_id)
        if not sup:
            return JSONResponse({"error": "That supplier no longer exists."}, 404)
        for field in ("name", "category", "contact", "notes", "legal_name",
                      "contact_person", "phone", "email", "address",
                      "payment_terms", "delivery_days"):
            if field in body and hasattr(sup, field):
                setattr(sup, field, str(body[field] or "").strip())
        for field in ("lead_time_days", "reliability", "quality"):
            if field in body:
                setattr(sup, field, int(_num(body, field)))
        if "min_order_value" in body and hasattr(sup, "min_order_value"):
            sup.min_order_value = _num(body, "min_order_value")
        if "preferred" in body and hasattr(sup, "preferred"):
            sup.preferred = bool(body["preferred"])
        s.add(sup)
        anbar.audit(s, staff, "anbar_supplier_update", "supplier", supplier_id, sup.name)
        s.commit()
        return {"ok": True, "message": f"{sup.name} updated."}


@router.post("/supplier-items")
def upsert_supplier_item(body: dict = Body(...), staff: Staff = Depends(_costs)):
    """Record what a supplier charges for an ingredient, so Anbar can compare."""
    with db() as s:
        try:
            supplier_id = int(body["supplier_id"])
            ingredient_id = int(body["ingredient_id"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose a supplier and an ingredient."}, 400)
        if not s.get(Supplier, supplier_id) or not s.get(Ingredient, ingredient_id):
            return JSONResponse({"error": "Supplier or ingredient not found."}, 404)
        row = s.exec(select(SupplierItem).where(
            SupplierItem.supplier_id == supplier_id,
            SupplierItem.ingredient_id == ingredient_id)).first()
        if row is None:
            row = SupplierItem(supplier_id=supplier_id, ingredient_id=ingredient_id)
        item = anbar.item_for(s, ingredient_id)
        row.pack_unit = str(body.get("pack_unit") or (item.purchase_unit if item else "kg"))
        row.pack_size_base = _num(body, "pack_size_base", 1.0) or 1.0
        row.price_per_pack = _num(body, "price_per_pack")
        row.min_order_qty = _num(body, "min_order_qty")
        row.lead_time_days = int(_num(body, "lead_time_days", 1))
        row.preferred = bool(body.get("preferred"))
        row.supplier_sku = str(body.get("supplier_sku") or "").strip()
        row.last_quoted_on = date.today()
        s.add(row)
        if row.price_per_pack and row.pack_size_base:
            s.add(PriceHistory(ingredient_id=ingredient_id, supplier_id=supplier_id,
                               price=round(row.price_per_pack / row.pack_size_base, 4)))
        anbar.audit(s, staff, "anbar_supplier_price", "ingredient", ingredient_id,
                    f"supplier {supplier_id} quoted {row.price_per_pack}/{row.pack_unit}")
        s.commit()
        return {"ok": True, "message": "Supplier price recorded."}


# ==================================================================== purchase orders


@router.get("/purchase-orders")
def purchase_orders(status: str = "", staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        sup_names = {x.id: x.name for x in s.exec(select(Supplier)).all()}
        ings = {i.id: i.name for i in s.exec(select(Ingredient)).all()}
        q = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
        if status:
            q = q.where(PurchaseOrder.status == status)
        rows = []
        for p in s.exec(q).all():
            lines = s.exec(select(PurchaseLine).where(PurchaseLine.order_id == p.id)).all()
            rows.append({
                "id": p.id, "code": getattr(p, "code", "") or f"PO{p.id:05d}",
                "supplier": sup_names.get(p.supplier_id, "—"),
                "supplier_id": p.supplier_id, "status": p.status,
                "created_at": p.created_at.strftime("%d %b %H:%M"),
                "expected_on": (getattr(p, "expected_on", None) or p.deliver_on).isoformat()
                               if (getattr(p, "expected_on", None) or p.deliver_on) else None,
                "total": round(p.total, 2) if show_money else None,
                "raised_by": p.raised_by,
                "approved_by": getattr(p, "approved_by", "") or "",
                "note": getattr(p, "note", "") or "",
                "lines": [{
                    "ingredient_id": l.ingredient_id, "name": ings.get(l.ingredient_id, "—"),
                    "qty": round(getattr(l, "qty_base", 0) or l.qty, 3),
                    "unit": getattr(l, "purchase_unit", "") or "",
                    "received": round(getattr(l, "received_qty", 0) or 0, 3),
                    "unit_price": round(l.unit_price, 3) if show_money else None,
                } for l in lines],
            })
        return {"rows": rows, "can_see_costs": show_money,
                "approval_threshold": _threshold(s)}


@router.post("/purchase-orders")
def create_po(body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Raise a purchase order. Above the approval threshold it opens as
    'pending' and cannot be sent until an owner or GM releases it."""
    with db() as s:
        try:
            supplier_id = int(body["supplier_id"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose a supplier."}, 400)
        sup = s.get(Supplier, supplier_id)
        if not sup:
            return JSONResponse({"error": "That supplier no longer exists."}, 404)
        lines = body.get("lines") or []
        if not lines:
            return JSONResponse({"error": "Add at least one line to the order."}, 400)

        po = PurchaseOrder(supplier_id=supplier_id, status="draft", total=0.0,
                           raised_by=staff.name,
                           deliver_on=_parse_date(body.get("expected_on", "")))
        for field, value in (("code", ""), ("note", str(body.get("note") or "").strip()),
                             ("created_by_id", staff.id),
                             ("expected_on", _parse_date(body.get("expected_on", "")))):
            if hasattr(po, field):
                setattr(po, field, value)
        s.add(po)
        s.flush()
        if hasattr(po, "code"):
            po.code = f"PO{po.id:05d}"

        subtotal = 0.0
        items = anbar.items_by_ingredient(s)
        for raw in lines:
            try:
                ing_id = int(raw["ingredient_id"])
                qty = float(raw.get("qty", 0))
                price = float(raw.get("unit_price", 0))
            except (KeyError, TypeError, ValueError):
                return JSONResponse({"error": "Every line needs an item, a quantity and a price."}, 400)
            if qty <= 0:
                continue
            ing = s.get(Ingredient, ing_id)
            if not ing:
                continue
            item = items.get(ing_id)
            unit = str(raw.get("unit") or (item.purchase_unit if item else ing.unit))
            qty_base = anbar.to_base(item, qty, unit)
            line = PurchaseLine(order_id=po.id, ingredient_id=ing_id,
                                qty=qty, unit_price=price)
            for field, value in (("purchase_unit", unit), ("qty_base", qty_base),
                                 ("received_qty", 0.0),
                                 ("note", str(raw.get("note") or "").strip())):
                if hasattr(line, field):
                    setattr(line, field, value)
            s.add(line)
            subtotal += qty * price

        tax = _num(body, "tax")
        po.total = round(subtotal + tax, 2)
        for field, value in (("subtotal", round(subtotal, 2)), ("tax", round(tax, 2))):
            if hasattr(po, field):
                setattr(po, field, value)
        threshold = _threshold(s)
        po.status = "pending" if po.total > threshold else "draft"
        s.add(po)
        if po.status == "pending":
            anbar.raise_alert(s, f"po_approval:{po.id}", "approval", "attention",
                              f"Purchase order {getattr(po, 'code', po.id)} needs approval",
                              f"₼{po.total} to {sup.name} is above the ₼{threshold} "
                              f"approval threshold.", ref_type="purchase_order", ref_id=po.id)
        anbar.audit(s, staff, "anbar_po_create", "purchaseorder", po.id,
                    f"{sup.name} ₼{po.total} ({po.status})")
        s.commit()
        return {"ok": True, "id": po.id, "status": po.status, "total": po.total,
                "message": (f"Order raised for ₼{po.total}. It needs owner approval "
                            f"before it can be sent." if po.status == "pending"
                            else f"Draft order raised for ₼{po.total}.")}


@router.post("/purchase-orders/{po_id}/status")
def po_status(po_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """draft -> pending -> approved -> sent -> (receiving handles the rest)."""
    with db() as s:
        po = s.get(PurchaseOrder, po_id)
        if not po:
            return JSONResponse({"error": "That order no longer exists."}, 404)
        target = str(body.get("status") or "").strip().lower()
        allowed = {"draft", "pending", "approved", "sent", "cancelled"}
        if target not in allowed:
            return JSONResponse({"error": f"'{target}' is not a valid order status."}, 400)
        if target == "approved":
            if po.total > _threshold(s) and staff.role not in APPROVE_ROLES:
                return JSONResponse(
                    {"error": f"₼{po.total} is above the approval threshold — "
                              f"an owner or general manager must release it."}, 403)
            if hasattr(po, "approved_by"):
                po.approved_by = staff.name
                po.approved_at = datetime.now()
            for a in s.exec(select(InvAlert).where(
                    InvAlert.key == f"po_approval:{po.id}",
                    InvAlert.status == "open")).all():
                a.status = "resolved"
                s.add(a)
        if target == "sent" and po.status == "pending":
            return JSONResponse({"error": "This order must be approved before it is sent."}, 409)
        if target == "sent" and hasattr(po, "sent_at"):
            po.sent_at = datetime.now()
        previous, po.status = po.status, target
        s.add(po)
        anbar.audit(s, staff, "anbar_po_status", "purchaseorder", po_id,
                    f"{previous} -> {target}")
        s.commit()
        return {"ok": True, "status": target,
                "message": f"Order {getattr(po, 'code', po_id)} is now {target}."}


@router.get("/reorder")
def reorder(horizon: int = 3, staff: Staff = Depends(_view)):
    with db() as s:
        plan = anbar_ai.reorder_plan(s, max(1, min(14, horizon)))
        if staff.role not in COST_ROLES:
            for r in plan["rows"]:
                r["value"] = None
            plan["total_value"] = None
        return plan


# ==================================================================== receiving


@router.get("/receipts")
def receipts(staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        sup_names = {x.id: x.name for x in s.exec(select(Supplier)).all()}
        ings = {i.id: i.name for i in s.exec(select(Ingredient)).all()}
        rows = []
        for r in s.exec(select(GoodsReceipt).order_by(GoodsReceipt.created_at.desc())).all():
            lines = s.exec(select(GoodsReceiptLine).where(
                GoodsReceiptLine.receipt_id == r.id)).all()
            rows.append({
                "id": r.id, "code": r.code, "supplier": sup_names.get(r.supplier_id, "—"),
                "supplier_id": r.supplier_id,
                "purchase_order_id": r.purchase_order_id,
                "invoice_ref": r.invoice_ref,
                "delivered_on": r.delivered_on.isoformat(),
                "status": r.status, "issues": r.issues,
                "received_by": r.received_by, "note": r.note,
                "total_value": round(r.total_value, 2) if show_money else None,
                "lines": [{
                    "id": l.id, "ingredient_id": l.ingredient_id,
                    "name": ings.get(l.ingredient_id, "—"),
                    "ordered": round(l.ordered_qty, 3),
                    "delivered": round(l.delivered_qty, 3),
                    "accepted": round(l.accepted_qty, 3),
                    "rejected": round(l.rejected_qty, 3),
                    "reject_reason": l.reject_reason, "quality": l.quality,
                    "batch_code": l.batch_code,
                    "expires_on": l.expires_on.isoformat() if l.expires_on else None,
                    "unit_price": round(l.unit_price, 3) if show_money else None,
                } for l in lines],
            })
        return {"rows": rows, "can_see_costs": show_money}


@router.post("/receipts")
def create_receipt(body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Open a delivery. Nothing moves until it is confirmed."""
    with db() as s:
        try:
            supplier_id = int(body["supplier_id"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose the supplier who delivered."}, 400)
        if not s.get(Supplier, supplier_id):
            return JSONResponse({"error": "That supplier no longer exists."}, 404)
        po_id = int(body["purchase_order_id"]) if body.get("purchase_order_id") else None
        receipt = GoodsReceipt(
            supplier_id=supplier_id, purchase_order_id=po_id,
            invoice_ref=str(body.get("invoice_ref") or "").strip(),
            delivered_on=_parse_date(body.get("delivered_on", "")) or date.today(),
            location_id=int(body["location_id"]) if body.get("location_id") else None,
            status="draft", received_by_id=staff.id, received_by=staff.name,
            note=str(body.get("note") or "").strip())
        s.add(receipt)
        s.flush()
        receipt.code = f"GR{receipt.id:05d}"

        items = anbar.items_by_ingredient(s)
        lines = body.get("lines") or []
        # Pre-fill from the purchase order when one is named and no lines were sent.
        if po_id and not lines:
            for pl in s.exec(select(PurchaseLine).where(PurchaseLine.order_id == po_id)).all():
                ordered = float(getattr(pl, "qty_base", 0) or pl.qty)
                lines.append({"ingredient_id": pl.ingredient_id, "ordered_qty": ordered,
                              "delivered_qty": ordered, "accepted_qty": ordered,
                              "unit_price": pl.unit_price})
        if not lines:
            return JSONResponse({"error": "A delivery needs at least one line."}, 400)

        total = 0.0
        for raw in lines:
            try:
                ing_id = int(raw["ingredient_id"])
            except (KeyError, TypeError, ValueError):
                continue
            ing = s.get(Ingredient, ing_id)
            if not ing:
                continue
            item = items.get(ing_id)
            unit = str(raw.get("unit") or (item.purchase_unit if item else ing.unit))
            delivered = anbar.to_base(item, float(raw.get("delivered_qty", 0) or 0), unit)
            accepted_raw = raw.get("accepted_qty")
            accepted = (anbar.to_base(item, float(accepted_raw), unit)
                        if accepted_raw not in (None, "") else delivered)
            rejected = max(0.0, delivered - accepted)
            price_per_pack = float(raw.get("unit_price", 0) or 0)
            factor = (item.purchase_factor if item and unit == item.purchase_unit else 1.0) or 1.0
            unit_price_base = price_per_pack / factor if factor else price_per_pack
            line = GoodsReceiptLine(
                receipt_id=receipt.id, ingredient_id=ing_id,
                ordered_qty=anbar.to_base(item, float(raw.get("ordered_qty", 0) or 0), unit),
                delivered_qty=delivered, accepted_qty=accepted, rejected_qty=rejected,
                reject_reason=str(raw.get("reject_reason") or "").strip(),
                unit_price=unit_price_base,
                batch_code=str(raw.get("batch_code") or "").strip(),
                expires_on=_parse_date(raw.get("expires_on", "")),
                quality=str(raw.get("quality") or "ok"))
            s.add(line)
            total += accepted * unit_price_base
        receipt.total_value = round(total, 2)
        receipt.issues = ",".join(sorted({
            str(r.get("quality")) for r in lines
            if r.get("quality") and r.get("quality") != "ok"}))
        s.add(receipt)
        anbar.audit(s, staff, "anbar_receipt_create", "goodsreceipt", receipt.id,
                    f"{receipt.code} draft, ₼{receipt.total_value}")
        s.commit()
        return {"ok": True, "id": receipt.id, "code": receipt.code,
                "total": receipt.total_value,
                "message": f"{receipt.code} opened. Confirm it to take the stock in."}


@router.post("/receipts/{receipt_id}/confirm")
def confirm_receipt(receipt_id: int, staff: Staff = Depends(_edit)):
    """Take the delivery into stock. Only accepted quantity moves, once."""
    with db() as s:
        receipt = s.get(GoodsReceipt, receipt_id)
        if not receipt:
            return JSONResponse({"error": "That delivery no longer exists."}, 404)
        if receipt.status == "confirmed":
            return JSONResponse({"error": "This delivery has already been taken into stock."}, 409)
        if receipt.status == "cancelled":
            return JSONResponse({"error": "This delivery was cancelled."}, 409)

        lines = s.exec(select(GoodsReceiptLine).where(
            GoodsReceiptLine.receipt_id == receipt_id)).all()
        items = anbar.items_by_ingredient(s)
        moved = 0
        for line in lines:
            if line.accepted_qty <= 0:
                continue
            item = items.get(line.ingredient_id)
            batch_id = None
            if item and (item.track_batches or line.expires_on):
                batch = InvBatch(
                    ingredient_id=line.ingredient_id,
                    location_id=receipt.location_id or (item.location_id if item else None),
                    batch_code=line.batch_code or f"{receipt.code}-{line.id}",
                    qty_received=line.accepted_qty, qty_base=line.accepted_qty,
                    unit_cost=line.unit_price, received_on=receipt.delivered_on,
                    expires_on=line.expires_on, supplier_id=receipt.supplier_id,
                    receipt_id=receipt.id)
                s.add(batch)
                s.flush()
                batch_id = batch.id
            try:
                anbar.post(s, ingredient_id=line.ingredient_id, qty_base=line.accepted_qty,
                           txn_type="PURCHASE_RECEIPT", staff=staff,
                           unit_cost=line.unit_price, batch_id=batch_id,
                           location_id=receipt.location_id,
                           ref_type="goods_receipt_line", ref_id=line.id,
                           idem_key=f"receipt:{line.id}",
                           reason="delivery accepted", note=receipt.code)
                moved += 1
            except StockError as exc:
                return _err(exc)
            if line.unit_price:
                s.add(PriceHistory(ingredient_id=line.ingredient_id,
                                   supplier_id=receipt.supplier_id,
                                   price=round(line.unit_price, 4),
                                   on_day=receipt.delivered_on))
            ing = s.get(Ingredient, line.ingredient_id)
            if ing and line.expires_on and (not ing.expires_on or line.expires_on < ing.expires_on):
                ing.expires_on = line.expires_on
                s.add(ing)

        receipt.status = "confirmed"
        receipt.confirmed_at = datetime.now()
        s.add(receipt)

        # Close the purchase order off when everything ordered has arrived.
        if receipt.purchase_order_id:
            po = s.get(PurchaseOrder, receipt.purchase_order_id)
            if po:
                po_lines = s.exec(select(PurchaseLine).where(
                    PurchaseLine.order_id == po.id)).all()
                by_ing = defaultdict(float)
                for l in lines:
                    by_ing[l.ingredient_id] += l.accepted_qty
                complete = True
                for pl in po_lines:
                    if hasattr(pl, "received_qty"):
                        pl.received_qty = (pl.received_qty or 0) + by_ing.get(pl.ingredient_id, 0)
                        s.add(pl)
                        ordered = float(getattr(pl, "qty_base", 0) or pl.qty)
                        if pl.received_qty + 1e-6 < ordered:
                            complete = False
                po.status = "delivered" if complete else "partial"
                if hasattr(po, "received_at"):
                    po.received_at = datetime.now()
                s.add(po)

        anbar.audit(s, staff, "anbar_receipt_confirm", "goodsreceipt", receipt_id,
                    f"{receipt.code} confirmed, {moved} lines, ₼{receipt.total_value}")
        if receipt.issues:
            anbar.raise_alert(s, f"receipt_issue:{receipt.id}", "delivery", "attention",
                              f"Quality issue on {receipt.code}",
                              f"Flagged: {receipt.issues.replace(',', ', ')}.",
                              ref_type="goods_receipt", ref_id=receipt.id)
        s.commit()
        return {"ok": True, "lines": moved,
                "message": f"{receipt.code} taken into stock ({moved} lines)."}


# ==================================================================== transfers


@router.get("/transfers")
def transfers(staff: Staff = Depends(_view)):
    with db() as s:
        locs = {l.id: l.name for l in s.exec(select(InvLocation)).all()}
        ings = {i.id: i.name for i in s.exec(select(Ingredient)).all()}
        rows = []
        for t in s.exec(select(InvTransfer).order_by(InvTransfer.requested_at.desc())).all():
            lines = s.exec(select(InvTransferLine).where(
                InvTransferLine.transfer_id == t.id)).all()
            rows.append({
                "id": t.id, "code": t.code, "status": t.status,
                "from": locs.get(t.from_location_id, "—"),
                "to": locs.get(t.to_location_id, "—"),
                "requested_by": t.requested_by,
                "requested_at": t.requested_at.strftime("%d %b %H:%M"),
                "approved_by": t.approved_by, "received_by": t.received_by,
                "note": t.note,
                "lines": [{"ingredient_id": l.ingredient_id,
                           "name": ings.get(l.ingredient_id, "—"),
                           "qty": round(l.qty_base, 3),
                           "received": round(l.received_qty, 3)} for l in lines],
            })
        return {"rows": rows,
                "locations": [{"id": k, "name": v} for k, v in locs.items()]}


@router.post("/transfers")
def create_transfer(body: dict = Body(...), staff: Staff = Depends(_edit)):
    with db() as s:
        try:
            frm, to = int(body["from_location_id"]), int(body["to_location_id"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose where the stock is moving from and to."}, 400)
        if frm == to:
            return JSONResponse({"error": "Source and destination must differ."}, 400)
        if not s.get(InvLocation, frm) or not s.get(InvLocation, to):
            return JSONResponse({"error": "That storage location no longer exists."}, 404)
        lines = body.get("lines") or []
        if not lines:
            return JSONResponse({"error": "Add at least one item to the transfer."}, 400)
        t = InvTransfer(from_location_id=frm, to_location_id=to, status="requested",
                        requested_by_id=staff.id, requested_by=staff.name,
                        note=str(body.get("note") or "").strip())
        s.add(t)
        s.flush()
        t.code = f"TR{t.id:05d}"
        items = anbar.items_by_ingredient(s)
        added = 0
        for raw in lines:
            try:
                ing_id = int(raw["ingredient_id"])
                qty = float(raw.get("qty", 0))
            except (KeyError, TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            item = items.get(ing_id)
            qty_base = anbar.to_base(item, qty, str(raw.get("unit") or ""))
            s.add(InvTransferLine(transfer_id=t.id, ingredient_id=ing_id,
                                  qty_base=qty_base,
                                  unit_cost=item.avg_cost if item else 0.0))
            added += 1
        if not added:
            return JSONResponse({"error": "No valid transfer line was supplied."}, 400)
        anbar.audit(s, staff, "anbar_transfer_create", "invtransfer", t.id, t.code)
        s.commit()
        return {"ok": True, "id": t.id, "code": t.code,
                "message": f"{t.code} requested ({added} lines)."}


@router.post("/transfers/{transfer_id}/status")
def transfer_status(transfer_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Stock leaves on 'in_transit' and lands on 'received' — a pair of
    ledger rows that net to zero, so a transfer can never invent stock."""
    with db() as s:
        t = s.get(InvTransfer, transfer_id)
        if not t:
            return JSONResponse({"error": "That transfer no longer exists."}, 404)
        target = str(body.get("status") or "").strip().lower()
        if target not in {"approved", "in_transit", "received", "cancelled"}:
            return JSONResponse({"error": f"'{target}' is not a valid transfer status."}, 400)
        lines = s.exec(select(InvTransferLine).where(
            InvTransferLine.transfer_id == transfer_id)).all()

        if target == "in_transit":
            if t.status in ("in_transit", "received"):
                return JSONResponse({"error": "This transfer has already left."}, 409)
            for line in lines:
                try:
                    anbar.post(s, ingredient_id=line.ingredient_id, qty_base=-line.qty_base,
                               txn_type="TRANSFER_OUT", staff=staff,
                               location_id=t.from_location_id,
                               ref_type="transfer_line", ref_id=line.id,
                               idem_key=f"transfer_out:{line.id}",
                               reason=f"transfer {t.code}")
                except StockError as exc:
                    return _err(exc)
            t.approved_by = t.approved_by or staff.name
            t.approved_at = t.approved_at or datetime.now()
        elif target == "received":
            if t.status != "in_transit":
                return JSONResponse(
                    {"error": "Send the transfer before receiving it."}, 409)
            for line in lines:
                line.received_qty = line.qty_base
                s.add(line)
                try:
                    anbar.post(s, ingredient_id=line.ingredient_id, qty_base=line.qty_base,
                               txn_type="TRANSFER_IN", staff=staff,
                               location_id=t.to_location_id,
                               ref_type="transfer_line", ref_id=line.id,
                               idem_key=f"transfer_in:{line.id}",
                               reason=f"transfer {t.code}")
                except StockError as exc:
                    return _err(exc)
            t.received_by = staff.name
            t.received_at = datetime.now()
        elif target == "approved":
            t.approved_by = staff.name
            t.approved_at = datetime.now()
        elif target == "cancelled" and t.status == "in_transit":
            return JSONResponse(
                {"error": "Stock is already in transit — receive it, then adjust."}, 409)

        previous, t.status = t.status, target
        s.add(t)
        anbar.audit(s, staff, "anbar_transfer_status", "invtransfer", transfer_id,
                    f"{t.code} {previous} -> {target}")
        s.commit()
        return {"ok": True, "status": target, "message": f"{t.code} is now {target}."}


# ==================================================================== stocktake


@router.get("/stocktakes")
def stocktakes(staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        rows = []
        for t in s.exec(select(InvStocktake).order_by(InvStocktake.started_at.desc())).all():
            rows.append({
                "id": t.id, "code": t.code, "scope": t.scope, "status": t.status,
                "blind": t.blind, "started_by": t.started_by,
                "started_at": t.started_at.strftime("%d %b %H:%M"),
                "approved_by": t.approved_by, "line_count": t.line_count,
                "variance_value": round(t.variance_value, 2) if show_money else None,
            })
        return {"rows": rows, "can_see_costs": show_money}


@router.post("/stocktakes")
def start_stocktake(body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Freeze the system quantity for every line in scope, then count."""
    with db() as s:
        scope = str(body.get("scope") or "full").strip()
        cat_id = int(body["category_id"]) if body.get("category_id") else None
        loc_id = int(body["location_id"]) if body.get("location_id") else None
        take = InvStocktake(
            scope=scope, category_id=cat_id, location_id=loc_id,
            blind=bool(body.get("blind")), status="counting",
            started_by_id=staff.id, started_by=staff.name,
            note=str(body.get("note") or "").strip())
        s.add(take)
        s.flush()
        take.code = f"ST{take.id:05d}"

        items = anbar.items_by_ingredient(s)
        selected = {int(x) for x in (body.get("ingredient_ids") or []) if str(x).isdigit()}
        count = 0
        for ing in s.exec(select(Ingredient)).all():
            item = items.get(ing.id)
            if item and not item.active:
                continue
            if scope == "category" and (not item or item.category_id != cat_id):
                continue
            if scope == "location" and (not item or item.location_id != loc_id):
                continue
            if scope == "selected" and ing.id not in selected:
                continue
            cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
            s.add(InvStocktakeLine(
                stocktake_id=take.id, ingredient_id=ing.id,
                system_qty=round(float(ing.in_stock or 0), 4), unit_cost=cost))
            count += 1
        if not count:
            return JSONResponse({"error": "No items fall inside that scope."}, 400)
        take.line_count = count
        s.add(take)
        anbar.audit(s, staff, "anbar_stocktake_start", "invstocktake", take.id,
                    f"{take.code} {scope}, {count} lines, blind={take.blind}")
        s.commit()
        return {"ok": True, "id": take.id, "code": take.code, "lines": count,
                "message": f"{take.code} open with {count} lines to count."}


@router.get("/stocktakes/{take_id}")
def stocktake_detail(take_id: int, staff: Staff = Depends(_view)):
    with db() as s:
        take = s.get(InvStocktake, take_id)
        if not take:
            return JSONResponse({"error": "That stocktake no longer exists."}, 404)
        show_money = staff.role in COST_ROLES
        ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
        items = anbar.items_by_ingredient(s)
        lines = s.exec(select(InvStocktakeLine).where(
            InvStocktakeLine.stocktake_id == take_id)).all()
        # A blind count hides the system figure until the count is submitted.
        hide = take.blind and take.status == "counting"
        rows = []
        for l in lines:
            ing = ings.get(l.ingredient_id)
            item = items.get(l.ingredient_id)
            rows.append({
                "id": l.id, "ingredient_id": l.ingredient_id,
                "name": ing.name if ing else "—",
                "unit": item.base_unit if item else (ing.unit if ing else ""),
                "system_qty": None if (hide and l.counted_qty is None) else round(l.system_qty, 3),
                "counted_qty": l.counted_qty,
                "variance_qty": round(l.variance_qty, 3),
                "variance_value": round(l.variance_value, 2) if show_money else None,
                "unit_cost": round(l.unit_cost, 4) if show_money else None,
                "comment": l.comment, "counted_by": l.counted_by,
            })
        rows.sort(key=lambda r: r["name"].lower())
        return {
            "stocktake": {
                "id": take.id, "code": take.code, "scope": take.scope,
                "status": take.status, "blind": take.blind,
                "started_by": take.started_by,
                "started_at": take.started_at.strftime("%d %b %H:%M"),
                "approved_by": take.approved_by, "note": take.note,
                "variance_value": round(take.variance_value, 2) if show_money else None,
            },
            "lines": rows, "blind_active": hide, "can_see_costs": show_money,
        }


@router.post("/stocktakes/{take_id}/count")
def stocktake_count(take_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Record physical counts. Adjusts nothing — that waits for approval."""
    with db() as s:
        take = s.get(InvStocktake, take_id)
        if not take:
            return JSONResponse({"error": "That stocktake no longer exists."}, 404)
        if take.status not in ("counting", "review"):
            return JSONResponse({"error": "This stocktake is closed."}, 409)
        counts = body.get("counts") or []
        updated = 0
        for raw in counts:
            try:
                line = s.get(InvStocktakeLine, int(raw["line_id"]))
                qty = float(raw["counted_qty"])
            except (KeyError, TypeError, ValueError):
                continue
            if not line or line.stocktake_id != take_id or qty < 0:
                continue
            line.counted_qty = round(qty, 4)
            line.variance_qty = round(qty - line.system_qty, 4)
            line.variance_value = round(line.variance_qty * line.unit_cost, 4)
            line.counted_by = staff.name
            line.counted_at = datetime.now()
            line.comment = str(raw.get("comment") or "").strip()[:200]
            s.add(line)
            updated += 1
        lines = s.exec(select(InvStocktakeLine).where(
            InvStocktakeLine.stocktake_id == take_id)).all()
        take.variance_value = round(sum(l.variance_value for l in lines), 2)
        if all(l.counted_qty is not None for l in lines):
            take.status = "review"
        s.add(take)
        s.commit()
        return {"ok": True, "updated": updated, "status": take.status,
                "variance_value": take.variance_value,
                "message": f"{updated} lines counted."}


@router.post("/stocktakes/{take_id}/approve")
def stocktake_approve(take_id: int, staff: Staff = Depends(_edit)):
    """Apply the count. Physical becomes truth; the difference is a ledger row."""
    with db() as s:
        take = s.get(InvStocktake, take_id)
        if not take:
            return JSONResponse({"error": "That stocktake no longer exists."}, 404)
        if take.status == "approved":
            return JSONResponse({"error": "This stocktake has already been applied."}, 409)
        lines = s.exec(select(InvStocktakeLine).where(
            InvStocktakeLine.stocktake_id == take_id)).all()
        counted = [l for l in lines if l.counted_qty is not None]
        if not counted:
            return JSONResponse({"error": "Nothing has been counted yet."}, 400)
        applied = 0
        for line in counted:
            if abs(line.variance_qty) < 1e-9:
                continue
            try:
                anbar.post(s, ingredient_id=line.ingredient_id, qty_base=line.variance_qty,
                           txn_type="STOCKTAKE_ADJUSTMENT", staff=staff,
                           unit_cost=line.unit_cost,
                           ref_type="stocktake_line", ref_id=line.id,
                           idem_key=f"stocktake:{line.id}",
                           reason=f"stocktake {take.code}",
                           note=line.comment, allow_negative=True)
                applied += 1
            except StockError:
                continue
        take.status = "approved"
        take.approved_by = staff.name
        take.approved_at = datetime.now()
        take.variance_value = round(sum(l.variance_value for l in counted), 2)
        s.add(take)
        if abs(take.variance_value) >= 50:
            anbar.raise_alert(
                s, f"stocktake_variance:{take.id}", "variance",
                "high" if abs(take.variance_value) >= 200 else "attention",
                f"{take.code} closed with ₼{abs(take.variance_value)} variance",
                f"{applied} lines adjusted. Worth reviewing the largest differences "
                f"before the next count.", ref_type="stocktake", ref_id=take.id,
                value_at_risk=abs(take.variance_value))
        anbar.audit(s, staff, "anbar_stocktake_approve", "invstocktake", take_id,
                    f"{take.code} approved, {applied} adjustments, "
                    f"variance ₼{take.variance_value}")
        s.commit()
        return {"ok": True, "adjusted": applied, "variance_value": take.variance_value,
                "message": f"{take.code} applied. {applied} lines adjusted, "
                           f"variance ₼{take.variance_value}."}


# ==================================================================== waste


@router.get("/waste")
def waste_list(days: int = 30, staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        rows = anbar.waste_window(s, max(1, min(365, days)))
        ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
        items = anbar.items_by_ingredient(s)
        out = []
        for w in sorted(rows, key=lambda x: (x.logged_on, x.id or 0), reverse=True):
            ing = ings.get(w.ingredient_id)
            item = items.get(w.ingredient_id)
            cost = float(getattr(w, "cost_value", 0) or 0)
            if not cost and ing:
                cost = (w.qty or 0) * ((item.avg_cost if item else ing.cost_per_unit) or 0)
            out.append({
                "id": w.id, "ingredient_id": w.ingredient_id,
                "name": ing.name if ing else "—",
                "qty": round(w.qty or 0, 3),
                "unit": item.base_unit if item else (ing.unit if ing else ""),
                "reason": w.reason, "date": w.logged_on.isoformat(),
                "by": str(getattr(w, "staff_name", "") or ""),
                "note": str(getattr(w, "note", "") or ""),
                "cost": round(cost, 2) if show_money else None,
            })
        intel = anbar_ai.waste_intelligence(s, max(1, min(365, days)))
        if not show_money:
            intel = {"days": intel["days"], "entries": intel["entries"],
                     "findings": intel["findings"]}
        return {"rows": out, "intelligence": intel, "can_see_costs": show_money,
                "reasons": anbar.WASTE_REASONS}


@router.post("/waste")
def log_waste(body: dict = Body(...), staff: Staff = Depends(_report)):
    """Report waste. Kitchen staff may do this; they just cannot see the value."""
    with db() as s:
        try:
            ingredient_id = int(body["ingredient_id"])
            qty = _num(body, "qty")
        except (KeyError, TypeError, ValueError, StockError):
            return JSONResponse({"error": "Choose an item and enter a quantity."}, 400)
        if qty <= 0:
            return JSONResponse({"error": "Waste quantity must be above zero."}, 400)
        ing = s.get(Ingredient, ingredient_id)
        if not ing:
            return JSONResponse({"error": "That item no longer exists."}, 404)
        reason = str(body.get("reason") or "other").strip().lower()
        if reason not in anbar.WASTE_REASONS:
            reason = "other"
        item = anbar.item_for(s, ingredient_id)
        qty_base = anbar.to_base(item, qty, str(body.get("unit") or ""))
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0

        try:
            anbar.post(s, ingredient_id=ingredient_id, qty_base=-qty_base,
                       txn_type="WASTE", staff=staff, reason=reason,
                       note=str(body.get("note") or "").strip(),
                       allow_negative=True)
        except StockError as exc:
            return _err(exc)

        entry = WasteLog(ingredient_id=ingredient_id, qty=qty_base, reason=reason)
        for field, value in (("at", datetime.now()), ("staff_id", staff.id),
                             ("staff_name", staff.name), ("unit_cost", cost),
                             ("cost_value", round(qty_base * cost, 4)),
                             ("note", str(body.get("note") or "").strip()),
                             ("location_id", item.location_id if item else None)):
            if hasattr(entry, field):
                setattr(entry, field, value)
        s.add(entry)
        anbar.audit(s, staff, "anbar_waste", "ingredient", ingredient_id,
                    f"{qty_base:.3f} {ing.unit} — {reason} (₼{round(qty_base * cost, 2)})")
        if qty_base * cost >= 50:
            anbar.raise_alert(s, f"waste_large:{ingredient_id}:{date.today()}", "waste",
                              "attention", f"Large waste entry: {ing.name}",
                              f"{round(qty_base, 2)} {ing.unit} written off "
                              f"(₼{round(qty_base * cost, 2)}) — {reason}.",
                              ingredient_id=ingredient_id,
                              value_at_risk=round(qty_base * cost, 2))
        s.commit()
        return {"ok": True,
                "message": f"{round(qty_base, 3)} {ing.unit} of {ing.name} recorded as waste."}


@router.post("/shortage")
def report_shortage(body: dict = Body(...), staff: Staff = Depends(_report)):
    """Kitchen-facing: 'we are out of this'. Raises an alert, moves no stock."""
    with db() as s:
        try:
            ingredient_id = int(body["ingredient_id"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose an item."}, 400)
        ing = s.get(Ingredient, ingredient_id)
        if not ing:
            return JSONResponse({"error": "That item no longer exists."}, 404)
        note = str(body.get("note") or "").strip()
        kind = str(body.get("kind") or "shortage").strip()
        labels = {"shortage": "Shortage reported", "damaged": "Damaged stock reported",
                  "request": "Ingredient requested", "quality": "Quality problem reported"}
        anbar.raise_alert(
            s, f"shortage:{ingredient_id}:{date.today()}", "stock", "high",
            f"{labels.get(kind, 'Shortage reported')}: {ing.name}",
            f"{staff.name} ({staff.role.value.replace('_', ' ')}) reported "
            f"{ing.name}{': ' + note if note else '.'}",
            ingredient_id=ingredient_id)
        anbar.notify_manager(s, "warning", f"{labels.get(kind, 'Shortage')}: {ing.name}",
                             f"Reported by {staff.name}. {note}")
        anbar.audit(s, staff, "anbar_shortage", "ingredient", ingredient_id,
                    f"{kind}: {note}"[:200])
        s.commit()
        return {"ok": True, "message": f"{ing.name} reported to the warehouse."}


# ==================================================================== recipes & costing


@router.get("/recipes")
def recipes(staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        table = anbar.food_cost_table(s) if show_money else []
        menu = s.exec(select(MenuItem)).all()
        costed = {r["menu_item_id"] for r in table}
        lines = defaultdict(int)
        for r in s.exec(select(RecipeLine)).all():
            lines[r.menu_item_id] += 1
        missing = [{"menu_item_id": m.id, "name": m.name, "course": m.course,
                    "price": round(m.price, 2), "sold_30d": m.sold_30d}
                   for m in menu if not lines.get(m.id)]
        missing.sort(key=lambda r: -r["sold_30d"])
        return {
            "dishes": table,
            "uncosted": missing,
            "costed_count": len(costed) if show_money else len(menu) - len(missing),
            "total_dishes": len(menu),
            "can_see_costs": show_money,
        }


@router.get("/recipe-usage")
def recipe_usage(menu_item_id: Optional[int] = None, days: int = Query(30, ge=1, le=365),
                 portions: int = Query(1, ge=1, le=10000), staff: Staff = Depends(_view)):
    from ..models import OrderItem
    from ..anbar_models import DishConsumption
    with db() as s:
        menu = s.exec(select(MenuItem).order_by(MenuItem.name)).all()
        if menu_item_id is None and menu:
            menu_item_id = menu[0].id
        dish = s.get(MenuItem, menu_item_id) if menu_item_id else None
        if not dish:
            raise HTTPException(404, "Choose a dish.")
        cutoff = datetime.now() - timedelta(days=days)
        tickets = {i.id: i for i in s.exec(select(OrderItem).where(OrderItem.menu_item_id == dish.id)).all()}
        txns = [t for t in s.exec(select(InvTxn).where(InvTxn.txn_type == "SALE_CONSUMPTION", InvTxn.at >= cutoff)).all()
                if t.ref_type == "order_item" and t.ref_id in tickets]
        used = defaultdict(float)
        for txn in txns:
            used[txn.ingredient_id] += max(0, -txn.qty_base)
        line_ids = {t.ref_id for t in txns}
        snapshots = {c.order_item_id: c for c in s.exec(select(DishConsumption).where(DishConsumption.menu_item_id == dish.id)).all()}
        prepared = sum(snapshots[i].portions if i in snapshots else tickets[i].qty for i in line_ids)
        recipe = {r.ingredient_id: r.qty_per_portion for r in anbar.recipe_for(s, dish.id)}
        items = anbar.items_by_ingredient(s)
        result = []
        for ing_id in recipe.keys() | used.keys():
            ing = s.get(Ingredient, ing_id)
            if not ing:
                continue
            item = items.get(ing_id)
            base = item.base_unit if item else ing.unit
            unit = "g" if anbar.unit_dim(base) == "mass" else "ml" if anbar.unit_dim(base) == "volume" else base
            def display(qty):
                value = anbar.convert(qty, base, unit)
                return round(qty if value is None else value, 3)
            per_portion = recipe.get(ing_id, 0)
            planned = per_portion * portions
            result.append({"ingredient_id": ing_id, "name": ing.name, "name_ru": getattr(ing, 'name_ru', '') or '', "unit": unit,
                           "per_portion": display(per_portion), "used": display(used[ing_id]),
                           "planned": display(planned), "remaining": display(ing.in_stock),
                           "after_plan": display(ing.in_stock - planned), "in_current_recipe": ing_id in recipe})
        return {"dish": {"id": dish.id, "name": dish.name}, "dishes": [{"id": m.id, "name": m.name} for m in menu],
                "days": days, "portions": portions, "prepared_portions": prepared,
                "has_recipe": bool(recipe), "ingredients": sorted(result, key=lambda r:r["name"])}


@router.get("/recipes/{menu_item_id}")
def recipe_detail(menu_item_id: int, staff: Staff = Depends(_view)):
    with db() as s:
        m = s.get(MenuItem, menu_item_id)
        if not m:
            return JSONResponse({"error": "That dish no longer exists."}, 404)
        show_money = staff.role in COST_ROLES
        detail = anbar.dish_cost(s, menu_item_id)
        if not show_money:
            for line in detail["lines"]:
                line["unit_cost"] = line["cost"] = None
        price = float(m.price or 0)
        return {
            "dish": {"id": m.id, "name": m.name, "course": m.course,
                     "price": round(price, 2),
                     "cost": round(detail["cost"], 3) if show_money else None,
                     "food_cost_pct": round(100 * detail["cost"] / price, 1)
                                      if show_money and price else None,
                     "margin": round(price - detail["cost"], 2) if show_money else None,
                     "sold_30d": m.sold_30d},
            "lines": detail["lines"], "can_see_costs": show_money,
        }


@router.post("/recipes/{menu_item_id}")
def save_recipe(menu_item_id: int, body: dict = Body(...), staff: Staff = Depends(_edit)):
    """Replace a dish's recipe. Also refreshes MenuItem.food_cost so the
    existing finance and menu-engineering screens see the same number."""
    with db() as s:
        m = s.get(MenuItem, menu_item_id)
        if not m:
            return JSONResponse({"error": "That dish no longer exists."}, 404)
        raw_lines = body.get("lines")
        if not isinstance(raw_lines, list):
            raise HTTPException(400, "Recipe ingredients must be a list.")
        validated = []
        seen = set()
        for raw in raw_lines:
            try:
                ing_id = int(raw["ingredient_id"])
                qty = _num(raw, "qty")
                ing = s.get(Ingredient, ing_id)
                if not ing or qty <= 0 or ing_id in seen:
                    raise StockError("Each ingredient needs one positive quantity per portion.")
                item = anbar.item_for(s, ing_id)
                validated.append((ing_id, anbar.to_base(item, qty, item.recipe_unit if item else ing.unit)))
                seen.add(ing_id)
            except (KeyError, ValueError, TypeError, StockError) as exc:
                raise HTTPException(400, str(exc))
        for existing in s.exec(select(RecipeLine).where(RecipeLine.menu_item_id == menu_item_id)).all():
            s.delete(existing)
        for ing_id, qty in validated:
            s.add(RecipeLine(menu_item_id=menu_item_id, ingredient_id=ing_id, qty_per_portion=qty))
        added = len(validated)
        s.flush()
        detail = anbar.dish_cost(s, menu_item_id)
        m.food_cost = round(detail["cost"], 3)
        s.add(m)
        anbar.audit(s, staff, "anbar_recipe_save", "menuitem", menu_item_id,
                    f"{m.name}: {added} ingredients, cost ₼{m.food_cost}")
        s.commit()
        return {"ok": True, "lines": added, "cost": m.food_cost,
                "message": f"{m.name} recipe saved — ₼{m.food_cost} per portion."}


# ==================================================================== intelligence


@router.get("/intelligence")
def intelligence(staff: Staff = Depends(_view)):
    with db() as s:
        show_money = staff.role in COST_ROLES
        payload = {
            "brief": anbar_ai.daily_brief(s),
            "demand": anbar_ai.ingredient_demand(s, 1),
            "reorder": anbar_ai.reorder_plan(s),
            "anomalies": anbar_ai.anomalies(s),
            "expiry": anbar_ai.expiry_risk(s),
            "can_see_costs": show_money,
        }
        if show_money:
            payload["food_cost"] = anbar_ai.food_cost_intelligence(s)
            payload["waste"] = anbar_ai.waste_intelligence(s, 30)
            payload["suppliers"] = anbar_ai.supplier_comparison(s)
            payload["cost_impact"] = anbar_ai.cost_impact(s)
            payload["price_moves"] = anbar_ai.price_moves(s)[:12]
        else:
            for r in payload["reorder"]["rows"]:
                r["value"] = None
            payload["reorder"]["total_value"] = None
            payload["expiry"]["value_at_risk"] = None
        return payload


@router.get("/ask")
def ask(q: str = Query(""), staff: Staff = Depends(_view)):
    """Grounded answers for the Copilot. Every reply cites its own rows."""
    question = (q or "").strip().lower()
    if not question:
        return {"answer": "Ask about stock, orders, expiry, waste, suppliers or margins.",
                "data": {}}
    with db() as s:
        show_money = staff.role in COST_ROLES

        def money(x):
            return f"₼{round(x, 2)}" if show_money else "—"

        if any(w in question for w in ("order", "buy", "purchase", "reorder")):
            plan = anbar_ai.reorder_plan(s)
            if not plan["rows"]:
                return {"answer": "Nothing needs ordering — every line covers expected "
                                  "demand over its supplier lead time.", "data": plan}
            top = plan["rows"][:5]
            lines = "; ".join(f"{r['name']} {r['suggested']}{r['unit']}" for r in top)
            return {"answer": f"{len(plan['rows'])} lines need ordering "
                              f"({money(plan['total_value'] or 0)} total). Largest: {lines}. "
                              f"Forecast confidence: {plan['confidence']}.",
                    "data": {"rows": top, "confidence": plan["confidence"]}}

        if any(w in question for w in ("expir", "expiry", "use by", "going off")):
            exp = anbar_ai.expiry_risk(s)
            if not exp["rows"]:
                return {"answer": "Nothing is within seven days of its date.", "data": exp}
            names = ", ".join(f"{r['name']} ({r['days']}d)" for r in exp["rows"][:5])
            return {"answer": f"{len(exp['rows'])} lines expire within a week: {names}. "
                              f"{money(exp['value_at_risk'])} is beyond expected use.",
                    "data": exp}

        if "waste" in question:
            w = anbar_ai.waste_intelligence(s, 30)
            top = ", ".join(f"{r['name']} {money(r['value'])}" for r in w["by_item"][:4])
            return {"answer": f"{money(w['total'])} of waste over 30 days across "
                              f"{w['entries']} entries. Largest: {top or 'nothing logged'}.",
                    "data": w}

        if any(w in question for w in ("supplier", "price", "cost more", "increase")):
            moves = anbar_ai.price_moves(s)
            ups = [m for m in moves if m["change_pct"] > 0][:5]
            if not ups:
                return {"answer": "No supplier price increases are on record.",
                        "data": {"moves": moves[:5]}}
            names = ", ".join(f"{m['name']} +{m['change_pct']}%" for m in ups)
            impact = anbar_ai.cost_impact(s)
            monthly = round(sum(i["monthly_impact"] for i in impact), 2)
            return {"answer": f"Recent increases: {names}. Against current volumes that is "
                              f"about {money(monthly)} a month across {len(impact)} dishes.",
                    "data": {"moves": ups, "impact": impact[:6]}}

        if any(w in question for w in ("margin", "food cost", "profit")):
            fc = anbar_ai.food_cost_intelligence(s)
            if not fc.get("dishes"):
                return {"answer": fc.get("note", "No recipes on file yet."), "data": fc}
            worst = fc["dishes"][0]
            return {"answer": f"Average food cost is {fc['average_food_cost_pct']}% across "
                              f"{fc['costed_dishes']} costed dishes. Highest: "
                              f"{worst['name']} at {worst['food_cost_pct']}%.",
                    "data": fc}

        if any(w in question for w in ("how much", "stock", "inventory", "have")):
            val = anbar.valuation(s)
            items = anbar.items_by_ingredient(s)
            counts = defaultdict(int)
            for ing in s.exec(select(Ingredient)).all():
                counts[anbar.status_for(ing, items.get(ing.id))] += 1
            return {"answer": f"{money(val['total'])} of stock across {val['items']} lines. "
                              f"{counts['out']} out of stock, {counts['critical']} critical, "
                              f"{counts['low']} low.",
                    "data": {"valuation": val if show_money else None, "counts": dict(counts)}}

        brief = anbar_ai.daily_brief(s)
        return {"answer": brief["headline"] + " " + " ".join(
            p["text"] for p in brief["points"][:3]), "data": brief}


# ==================================================================== alerts, activity, reports


@router.get("/alerts")
def alerts(status: str = "open", staff: Staff = Depends(_view)):
    with db() as s:
        q = select(InvAlert).order_by(InvAlert.at.desc())
        if status:
            q = q.where(InvAlert.status == status)
        show_money = staff.role in COST_ROLES
        return {"rows": [{
            "id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title,
            "body": a.body, "status": a.status,
            "at": a.at.strftime("%d %b %H:%M"),
            "ingredient_id": a.ingredient_id,
            "value_at_risk": a.value_at_risk if show_money else None,
        } for a in s.exec(q).all()[:80]]}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, staff: Staff = Depends(_edit)):
    with db() as s:
        a = s.get(InvAlert, alert_id)
        if not a:
            return JSONResponse({"error": "That alert no longer exists."}, 404)
        a.status = "acknowledged"
        a.ack_by = staff.name
        a.ack_at = datetime.now()
        s.add(a)
        s.commit()
        return {"ok": True, "message": "Alert acknowledged."}


@router.get("/activity")
def activity(limit: int = 100, kind: str = "", staff: Staff = Depends(_view)):
    """The audit trail: every stock movement and every warehouse action."""
    with db() as s:
        show_money = staff.role in COST_ROLES
        ings = {i.id: i.name for i in s.exec(select(Ingredient)).all()}
        q = select(InvTxn).order_by(InvTxn.at.desc())
        if kind:
            q = q.where(InvTxn.txn_type == kind)
        txns = s.exec(q).all()[:max(1, min(400, limit))]
        ledger = [{
            "id": t.id, "at": t.at.strftime("%d %b %Y %H:%M"), "type": t.txn_type,
            "item": ings.get(t.ingredient_id, "—"), "ingredient_id": t.ingredient_id,
            "qty": round(t.qty_base, 3), "balance": round(t.balance_after, 3),
            "value": round(t.value, 2) if show_money else None,
            "by": t.staff_name, "role": t.staff_role,
            "reason": t.reason, "note": t.note,
            "ref": f"{t.ref_type}#{t.ref_id}" if t.ref_id else "",
        } for t in txns]

        audits = s.exec(select(AuditLog).where(
            AuditLog.action.like("anbar_%")).order_by(AuditLog.at.desc())).all()[:80]
        people = {p.id: p.name for p in s.exec(select(Staff)).all()}
        return {
            "ledger": ledger,
            "audit": [{
                "id": a.id, "at": a.at.strftime("%d %b %Y %H:%M"),
                "action": a.action.replace("anbar_", "").replace("_", " "),
                "by": people.get(a.staff_id, "SUFRA"),
                "entity": a.entity_type, "entity_id": a.entity_id, "detail": a.detail,
            } for a in audits],
            "types": sorted({t.txn_type for t in s.exec(select(InvTxn)).all()}),
            "can_see_costs": show_money,
        }


@router.get("/reports/{name}")
def report(name: str, days: int = 30, staff: Staff = Depends(_costs)):
    """Reports carry money, so they sit behind the cost tier by definition."""
    window = max(1, min(400, days))
    with db() as s:
        cutoff_date = date.today() - timedelta(days=window)
        cutoff_dt = datetime.now() - timedelta(days=window)
        items = anbar.items_by_ingredient(s)
        ings = {i.id: i for i in s.exec(select(Ingredient)).all()}

        if name == "valuation":
            val = anbar.valuation(s)
            rows = []
            for ing in ings.values():
                item = items.get(ing.id)
                cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
                qty = float(ing.in_stock or 0)
                if qty <= 0:
                    continue
                rows.append({"name": ing.name, "qty": round(qty, 3),
                             "unit": item.base_unit if item else ing.unit,
                             "cost": round(cost, 4), "value": round(qty * cost, 2)})
            rows.sort(key=lambda r: -r["value"])
            return {"title": "Inventory valuation", "total": val["total"],
                    "by_category": val["by_category"], "rows": rows}

        if name == "movement":
            txns = s.exec(select(InvTxn).where(InvTxn.at >= cutoff_dt)).all()
            by_type = defaultdict(lambda: {"qty": 0.0, "value": 0.0, "count": 0})
            for t in txns:
                b = by_type[t.txn_type]
                b["qty"] += t.qty_base
                b["value"] += t.value
                b["count"] += 1
            return {"title": "Inventory movement", "days": window,
                    "rows": [{"type": k, "count": v["count"],
                              "qty": round(v["qty"], 3), "value": round(v["value"], 2)}
                             for k, v in sorted(by_type.items())]}

        if name == "purchasing":
            receipts = s.exec(select(GoodsReceipt).where(
                GoodsReceipt.status == "confirmed",
                GoodsReceipt.delivered_on >= cutoff_date)).all()
            sups = {x.id: x.name for x in s.exec(select(Supplier)).all()}
            by_sup = defaultdict(lambda: {"value": 0.0, "deliveries": 0})
            for r in receipts:
                by_sup[sups.get(r.supplier_id, "—")]["value"] += r.total_value
                by_sup[sups.get(r.supplier_id, "—")]["deliveries"] += 1
            return {"title": "Purchasing", "days": window,
                    "total": round(sum(r.total_value for r in receipts), 2),
                    "rows": sorted(({"supplier": k, "value": round(v["value"], 2),
                                     "deliveries": v["deliveries"]}
                                    for k, v in by_sup.items()),
                                   key=lambda r: -r["value"])}

        if name == "supplier-performance":
            return {"title": "Supplier performance",
                    "rows": anbar_ai.supplier_intelligence(s)}

        if name == "waste":
            return {"title": "Waste", "days": window,
                    **anbar_ai.waste_intelligence(s, window)}

        if name == "variance":
            rows = []
            for ing in ings.values():
                theoretical = anbar.theoretical_stock(s, ing.id)
                physical = float(ing.in_stock or 0)
                if not theoretical and not physical:
                    continue
                item = items.get(ing.id)
                cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0
                diff = physical - theoretical
                if abs(diff) < 1e-6:
                    continue
                rows.append({
                    "name": ing.name, "theoretical": round(theoretical, 3),
                    "physical": round(physical, 3), "variance": round(diff, 3),
                    "unit": item.base_unit if item else ing.unit,
                    "value": round(diff * cost, 2),
                    "pct": round(100 * diff / theoretical, 1) if theoretical else None,
                })
            rows.sort(key=lambda r: r["value"])
            return {"title": "Stock variance", "rows": rows,
                    "total": round(sum(r["value"] for r in rows), 2)}

        if name == "food-cost":
            return {"title": "Food cost", **anbar_ai.food_cost_intelligence(s)}

        if name == "consumption":
            txns = s.exec(select(InvTxn).where(
                InvTxn.txn_type == "SALE_CONSUMPTION", InvTxn.at >= cutoff_dt)).all()
            by_item = defaultdict(lambda: {"qty": 0.0, "value": 0.0})
            for t in txns:
                by_item[t.ingredient_id]["qty"] += abs(t.qty_base)
                by_item[t.ingredient_id]["value"] += abs(t.value)
            rows = [{"name": ings[k].name if k in ings else "—",
                     "qty": round(v["qty"], 3),
                     "unit": items[k].base_unit if k in items else "",
                     "value": round(v["value"], 2)}
                    for k, v in by_item.items()]
            rows.sort(key=lambda r: -r["value"])
            return {"title": "Product consumption", "days": window, "rows": rows}

        if name == "expiry":
            return {"title": "Expiry risk", **anbar_ai.expiry_risk(s)}

        if name == "price-change":
            return {"title": "Price changes", "rows": anbar_ai.price_moves(s)}

        return JSONResponse({"error": f"No report called '{name}'."}, 404)

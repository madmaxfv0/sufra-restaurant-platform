"""SUFRA ANBAR — the stock engine.

One rule holds this module together: **stock only ever changes through
post()**. Nothing else writes Ingredient.in_stock. That gives three things
the old inventory screen could not:

  * every gram is explainable — the ledger says who, when, why and from what
  * nothing can be double-counted — post() is idempotent on idem_key
  * theoretical and physical stock can be compared, which is what variance is

Units: the ledger is always in the item's base unit. A recipe card written
in grams, a supplier invoicing in cases and a bar counting bottles all pass
through to_base() on the way in.

Costing: weighted average. Receiving 10kg at ₼10 on top of 10kg at ₼12 does
not make the stock worth ₼12/kg — it makes it worth ₼11/kg, and that is the
number waste, variance and food cost are all valued at.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlmodel import Session, SQLModel, select

from .database import DB_PATH, IS_SQLITE, engine
from .models import (AuditLog, Ingredient, MenuItem, Notification, Order,
                     OrderItem, PriceHistory, PurchaseLine, PurchaseOrder,
                     RecipeLine, Staff, Supplier, WasteLog)
from .anbar_models import (GoodsReceipt, GoodsReceiptLine, InvAlert, InvBatch,
                           InvCategory, InvItem, InvLocation, InvStocktake,
                           InvStocktakeLine, InvTransfer, InvTransferLine,
                           InvTxn, SupplierItem, WarehouseMigration, DishConsumption)

# ---------------------------------------------------------------- units

# Conversion to a canonical base within the same dimension. Anything not
# here (pcs, box, bottle, portion) is a counted unit and converts only
# through an item's own purchase_factor / recipe_factor.
MASS = {"kg": 1.0, "g": 0.001, "mg": 0.000001, "lb": 0.4535924, "oz": 0.02834952}
VOLUME = {"l": 1.0, "ml": 0.001, "cl": 0.01, "dl": 0.1}
COUNT = {"pcs", "piece", "unit", "box", "case", "bottle", "pack", "portion",
         "tray", "bag", "can", "jar", "tin", "roll", "sheet", "each"}

ALL_UNITS = ["kg", "g", "l", "ml", "pcs", "box", "case", "bottle", "pack",
             "portion", "tray", "bag", "can", "jar"]

TXN_IN = {"PURCHASE_RECEIPT", "TRANSFER_IN", "RETURN_TO_STOCK"}
TXN_OUT = {"SALE_CONSUMPTION", "WASTE", "TRANSFER_OUT", "RETURN_TO_SUPPLIER"}

WASTE_REASONS = ["spoilage", "expired", "prep", "overproduction", "returned",
                 "damaged", "incorrect_prep", "staff_meal", "quality_reject", "other"]

DEFAULT_CATEGORIES = [
    ("Meat", "Ət", "Мясо", "food", 10),
    ("Poultry", "Quş əti", "Птица", "food", 15),
    ("Seafood", "Dəniz məhsulları", "Морепродукты", "food", 20),
    ("Produce", "Tərəvəz və meyvə", "Овощи и фрукты", "food", 25),
    ("Dairy", "Süd məhsulları", "Молочные продукты", "food", 30),
    ("Dry Goods", "Quru ərzaq", "Бакалея", "food", 35),
    ("Bakery", "Çörək məmulatları", "Выпечка", "food", 40),
    ("Frozen", "Dondurulmuş", "Заморозка", "food", 45),
    ("Sauces", "Souslar", "Соусы", "food", 50),
    ("Spices", "Ədviyyatlar", "Специи", "food", 55),
    ("Beverages", "İçkilər", "Напитки", "beverage", 60),
    ("Coffee & Tea", "Qəhvə və çay", "Кофе и чай", "beverage", 65),
    ("Alcohol", "Alkoqol", "Алкоголь", "alcohol", 70),
    ("Cleaning", "Təmizlik", "Уборка", "non_food", 80),
    ("Packaging", "Qablaşdırma", "Упаковка", "non_food", 85),
    ("Consumables", "Sərfiyyat materialları", "Расходные материалы", "non_food", 90),
    ("Other", "Digər", "Прочее", "food", 99),
]

DEFAULT_LOCATIONS = [
    ("Main Warehouse", "Əsas anbar", "Главный склад", "warehouse", None, True, 10),
    ("Kitchen Fridge", "Mətbəx soyuducusu", "Кухонный холодильник", "fridge", 4.0, False, 20),
    ("Kitchen Freezer", "Mətbəx dondurucusu", "Кухонная морозильная камера", "freezer", -18.0, False, 30),
    ("Dry Storage", "Quru anbar", "Сухой склад", "dry", None, False, 40),
    ("Bar", "Bar", "Бар", "bar", None, False, 50),
    ("Prep Kitchen", "Hazırlıq mətbəxi", "Заготовочный цех", "prep", None, False, 60),
]

# Categories guessed from the existing free-text Ingredient.store / name, so
# a database that predates Anbar arrives already sorted instead of dumping
# every item into "Other".
_CATEGORY_HINTS = [
    ("Seafood", ("salmon", "tuna", "prawn", "shrimp", "squid", "sea bass", "cod",
                 "crab", "oyster", "mussel", "octopus", "caviar", "fish")),
    ("Meat", ("beef", "lamb", "pork", "veal", "steak", "tenderloin", "mince",
              "bacon", "sausage", "ribeye", "brisket")),
    ("Poultry", ("chicken", "duck", "turkey", "quail", "poussin")),
    ("Dairy", ("milk", "cream", "butter", "cheese", "yoghurt", "yogurt",
               "mozzarella", "parmesan", "feta", "egg")),
    ("Produce", ("tomato", "potato", "onion", "garlic", "lettuce", "carrot",
                 "pepper", "mushroom", "lemon", "lime", "herb", "basil",
                 "spinach", "avocado", "berry", "apple", "cucumber", "aubergine")),
    ("Bakery", ("bread", "flour", "dough", "pastry", "bun", "brioche")),
    ("Alcohol", ("wine", "vodka", "gin", "whisky", "whiskey", "rum", "beer",
                 "prosecco", "champagne", "tequila", "liqueur", "vermouth")),
    ("Coffee & Tea", ("coffee", "espresso", "tea", "matcha")),
    ("Beverages", ("juice", "soda", "cola", "water", "tonic", "syrup", "lemonade")),
    ("Spices", ("salt", "pepper corn", "saffron", "cumin", "paprika", "spice",
                "cinnamon", "sumac", "turmeric")),
    ("Sauces", ("sauce", "oil", "vinegar", "mayonnaise", "mustard", "stock", "paste")),
    ("Cleaning", ("detergent", "sanitiser", "sanitizer", "bleach", "cleaner", "soap")),
    ("Packaging", ("box", "container", "bag", "napkin", "cup", "lid", "wrap", "foil")),
]

_STORE_TO_LOCATION = {
    "dry store": "Dry Storage", "dry": "Dry Storage", "dry storage": "Dry Storage",
    "fridge": "Kitchen Fridge", "chiller": "Kitchen Fridge", "cold": "Kitchen Fridge",
    "freezer": "Kitchen Freezer", "frozen": "Kitchen Freezer",
    "bar": "Bar", "cellar": "Bar", "wine": "Bar",
    "prep": "Prep Kitchen", "kitchen": "Kitchen Fridge",
}


def unit_dim(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u in MASS:
        return "mass"
    if u in VOLUME:
        return "volume"
    return "count"


def convert(qty: float, frm: str, to: str) -> Optional[float]:
    """Convert between two units of the same dimension. None when the two
    units are not comparable — the caller must then use the item's own
    purchase/recipe factor rather than guessing."""
    a, b = (frm or "").strip().lower(), (to or "").strip().lower()
    if a == b:
        return qty
    for table in (MASS, VOLUME):
        if a in table and b in table:
            return qty * table[a] / table[b]
    return None


def to_base(item: Optional[InvItem], qty: float, unit: str, fallback_unit: str = "") -> float:
    """Normalise any quantity into the item's base unit.

    Tries real unit maths first (g -> kg). Falls back to the item's declared
    purchase/recipe factor, which is the only way a "case" or a "bottle" can
    become a number of kilograms or millilitres.
    """
    if item is None:
        return qty
    u = (unit or fallback_unit or item.base_unit or "").strip().lower()
    base = (item.base_unit or "kg").strip().lower()
    if not u or u == base:
        return qty
    direct = convert(qty, u, base)
    if direct is not None:
        return direct
    if u == (item.purchase_unit or "").strip().lower():
        return qty * (item.purchase_factor or 1.0)
    if u == (item.recipe_unit or "").strip().lower():
        return qty * (item.recipe_factor or 1.0)
    return qty


def from_base(item: Optional[InvItem], qty_base: float, unit: str) -> float:
    """Inverse of to_base, for display."""
    if item is None:
        return qty_base
    u = (unit or "").strip().lower()
    base = (item.base_unit or "kg").strip().lower()
    if not u or u == base:
        return qty_base
    direct = convert(qty_base, base, u)
    if direct is not None:
        return direct
    if u == (item.purchase_unit or "").strip().lower() and item.purchase_factor:
        return qty_base / item.purchase_factor
    if u == (item.recipe_unit or "").strip().lower() and item.recipe_factor:
        return qty_base / item.recipe_factor
    return qty_base


# ---------------------------------------------------------------- schema

SUPPLIER_COLUMNS = [
    ("legal_name", "TEXT NOT NULL DEFAULT ''"),
    ("contact_person", "TEXT NOT NULL DEFAULT ''"),
    ("phone", "TEXT NOT NULL DEFAULT ''"),
    ("email", "TEXT NOT NULL DEFAULT ''"),
    ("address", "TEXT NOT NULL DEFAULT ''"),
    ("payment_terms", "TEXT NOT NULL DEFAULT ''"),
    ("delivery_days", "TEXT NOT NULL DEFAULT ''"),
    ("min_order_value", "REAL NOT NULL DEFAULT 0"),
    ("preferred", "INTEGER NOT NULL DEFAULT 0"),
    ("active", "INTEGER NOT NULL DEFAULT 1"),
]

PURCHASE_ORDER_COLUMNS = [
    ("code", "TEXT NOT NULL DEFAULT ''"),
    ("expected_on", "DATE"),
    ("subtotal", "REAL NOT NULL DEFAULT 0"),
    ("tax", "REAL NOT NULL DEFAULT 0"),
    ("note", "TEXT NOT NULL DEFAULT ''"),
    ("created_by_id", "INTEGER"),
    ("approved_by", "TEXT NOT NULL DEFAULT ''"),
    ("approved_at", "DATETIME"),
    ("sent_at", "DATETIME"),
    ("received_at", "DATETIME"),
]

PURCHASE_LINE_COLUMNS = [
    ("purchase_unit", "TEXT NOT NULL DEFAULT ''"),
    ("qty_base", "REAL NOT NULL DEFAULT 0"),
    ("received_qty", "REAL NOT NULL DEFAULT 0"),
    ("note", "TEXT NOT NULL DEFAULT ''"),
]

WASTE_COLUMNS = [
    ("at", "DATETIME"),
    ("location_id", "INTEGER"),
    ("staff_id", "INTEGER"),
    ("staff_name", "TEXT NOT NULL DEFAULT ''"),
    ("unit_cost", "REAL NOT NULL DEFAULT 0"),
    ("cost_value", "REAL NOT NULL DEFAULT 0"),
    ("note", "TEXT NOT NULL DEFAULT ''"),
]


def ensure_schema() -> None:
    """Idempotent. Creates Anbar tables, widens the three existing tables
    Anbar needs more detail from, seeds reference data, and gives every
    pre-existing Ingredient an InvItem profile so nothing is invisible."""
    SQLModel.metadata.create_all(engine)
    if IS_SQLITE:
        con = sqlite3.connect(str(DB_PATH))
        try:
            def cols(table: str) -> set[str]:
                return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            for table, spec in (("supplier", SUPPLIER_COLUMNS),
                                ("purchaseorder", PURCHASE_ORDER_COLUMNS),
                                ("purchaseline", PURCHASE_LINE_COLUMNS),
                                ("wastelog", WASTE_COLUMNS)):
                present = cols(table)
                for name, ddl in spec:
                    if name not in present:
                        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            con.execute("CREATE INDEX IF NOT EXISTS ix_invtxn_ing_at "
                        "ON invtxn(ingredient_id, at)")
            # SQLModel builds a plain unique index from unique=True, which
            # would reject the second movement that has no natural key.
            # Replace it with a partial one that only polices real keys.
            con.execute("DROP INDEX IF EXISTS ix_invtxn_idem_key")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_invtxn_idem "
                        "ON invtxn(idem_key) WHERE idem_key != ''")
            con.execute("CREATE INDEX IF NOT EXISTS ix_invbatch_exp "
                        "ON invbatch(expires_on, status)")
            con.commit()
        finally:
            con.close()
    _seed_reference()


def normalize_recipe_units(s: Session):
    key = "recipe-base-units-v1"
    if s.get(WarehouseMigration, key):
        return
    items = items_by_ingredient(s)
    edited = {a.entity_id for a in s.exec(select(AuditLog).where(AuditLog.action == "anbar_recipe_save")).all()}
    for dish_id in edited:
        for line in recipe_for(s, dish_id):
            item = items.get(line.ingredient_id)
            if item:
                line.qty_per_portion = to_base(item, line.qty_per_portion, item.recipe_unit)
                s.add(line)
    s.add(WarehouseMigration(key=key))
    s.flush()


def _seed_reference() -> None:
    with Session(engine, expire_on_commit=False) as s:
        have_cat = {c.name for c in s.exec(select(InvCategory)).all()}
        for name, az, ru, kind, order in DEFAULT_CATEGORIES:
            if name not in have_cat:
                s.add(InvCategory(name=name, name_az=az, name_ru=ru,
                                  kind=kind, sort_order=order))
        have_loc = {l.name for l in s.exec(select(InvLocation)).all()}
        for name, az, ru, kind, temp, default, order in DEFAULT_LOCATIONS:
            if name not in have_loc:
                s.add(InvLocation(name=name, name_az=az, name_ru=ru, kind=kind,
                                  temp_c=temp, is_default=default, sort_order=order))
        s.commit()
        from .ingredient_names import RUSSIAN_NAMES
        for ing in s.exec(select(Ingredient)).all():
            if not ing.name_ru and ing.name in RUSSIAN_NAMES:
                ing.name_ru = RUSSIAN_NAMES[ing.name]
                s.add(ing)
        backfill_items(s)
        normalize_recipe_units(s)
        s.commit()
        seed_opening_balances(s)
        s.commit()


def seed_opening_balances(s: Session) -> int:
    """Give stock that predates Anbar an opening entry in the ledger.

    Without this, theoretical stock (which is the sum of the ledger) starts
    at zero while the shelf holds whatever was already there, and every
    pre-existing item reports a permanent phantom variance equal to its
    opening quantity. That would make the variance report — the single most
    useful number in a warehouse — worthless on day one.

    This writes InvTxn directly rather than through post(): the stock is
    already on the shelf and must not be added again. It is a bookkeeping
    entry recording an opening position, not a movement.
    """
    seeded = 0
    for ing in s.exec(select(Ingredient)).all():
        key = f"opening:{ing.id}"
        if s.exec(select(InvTxn).where(InvTxn.idem_key == key)).first():
            continue
        # Back-derive the opening position rather than assuming the ledger is
        # empty: opening + movements already recorded = what is on the shelf.
        # That keeps the arithmetic true even when Anbar has been running for
        # a while before this ever runs.
        recorded = sum(t.qty_base for t in s.exec(
            select(InvTxn).where(InvTxn.ingredient_id == ing.id)).all())
        qty = float(ing.in_stock or 0.0) - recorded
        if abs(qty) < 1e-9:
            continue
        item = item_for(s, ing.id)
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0.0
        s.add(InvTxn(
            txn_type="OPENING_BALANCE", ingredient_id=ing.id,
            location_id=item.location_id if item else None,
            qty_base=round(qty, 6), unit_cost=round(cost, 6),
            value=round(qty * cost, 4), balance_after=round(qty, 6),
            idem_key=key, staff_name="SUFRA",
            reason="opening balance when Anbar was installed",
            note="stock already on the shelf before the ledger existed"))
        seeded += 1
    return seeded


def _guess_category(s: Session, ing: Ingredient) -> Optional[int]:
    cats = {c.name: c.id for c in s.exec(select(InvCategory)).all()}
    haystack = f"{ing.name} {ing.store}".lower()
    for cat_name, words in _CATEGORY_HINTS:
        if any(w in haystack for w in words):
            return cats.get(cat_name)
    return cats.get("Other")


def _guess_location(s: Session, ing: Ingredient) -> Optional[int]:
    locs = {l.name: l.id for l in s.exec(select(InvLocation)).all()}
    store = (ing.store or "").strip().lower()
    for key, target in _STORE_TO_LOCATION.items():
        if key in store:
            return locs.get(target)
    return next((l.id for l in s.exec(select(InvLocation)).all() if l.is_default), None)


def backfill_items(s: Session) -> int:
    """Give every Ingredient without one an InvItem profile, with sensible
    units and thresholds derived from what the row already says."""
    known = {i.ingredient_id for i in s.exec(select(InvItem)).all()}
    made = 0
    for ing in s.exec(select(Ingredient).order_by(Ingredient.id)).all():
        if ing.id in known:
            continue
        base = (ing.unit or "kg").strip().lower()
        dim = unit_dim(base)
        recipe_unit, recipe_factor = {
            "mass": ("g", 0.001), "volume": ("ml", 0.001),
        }.get(dim, (base, 1.0))
        if base == "g":
            recipe_unit, recipe_factor = "g", 1.0
        if base == "ml":
            recipe_unit, recipe_factor = "ml", 1.0
        par = ing.par_level or 0.0
        cat_id = _guess_category(s, ing)
        cat = s.get(InvCategory, cat_id) if cat_id else None
        s.add(InvItem(
            ingredient_id=ing.id,
            sku=f"SKU{ing.id:04d}",
            category_id=cat_id,
            location_id=_guess_location(s, ing),
            base_unit=base, purchase_unit=base, purchase_factor=1.0,
            recipe_unit=recipe_unit, recipe_factor=recipe_factor,
            min_stock=round(par * 0.5, 3), reorder_point=round(par, 3),
            target_stock=round(par * 2.5, 3) if par else 0.0,
            max_stock=round(par * 4, 3) if par else 0.0,
            avg_cost=ing.cost_per_unit, last_cost=ing.cost_per_unit,
            is_food=(cat.kind != "non_food") if cat else True,
            track_batches=bool(ing.expires_on),
        ))
        made += 1
    return made


def item_for(s: Session, ingredient_id: int) -> Optional[InvItem]:
    return s.exec(select(InvItem).where(InvItem.ingredient_id == ingredient_id)).first()


def items_by_ingredient(s: Session) -> dict[int, InvItem]:
    return {i.ingredient_id: i for i in s.exec(select(InvItem)).all()}


# ---------------------------------------------------------------- the one write path


class StockError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def post(s: Session, *, ingredient_id: int, qty_base: float, txn_type: str,
         staff: Optional[Staff] = None, unit_cost: Optional[float] = None,
         location_id: Optional[int] = None, batch_id: Optional[int] = None,
         ref_type: str = "", ref_id: Optional[int] = None, idem_key: str = "",
         reason: str = "", note: str = "", allow_negative: bool = False,
         at: Optional[datetime] = None) -> Optional[InvTxn]:
    """Move stock. The only function in SUFRA that changes Ingredient.in_stock.

    Returns the ledger row, or None when idem_key has already been posted —
    which is the whole point: settling the same bill twice, or confirming a
    delivery twice, cannot move stock twice.
    """
    if qty_base == 0:
        return None
    if idem_key:
        existing = s.exec(select(InvTxn).where(InvTxn.idem_key == idem_key)).first()
        if existing:
            return None

    ing = s.get(Ingredient, ingredient_id)
    if not ing:
        raise StockError("That ingredient no longer exists.", 404)
    item = item_for(s, ingredient_id)

    cost = unit_cost if unit_cost is not None else (
        item.avg_cost if item and item.avg_cost else ing.cost_per_unit)

    before = float(ing.in_stock or 0.0)
    after = before + qty_base
    if after < 0 and not allow_negative:
        # Refuse rather than silently clamping: a negative balance is a real
        # operational signal and quietly zeroing it destroys the evidence.
        raise StockError(
            f"{ing.name}: only {before:g} {ing.unit} on hand, "
            f"cannot remove {abs(qty_base):g}.", 409)

    # Weighted average cost, recalculated on the way in only. Stock going
    # out is valued at the average it was carried at, which is what makes
    # waste and variance figures comparable across a month.
    if item is not None and qty_base > 0 and unit_cost is not None:
        prior_value = max(0.0, before) * (item.avg_cost or unit_cost)
        new_value = qty_base * unit_cost
        total_qty = max(0.0, before) + qty_base
        item.avg_cost = round((prior_value + new_value) / total_qty, 6) if total_qty else unit_cost
        item.last_cost = unit_cost
        item.updated_at = datetime.now()
        s.add(item)
        cost = item.avg_cost
        ing.cost_per_unit = round(item.avg_cost, 4)

    ing.in_stock = round(max(0.0, after) if not allow_negative else after, 6)
    s.add(ing)

    txn = InvTxn(
        at=at or datetime.now(), txn_type=txn_type, ingredient_id=ingredient_id,
        location_id=location_id or (item.location_id if item else None),
        batch_id=batch_id, qty_base=round(qty_base, 6), unit_cost=round(cost, 6),
        value=round(qty_base * cost, 4), balance_after=round(after, 6),
        ref_type=ref_type, ref_id=ref_id, idem_key=idem_key,
        staff_id=staff.id if staff else None,
        staff_name=staff.name if staff else "SUFRA",
        staff_role=(staff.role.value if staff and hasattr(staff.role, "value") else ""),
        reason=reason, note=note)
    s.add(txn)
    s.flush()
    return txn


def audit(s: Session, staff: Optional[Staff], action: str, entity: str,
          entity_id: Optional[int], detail: str) -> None:
    s.add(AuditLog(staff_id=staff.id if staff else None, action=action,
                   entity_type=entity, entity_id=entity_id, detail=detail[:400]))


# ---------------------------------------------------------------- FEFO batches


def consume_batches(s: Session, ingredient_id: int, qty_base: float,
                    location_id: Optional[int] = None) -> list[tuple[int, float, float]]:
    """Draw `qty_base` from open batches, earliest expiry first (FEFO).

    Returns [(batch_id, qty_taken, unit_cost)]. Items that do not track
    batches simply return nothing and are valued at weighted average.
    """
    rows = s.exec(select(InvBatch).where(
        InvBatch.ingredient_id == ingredient_id,
        InvBatch.status == "active",
        InvBatch.qty_base > 0).order_by(InvBatch.expires_on, InvBatch.received_on)).all()
    if location_id:
        preferred = [b for b in rows if b.location_id == location_id]
        rows = preferred + [b for b in rows if b.location_id != location_id]
    taken: list[tuple[int, float, float]] = []
    remaining = qty_base
    for b in rows:
        if remaining <= 1e-9:
            break
        draw = min(b.qty_base, remaining)
        b.qty_base = round(b.qty_base - draw, 6)
        if b.qty_base <= 1e-9:
            b.status = "depleted"
        s.add(b)
        taken.append((b.id, draw, b.unit_cost))
        remaining -= draw
    return taken


# ---------------------------------------------------------------- order consumption


def recipe_for(s: Session, menu_item_id: int) -> list[RecipeLine]:
    return s.exec(select(RecipeLine).where(
        RecipeLine.menu_item_id == menu_item_id)).all()


def consume_order(s: Session, order_id: int, staff: Optional[Staff] = None, only_item_id: Optional[int] = None) -> dict:
    """Post recipe estimates at preparation, with settlement as a fallback.

    A portion snapshot and per-ingredient ledger keys make repeated kitchen
    advances and later payment no-ops. Quantities are canonical stock units.
    A missing recipe remains uncounted and visible as a recipe gap.
    """
    order = s.get(Order, order_id)
    if not order:
        return {"ok": False, "reason": "no_order"}
    lines = s.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all()
    items = items_by_ingredient(s)

    posted = 0
    uncosted: set[str] = set()
    cost_total = 0.0
    for line in lines:
        if only_item_id is not None and line.id != only_item_id:
            continue
        if line.void_reason:
            continue
        recipe = recipe_for(s, line.menu_item_id)
        if not recipe:
            menu = s.get(MenuItem, line.menu_item_id)
            if menu:
                uncosted.add(menu.name)
            continue
        if s.get(DishConsumption, line.id):
            continue
        # Snapshot even when legacy ledger rows already exist: payment must not
        # redraw batches or deduct a cooked ticket a second time.
        s.add(DishConsumption(order_item_id=line.id, menu_item_id=line.menu_item_id, portions=line.qty))
        for r in recipe:
            if s.exec(select(InvTxn).where(InvTxn.idem_key == f"sale:{line.id}:{r.ingredient_id}")).first():
                continue
            item = items.get(r.ingredient_id)
            qty = r.qty_per_portion * line.qty
            if qty <= 0:
                continue
            batch_draws = consume_batches(s, r.ingredient_id, qty) if (
                item and item.track_batches) else []
            try:
                txn = post(s, ingredient_id=r.ingredient_id, qty_base=-qty,
                           txn_type="SALE_CONSUMPTION", staff=staff,
                           batch_id=batch_draws[0][0] if batch_draws else None,
                           ref_type="order_item", ref_id=line.id,
                           idem_key=f"sale:{line.id}:{r.ingredient_id}",
                           reason="recipe estimate at preparation" if only_item_id is not None else "recipe estimate at settlement",
                           note=f"order {order_id}", allow_negative=True)
            except StockError:
                continue
            if txn:
                posted += 1
                cost_total += abs(txn.value)
    return {"ok": True, "lines": posted, "cost": round(cost_total, 2),
            "uncosted_dishes": sorted(uncosted)}


def consume_order_safe(order_id: int, staff: Optional[Staff] = None) -> None:
    """Fire-and-forget wrapper for call sites inside service flows.

    Deducting stock must never be the reason a guest cannot pay their bill,
    so this opens its own session and swallows failures into a manager
    notification instead of propagating.
    """
    try:
        with Session(engine, expire_on_commit=False) as s:
            result = consume_order(s, order_id, staff)
            if result.get("uncosted_dishes"):
                names = ", ".join(result["uncosted_dishes"][:4])
                key = f"uncosted:{date.today().isoformat()}"
                if not s.exec(select(InvAlert).where(InvAlert.key == key)).first():
                    s.add(InvAlert(
                        key=key, kind="stock", severity="attention",
                        title="Dishes sold without a recipe",
                        body=f"{names} sold today with no recipe on file, so no "
                             f"ingredients were deducted. Add a recipe in Anbar → "
                             f"Recipes & Costing to make stock and food cost accurate."))
            s.commit()
    except Exception as exc:                      # never break service
        print("[anbar] consumption failed for order", order_id, exc)


# ---------------------------------------------------------------- status & valuation


def status_for(ing: Ingredient, item: Optional[InvItem],
               today: Optional[date] = None) -> str:
    """Healthy / Low / Critical / Out of stock / Over-stocked / Expiring / Expired."""
    today = today or date.today()
    qty = float(ing.in_stock or 0.0)
    if ing.expires_on:
        if ing.expires_on < today:
            return "expired"
        if (ing.expires_on - today).days <= 3 and qty > 0:
            return "expiring"
    if qty <= 0:
        return "out"
    reorder = (item.reorder_point if item and item.reorder_point else ing.par_level) or 0.0
    minimum = (item.min_stock if item and item.min_stock else reorder * 0.5) or 0.0
    maximum = (item.max_stock if item else 0.0) or 0.0
    if minimum and qty < minimum:
        return "critical"
    if reorder and qty <= reorder:
        return "low"
    if maximum and qty > maximum:
        return "over"
    return "healthy"


STATUS_RANK = {"out": 0, "expired": 1, "critical": 2, "expiring": 3,
               "low": 4, "over": 5, "healthy": 6}


def valuation(s: Session) -> dict:
    """Inventory value = sum(on-hand x weighted average cost)."""
    items = items_by_ingredient(s)
    cats = {c.id: c for c in s.exec(select(InvCategory)).all()}
    total = 0.0
    by_category: dict[str, float] = {}
    counted = 0
    for ing in s.exec(select(Ingredient)).all():
        item = items.get(ing.id)
        if item and not item.active:
            continue
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0.0
        value = float(ing.in_stock or 0.0) * cost
        total += value
        counted += 1
        cat = cats.get(item.category_id) if item and item.category_id else None
        key = cat.name if cat else "Other"
        by_category[key] = by_category.get(key, 0.0) + value
    return {
        "total": round(total, 2), "items": counted,
        "by_category": sorted(
            ({"name": k, "value": round(v, 2)} for k, v in by_category.items()),
            key=lambda r: -r["value"]),
    }


def theoretical_stock(s: Session, ingredient_id: int,
                      since: Optional[datetime] = None) -> float:
    """Opening + received + transfers in - consumption - waste - transfers out.

    Derived purely from the ledger, which is what makes it independent of
    Ingredient.in_stock and therefore able to disagree with it. That
    disagreement is variance.
    """
    q = select(InvTxn).where(InvTxn.ingredient_id == ingredient_id)
    if since:
        q = q.where(InvTxn.at >= since)
    rows = s.exec(q).all()
    return round(sum(r.qty_base for r in rows), 6)


def usage(s: Session, ingredient_id: int, days: int) -> float:
    """How much actually left stock through sales in the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    rows = s.exec(select(InvTxn).where(
        InvTxn.ingredient_id == ingredient_id,
        InvTxn.txn_type == "SALE_CONSUMPTION",
        InvTxn.at >= cutoff)).all()
    return round(abs(sum(r.qty_base for r in rows)), 4)


def waste_window(s: Session, days: int) -> list[WasteLog]:
    return s.exec(select(WasteLog).where(
        WasteLog.logged_on >= date.today() - timedelta(days=days))).all()


def waste_value(s: Session, rows: Iterable[WasteLog]) -> float:
    items = items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    total = 0.0
    for w in rows:
        stored = float(getattr(w, "cost_value", 0.0) or 0.0)
        if stored:
            total += stored
            continue
        item = items.get(w.ingredient_id)
        ing = ings.get(w.ingredient_id)
        cost = (item.avg_cost if item and item.avg_cost
                else (ing.cost_per_unit if ing else 0.0))
        total += (w.qty or 0.0) * cost
    return round(total, 2)


# ---------------------------------------------------------------- recipe costing


def dish_cost(s: Session, menu_item_id: int,
              items: Optional[dict[int, InvItem]] = None,
              ings: Optional[dict[int, Ingredient]] = None) -> dict:
    """What one portion costs to make, at today's weighted average cost."""
    items = items if items is not None else items_by_ingredient(s)
    ings = ings if ings is not None else {i.id: i for i in s.exec(select(Ingredient)).all()}
    total = 0.0
    lines = []
    for r in recipe_for(s, menu_item_id):
        ing = ings.get(r.ingredient_id)
        if not ing:
            continue
        item = items.get(r.ingredient_id)
        qty_base = r.qty_per_portion
        cost = (item.avg_cost if item and item.avg_cost else ing.cost_per_unit) or 0.0
        line_cost = qty_base * cost
        total += line_cost
        lines.append({
            "ingredient_id": ing.id, "name": ing.name, "name_ru": ing.name_ru,
            "qty": round(from_base(item, r.qty_per_portion, item.recipe_unit) if item else r.qty_per_portion, 4),
            "unit": item.recipe_unit if item else ing.unit,
            "qty_base": round(qty_base, 5),
            "base_unit": item.base_unit if item else ing.unit,
            "unit_cost": round(cost, 4), "cost": round(line_cost, 4),
        })
    return {"cost": round(total, 4), "lines": lines, "costed": bool(lines)}


def food_cost_table(s: Session) -> list[dict]:
    """Every dish with a recipe, priced. The bridge between Anbar and the menu."""
    items = items_by_ingredient(s)
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    out = []
    for m in s.exec(select(MenuItem)).all():
        detail = dish_cost(s, m.id, items, ings)
        if not detail["costed"]:
            continue
        price = float(m.price or 0.0)
        cost = detail["cost"]
        out.append({
            "menu_item_id": m.id, "name": m.name, "course": m.course,
            "price": round(price, 2), "cost": round(cost, 2),
            "food_cost_pct": round(100 * cost / price, 1) if price else 0.0,
            "margin": round(price - cost, 2),
            "sold_30d": m.sold_30d,
            "monthly_margin": round((price - cost) * m.sold_30d, 2),
            "stated_cost": round(float(m.food_cost or 0.0), 2),
            "lines": len(detail["lines"]),
        })
    out.sort(key=lambda r: -r["food_cost_pct"])
    return out


# ---------------------------------------------------------------- alerts


def raise_alert(s: Session, key: str, kind: str, severity: str, title: str,
                body: str, ingredient_id: Optional[int] = None,
                value_at_risk: float = 0.0, ref_type: str = "",
                ref_id: Optional[int] = None) -> Optional[InvAlert]:
    """Deduplicated on key. An open alert is refreshed, not duplicated."""
    existing = s.exec(select(InvAlert).where(
        InvAlert.key == key, InvAlert.status == "open")).first()
    if existing:
        existing.at = datetime.now()
        existing.title, existing.body = title, body
        existing.severity, existing.value_at_risk = severity, value_at_risk
        s.add(existing)
        return existing
    alert = InvAlert(key=key, kind=kind, severity=severity, title=title, body=body,
                     ingredient_id=ingredient_id, value_at_risk=value_at_risk,
                     ref_type=ref_type, ref_id=ref_id)
    s.add(alert)
    return alert


def notify_manager(s: Session, level: str, title: str, body: str) -> None:
    s.add(Notification(level=level, title=title[:120], body=body[:400],
                       audience="manager"))


def next_code(s: Session, model, prefix: str) -> str:
    count = len(s.exec(select(model)).all()) + 1
    return f"{prefix}{count:05d}"

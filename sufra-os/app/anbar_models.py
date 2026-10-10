"""SUFRA ANBAR — warehouse, procurement and food-cost tables.

Additive only. The existing spine stays canonical and untouched:

    Ingredient      the item identity, on-hand quantity and current cost
    RecipeLine      how much of an ingredient one portion of a dish uses
    Supplier        who sells it
    PurchaseOrder   / PurchaseLine — what was ordered
    PriceHistory    what it cost over time
    WasteLog        what was thrown away

Everything here hangs off those ids the same way MenuContent hangs off
MenuItem and HRProfile hangs off Staff. Nothing in models.py is rewritten,
so an existing nova.db upgrades in place and every screen that already
reads Ingredient keeps working exactly as before.

The one genuinely new idea is InvTxn: a signed, append-only ledger of every
gram that moves. Ingredient.in_stock remains the fast on-hand number the
rest of SUFRA reads; the ledger is how that number can be explained,
audited and reconciled.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------- reference data


class InvCategory(SQLModel, table=True):
    """Configurable product category. Not hard-coded: a café adds "Syrups",
    a bakery adds "Flours", without touching code."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    name_az: str = ""
    name_ru: str = ""
    kind: str = "food"            # food | beverage | alcohol | non_food
    # Non-food categories (cleaning, packaging) never need a recipe and are
    # excluded from food-cost maths.
    sort_order: int = 50
    active: bool = True


class InvLocation(SQLModel, table=True):
    """A physical place stock can sit. Stock is always somewhere."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    name_az: str = ""
    name_ru: str = ""
    kind: str = "warehouse"       # warehouse | fridge | freezer | bar | dry | prep | retail
    temp_c: Optional[float] = None
    is_default: bool = False
    sort_order: int = 50
    active: bool = True


class InvItem(SQLModel, table=True):
    """The enterprise profile of an Ingredient.

    Ingredient keeps identity, on-hand and current cost. This row carries
    everything the warehouse needs on top: SKU, category, storage, the
    purchase/recipe unit pair and its conversion factor, the four stock
    thresholds, and weighted-average cost.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True, unique=True)
    sku: str = Field(default="", index=True)
    barcode: str = ""
    category_id: Optional[int] = Field(default=None, foreign_key="invcategory.id", index=True)
    subcategory: str = ""
    location_id: Optional[int] = Field(default=None, foreign_key="invlocation.id", index=True)

    # ---- units ----------------------------------------------------
    # Everything in the ledger is stored in base_unit. purchase_factor is
    # how many base units one purchase unit contains: a 24-bottle case of
    # 700ml vodka bought by the case, held in ml, is 24 * 700 = 16800.
    base_unit: str = "kg"         # what stock is held and deducted in
    purchase_unit: str = "kg"     # what the supplier invoices
    purchase_factor: float = 1.0  # base units per purchase unit
    recipe_unit: str = "g"        # what a chef writes on a recipe card
    recipe_factor: float = 0.001  # base units per recipe unit

    # ---- thresholds -----------------------------------------------
    min_stock: float = 0.0        # never go below
    reorder_point: float = 0.0    # order when at or under
    target_stock: float = 0.0     # order up to
    max_stock: float = 0.0        # over this is over-stocked capital

    # ---- costing --------------------------------------------------
    avg_cost: float = 0.0         # weighted average, base unit
    last_cost: float = 0.0        # most recent landed cost, base unit

    secondary_supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id")
    shelf_life_days: int = 0      # 0 = does not perish
    storage_temp: str = ""
    track_batches: bool = False
    is_food: bool = True          # False = cleaning, packaging, consumables
    active: bool = True
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SupplierItem(SQLModel, table=True):
    """One supplier's offer for one ingredient. Several suppliers may
    quote the same ingredient at different prices and reliabilities."""

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    supplier_sku: str = ""
    pack_unit: str = "kg"
    pack_size_base: float = 1.0       # base units per pack
    price_per_pack: float = 0.0
    min_order_qty: float = 0.0
    lead_time_days: int = 1
    preferred: bool = False
    active: bool = True
    last_quoted_on: Optional[date] = None


# ---------------------------------------------------------------- the ledger


class InvTxn(SQLModel, table=True):
    """Append-only stock movement ledger. Never updated, never deleted.

    qty_base is signed: positive brings stock in, negative takes it out.
    Sum of qty_base for an ingredient is its theoretical on-hand, which is
    what variance is measured against.

    idem_key is the duplicate guard. A settled bill writes one row per
    order item with key "sale:<order_item_id>"; receiving a delivery writes
    "receipt:<line_id>". Re-running either is a no-op because the unique
    index refuses the second insert.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    txn_type: str = Field(default="MANUAL_ADJUSTMENT", index=True)
    # PURCHASE_RECEIPT | SALE_CONSUMPTION | WASTE | TRANSFER_IN | TRANSFER_OUT
    # | STOCKTAKE_ADJUSTMENT | MANUAL_ADJUSTMENT | RETURN_TO_SUPPLIER | RETURN_TO_STOCK
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    location_id: Optional[int] = Field(default=None, foreign_key="invlocation.id")
    batch_id: Optional[int] = Field(default=None, foreign_key="invbatch.id")

    qty_base: float = 0.0         # signed, in the item's base unit
    unit_cost: float = 0.0        # cost per base unit at the time it moved
    value: float = 0.0            # qty_base * unit_cost, signed
    balance_after: float = 0.0    # on-hand immediately after this movement

    ref_type: str = ""            # order_item | goods_receipt_line | stocktake_line | ...
    ref_id: Optional[int] = None
    # Not unique=True: that would build a plain unique index, and a plain
    # unique index treats '' as a value — so the second movement with no
    # natural idempotency key (a waste entry, a manual adjustment) would be
    # rejected. The partial index in ensure_schema enforces uniqueness only
    # where a key is actually set, which is the behaviour we want.
    idem_key: str = Field(default="", index=True)

    staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    staff_name: str = "SUFRA"
    staff_role: str = ""
    reason: str = ""
    note: str = ""


class InvBatch(SQLModel, table=True):
    """A delivered lot with its own expiry. Drives FEFO and expiry risk."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    location_id: Optional[int] = Field(default=None, foreign_key="invlocation.id")
    batch_code: str = ""
    qty_received: float = 0.0
    qty_base: float = 0.0             # remaining
    unit_cost: float = 0.0
    received_on: date = Field(default_factory=date.today)
    expires_on: Optional[date] = Field(default=None, index=True)
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id")
    receipt_id: Optional[int] = Field(default=None, foreign_key="goodsreceipt.id")
    status: str = "active"            # active | depleted | expired | quarantined


# ---------------------------------------------------------------- receiving


class GoodsReceipt(SQLModel, table=True):
    """A delivery at the door. Stock only moves when this is confirmed."""

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(default="", index=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    purchase_order_id: Optional[int] = Field(default=None, foreign_key="purchaseorder.id")
    invoice_ref: str = ""
    delivered_on: date = Field(default_factory=date.today)
    location_id: Optional[int] = Field(default=None, foreign_key="invlocation.id")
    status: str = "draft"             # draft | confirmed | cancelled
    total_value: float = 0.0
    issues: str = ""                  # csv: damaged, wrong_product, short, quality, expiry, temperature, price
    note: str = ""
    received_by_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    received_by: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    confirmed_at: Optional[datetime] = None


class GoodsReceiptLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    receipt_id: int = Field(foreign_key="goodsreceipt.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    ordered_qty: float = 0.0          # base units
    delivered_qty: float = 0.0
    accepted_qty: float = 0.0
    rejected_qty: float = 0.0
    reject_reason: str = ""
    unit_price: float = 0.0           # per base unit
    batch_code: str = ""
    expires_on: Optional[date] = None
    quality: str = "ok"               # ok | damaged | wrong | short | poor | expiring | temperature


# ---------------------------------------------------------------- transfers


class InvTransfer(SQLModel, table=True):
    """Moving stock between two locations. Never creates or destroys any."""

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(default="", index=True)
    from_location_id: int = Field(foreign_key="invlocation.id", index=True)
    to_location_id: int = Field(foreign_key="invlocation.id", index=True)
    status: str = "requested"         # requested | approved | in_transit | received | cancelled
    note: str = ""
    requested_by_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    requested_by: str = ""
    requested_at: datetime = Field(default_factory=datetime.now)
    approved_by: str = ""
    approved_at: Optional[datetime] = None
    received_by: str = ""
    received_at: Optional[datetime] = None


class InvTransferLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    transfer_id: int = Field(foreign_key="invtransfer.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    qty_base: float = 0.0
    received_qty: float = 0.0
    unit_cost: float = 0.0


# ---------------------------------------------------------------- stocktake


class InvStocktake(SQLModel, table=True):
    """A physical count. Nothing adjusts until a manager approves it."""

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(default="", index=True)
    scope: str = "full"               # full | category | location | selected
    category_id: Optional[int] = Field(default=None, foreign_key="invcategory.id")
    location_id: Optional[int] = Field(default=None, foreign_key="invlocation.id")
    status: str = "counting"          # counting | review | approved | cancelled
    blind: bool = False               # counter cannot see the system figure
    note: str = ""
    started_by_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    started_by: str = ""
    started_at: datetime = Field(default_factory=datetime.now)
    approved_by: str = ""
    approved_at: Optional[datetime] = None
    variance_value: float = 0.0
    line_count: int = 0


class InvStocktakeLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    stocktake_id: int = Field(foreign_key="invstocktake.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    system_qty: float = 0.0           # frozen when the count opened
    counted_qty: Optional[float] = None
    variance_qty: float = 0.0
    unit_cost: float = 0.0
    variance_value: float = 0.0
    counted_by: str = ""
    counted_at: Optional[datetime] = None
    comment: str = ""


# ---------------------------------------------------------------- alerts


class InvAlert(SQLModel, table=True):
    """An Anbar finding worth a manager's attention. Deduplicated by key
    so the same shortage does not generate a new row every minute."""

    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    key: str = Field(default="", index=True)
    kind: str = "stock"               # stock | expiry | price | variance | waste | delivery | approval
    severity: str = "info"            # info | attention | high | critical
    title: str = ""
    body: str = ""
    ingredient_id: Optional[int] = Field(default=None, foreign_key="ingredient.id")
    ref_type: str = ""
    ref_id: Optional[int] = None
    value_at_risk: float = 0.0
    status: str = "open"              # open | acknowledged | resolved
    ack_by: str = ""
    ack_at: Optional[datetime] = None


class WarehouseMigration(SQLModel, table=True):
    key: str = Field(primary_key=True)
    applied_at: datetime = Field(default_factory=datetime.now)


class DishConsumption(SQLModel, table=True):
    """Snapshot of portions at preparation time, independent of later ticket edits."""
    order_item_id: int = Field(primary_key=True, foreign_key="orderitem.id")
    menu_item_id: int = Field(foreign_key="menuitem.id")
    portions: int
    at: datetime = Field(default_factory=datetime.now, index=True)
